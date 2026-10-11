from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from models.fresh_machine_activation import (
    FreshMachineActivationService,
    RuntimeActivationProof,
)
from models.hardware_profile import HardwareProfiler, build_offline_readiness
from models.intelligence_restore import (
    IntelligenceRestorePackage,
    RestoreArtifact,
    RestoreArtifactKind,
)
from models.intelligence_vault import FilesystemIntelligenceVault
from models.model_bundle import (
    checkpoint_inventory_sha256,
    create_portable_model_bundle,
)
from models.offline_pack import OfflinePackManager
from models.portable_intelligence import (
    ExecutionTarget,
    FilesystemIntelligenceManifestStore,
    IntelligenceManifest,
    IntelligenceReference,
    ModelTier,
    RuntimeCandidate,
)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            json.dump(dict(payload), handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def runtime_candidates_from_manifest(manifest: IntelligenceManifest) -> tuple[RuntimeCandidate, ...]:
    """Read the authenticated runtime catalog from the Intelligence Manifest."""

    manifest.verify()
    raw = manifest.runtime_policy.get("runtime_candidates", ())
    if raw in (None, ""):
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("runtime_policy.runtime_candidates must be a list")
    if len(raw) > 32:
        raise ValueError("runtime candidate catalog exceeds limit")
    allowed = {
        "runtime_id",
        "model_ref",
        "tier",
        "target",
        "minimum_ram_gb",
        "minimum_vram_gb",
        "enabled",
    }
    candidates: list[RuntimeCandidate] = []
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("runtime candidate must be an object")
        unknown = set(map(str, item)) - allowed
        if unknown:
            raise ValueError(f"runtime candidate has unsupported fields: {sorted(unknown)}")
        candidate = RuntimeCandidate(
            runtime_id=str(item.get("runtime_id") or ""),
            model_ref=str(item.get("model_ref") or ""),
            tier=ModelTier(str(item.get("tier") or "")),
            target=ExecutionTarget(str(item.get("target") or "")),
            minimum_ram_gb=float(item.get("minimum_ram_gb", 0) or 0),
            minimum_vram_gb=float(item.get("minimum_vram_gb", 0) or 0),
            enabled=bool(item.get("enabled", True)),
        )
        if candidate.runtime_id in ids:
            raise ValueError("runtime candidate ids must be unique")
        ids.add(candidate.runtime_id)
        candidates.append(candidate)
    return tuple(candidates)


def runtime_candidate_public(candidate: RuntimeCandidate) -> dict[str, Any]:
    return {
        "runtime_id": candidate.runtime_id,
        "model_ref": candidate.model_ref,
        "tier": candidate.tier.value,
        "target": candidate.target.value,
        "minimum_ram_gb": candidate.minimum_ram_gb,
        "minimum_vram_gb": candidate.minimum_vram_gb,
        "enabled": candidate.enabled,
    }


class GovernedRouterActivationBackend:
    """Health-proof adapter over the already-authoritative model router.

    This adapter does not route inference or mutate provider choice. It proves
    that the runtime selected from the authenticated manifest corresponds to a
    currently configured provider/model and that its existing endpoint responds
    to the router's bounded health request.
    """

    def __init__(self, router) -> None:
        self.router = router

    def activate(self, candidate, *, manifest, local_artifacts) -> RuntimeActivationProof:
        providers = getattr(self.router, "providers", {}) or {}
        provider = providers.get(candidate.runtime_id)
        if provider is None:
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, "runtime_provider_not_registered")
        if not bool(provider.configured and (provider.private or provider.api_key)):
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, "runtime_provider_not_configured")
        if str(provider.model) != candidate.model_ref:
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, "runtime_model_mismatch")
        if candidate.target is ExecutionTarget.LOCAL and not bool(provider.private):
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, "local_runtime_is_not_private")
        disabled = set(getattr(self.router, "disabled", set()) or set())
        allowed = tuple(getattr(self.router, "owner_allowed", ()) or ())
        if provider.id in disabled or (allowed and provider.id not in allowed):
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, "runtime_provider_blocked_by_policy")
        try:
            response = self.router._request(provider, "GET", "/models", timeout=self.router.health_timeout)
            close = getattr(response, "close", None)
            if callable(close):
                close()
        except Exception as exc:
            return RuntimeActivationProof(False, candidate.runtime_id, candidate.model_ref, f"runtime_health_failed:{type(exc).__name__}")
        return RuntimeActivationProof(True, candidate.runtime_id, candidate.model_ref, "governed_router_health_verified")


class PortableIntelligenceRuntime:
    """Canonical composition root for Vishnu's portable intelligence services."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        model_router,
        settings=None,
        training_registry=None,
        specialist_registry=None,
        events=None,
        vault_persistent: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.settings = settings
        self.model_router = model_router
        self.training_registry = training_registry
        self.specialist_registry = specialist_registry
        self.events = events
        self.manifests = FilesystemIntelligenceManifestStore(self.data_dir)
        self.vault = FilesystemIntelligenceVault(
            self.data_dir / "intelligence-vault",
            persistent=bool(vault_persistent),
        )
        self.hardware = HardwareProfiler()
        self.offline_packs = OfflinePackManager(self.vault)
        self.activation = FreshMachineActivationService(
            self.manifests,
            GovernedRouterActivationBackend(model_router),
        )
        self.packages_root = self.data_dir / "intelligence" / "restore-packages"
        self.packages_root.mkdir(parents=True, exist_ok=True)
        self.active_package_path = self.data_dir / "intelligence" / "active-restore-package.json"
        self.offline_root = self.data_dir / "intelligence" / "offline-packs"
        self.offline_root.mkdir(parents=True, exist_ok=True)
        self.model_bundles_root = self.data_dir / "intelligence" / "model-bundles"
        self.model_bundles_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_package_id(package_id: str) -> str:
        value = str(package_id or "")
        if not value.startswith("virp-") or any(ch not in "0123456789abcdef" for ch in value[5:]):
            raise ValueError("invalid restore package id")
        return value

    def _package_path(self, package_id: str) -> Path:
        return self.packages_root / f"{self._safe_package_id(package_id)}.json"

    def save_restore_package(self, package: IntelligenceRestorePackage, *, activate: bool = True) -> IntelligenceRestorePackage:
        package.verify()
        path = self._package_path(package.package_id)
        payload = package.public()
        if path.exists():
            existing = self.load_restore_package(package.package_id)
            if existing.fingerprint != package.fingerprint:
                raise RuntimeError("immutable restore package conflict")
        else:
            _atomic_json(path, payload)
        if activate:
            self.manifests.activate(package.manifest)
            _atomic_json(
                self.active_package_path,
                {
                    "schema_version": 1,
                    "package_id": package.package_id,
                    "fingerprint": package.fingerprint,
                },
            )
        return self.load_restore_package(package.package_id)

    def load_restore_package(self, package_id: str) -> IntelligenceRestorePackage:
        path = self._package_path(package_id)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(package_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("restore package is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("restore package must be an object")
        return IntelligenceRestorePackage.from_dict(payload)

    def active_restore_package(self) -> IntelligenceRestorePackage | None:
        if not self.active_package_path.exists():
            return None
        if not self.active_package_path.is_file() or self.active_package_path.is_symlink():
            raise ValueError("active restore package pointer is invalid")
        try:
            pointer = json.loads(self.active_package_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("active restore package pointer is unreadable") from exc
        package = self.load_restore_package(str(pointer.get("package_id") or ""))
        if str(pointer.get("fingerprint") or "") != package.fingerprint:
            raise RuntimeError("active restore package pointer fingerprint mismatch")
        active_manifest = self.manifests.active()
        if active_manifest is None or active_manifest.manifest_id != package.manifest.manifest_id or active_manifest.fingerprint != package.manifest.fingerprint:
            raise RuntimeError("active restore package does not match active Intelligence Manifest")
        return package

    def _provider_candidates(self) -> tuple[RuntimeCandidate, ...]:
        providers = getattr(self.model_router, "providers", {}) or {}
        settings = self.settings
        local_tier_raw = str(getattr(settings, "local_ai_model_tier", "small") if settings is not None else "small")
        try:
            local_tier = ModelTier(local_tier_raw)
        except ValueError:
            local_tier = ModelTier.SMALL
        local_ram = float(getattr(settings, "local_ai_min_ram_gb", 8.0) if settings is not None else 8.0)
        local_vram = float(getattr(settings, "local_ai_min_vram_gb", 0.0) if settings is not None else 0.0)
        rows: list[RuntimeCandidate] = []
        for provider in providers.values():
            if not bool(provider.configured and (provider.private or provider.api_key)):
                continue
            if provider.id == "self_hosted":
                rows.append(
                    RuntimeCandidate(
                        runtime_id=provider.id,
                        model_ref=str(provider.model),
                        tier=local_tier,
                        target=ExecutionTarget.LOCAL,
                        minimum_ram_gb=max(0.0, local_ram),
                        minimum_vram_gb=max(0.0, local_vram),
                    )
                )
            else:
                rows.append(
                    RuntimeCandidate(
                        runtime_id=provider.id,
                        model_ref=str(provider.model),
                        tier=ModelTier.LARGE,
                        target=ExecutionTarget.REMOTE,
                    )
                )
        return tuple(rows)

    def _active_training_model(self):
        if self.training_registry is None:
            return None
        governance = getattr(self.training_registry, "governance", None)
        active = governance.active_model() if governance is not None else None
        if not active:
            return None
        return self.training_registry.get_model(active["model_id"])

    @staticmethod
    def _canonical_checkpoint_digest(model) -> str:
        metrics = dict(getattr(model, "metrics", {}) or {})
        for key in ("artifact_sha256", "checkpoint_sha256"):
            value = str(metrics.get(key) or "").strip().lower()
            if len(value) == 64 and all(char in "0123456789abcdef" for char in value):
                return value
        checkpoint = Path(str(getattr(model, "checkpoint_ref", "") or "")).expanduser()
        if checkpoint.is_dir() and not checkpoint.is_symlink():
            return checkpoint_inventory_sha256(checkpoint)
        if checkpoint.is_file() and not checkpoint.is_symlink():
            return _sha256_file(checkpoint.resolve())[0]
        return ""

    def _model_references(self) -> tuple[IntelligenceReference, ...]:
        refs: list[IntelligenceReference] = []
        providers = getattr(self.model_router, "providers", {}) or {}
        for provider in providers.values():
            if bool(provider.configured and (provider.private or provider.api_key)):
                refs.append(
                    IntelligenceReference(
                        name=f"provider:{provider.id}",
                        ref_id=provider.id,
                        version=str(provider.model),
                    )
                )
        model = self._active_training_model()
        if model is not None:
            digest = self._canonical_checkpoint_digest(model)
            refs.append(
                IntelligenceReference(
                    name="trained:active",
                    ref_id=str(model.model_id),
                    version=str(getattr(model, "created_at", None) or model.model_id),
                    sha256=digest,
                )
            )
        return tuple(refs)

    def _agent_references(self) -> tuple[IntelligenceReference, ...]:
        if self.specialist_registry is None:
            return ()
        refs: list[IntelligenceReference] = []
        for binding in self.specialist_registry.active_bindings():
            refs.append(
                IntelligenceReference(
                    name=f"specialist:{binding.specialist_role}:{binding.task_domain}",
                    ref_id=binding.model_id,
                    version=binding.binding_id,
                )
            )
        return tuple(refs)

    def publish_current_manifest(self, *, core_version: str, owner_id: str = "owner") -> IntelligenceManifest:
        candidates = self._provider_candidates()
        privacy = str(getattr(self.model_router, "owner_privacy", "local_preferred") or "local_preferred")
        manifest = IntelligenceManifest.create(
            owner_id=owner_id,
            core_version=str(core_version or "unknown"),
            models=self._model_references(),
            agents=self._agent_references(),
            schemas={
                "portable_intelligence": "1",
                "restore_package": "1",
                "offline_pack": "1",
                "fresh_machine_activation": "1",
                "portable_model_bundle": "1",
            },
            registries={
                "training": "canonical",
                "specialists": "canonical-active-model-projection",
            },
            runtime_policy={
                "local_only": privacy == "local_only",
                "runtime_candidates": [runtime_candidate_public(item) for item in candidates],
            },
        )
        self.manifests.activate(manifest)
        if self.events is not None:
            self.events.emit("intelligence.manifest_published", manifest_id=manifest.manifest_id)
        return manifest

    def _portable_training_artifact(self, owner_id: str) -> RestoreArtifact | None:
        model = self._active_training_model()
        if model is None:
            return None
        checkpoint = Path(str(getattr(model, "checkpoint_ref", "") or "")).expanduser()
        method = str(getattr(model, "method", "") or "").lower()
        kind = RestoreArtifactKind.ADAPTER if method in {"lora", "qlora"} else RestoreArtifactKind.MODEL
        expected_inventory = self._canonical_checkpoint_digest(model)

        if checkpoint.is_dir() and not checkpoint.is_symlink():
            bundle_path = self.model_bundles_root / f"{model.model_id}.zip"
            bundle = create_portable_model_bundle(
                checkpoint,
                bundle_path,
                model_id=str(model.model_id),
                expected_inventory_sha256=expected_inventory or None,
            )
            source = bundle.path
            digest = bundle.bundle_sha256
            size = bundle.size_bytes
            name = "active-trained-model-bundle"
        elif checkpoint.is_file() and not checkpoint.is_symlink():
            source = checkpoint.resolve()
            digest, size = _sha256_file(source)
            name = "active-trained-model"
        else:
            raise RuntimeError("active trained-model checkpoint is missing or unsafe")

        artifact = RestoreArtifact(
            name=name,
            artifact_id=str(model.model_id),
            version=str(getattr(model, "created_at", None) or model.model_id),
            sha256=digest,
            locator=f"vault://sha256/{digest}",
            kind=kind,
            required=True,
            size_bytes=size,
        )
        return self.vault.put(owner_id, artifact, source).artifact

    def publish_current_restore_package(self, *, core_version: str, owner_id: str = "owner") -> IntelligenceRestorePackage:
        manifest = self.publish_current_manifest(core_version=core_version, owner_id=owner_id)
        artifact = self._portable_training_artifact(owner_id)
        artifacts = () if artifact is None else (artifact,)
        package = IntelligenceRestorePackage.create(manifest=manifest, artifacts=artifacts, owner_id=owner_id)
        saved = self.save_restore_package(package, activate=True)
        if self.events is not None:
            self.events.emit("intelligence.restore_package_published", package_id=saved.package_id)
        return saved

    def runtime_candidates(self) -> tuple[RuntimeCandidate, ...]:
        manifest = self.manifests.active()
        if manifest is None:
            return ()
        return runtime_candidates_from_manifest(manifest)

    def _vault_artifacts(self, package: IntelligenceRestorePackage) -> dict[str, str]:
        local: dict[str, str] = {}
        for artifact in package.artifacts:
            try:
                record = self.vault.verify(package.owner_id, artifact.artifact_id)
            except (FileNotFoundError, RuntimeError, ValueError, PermissionError):
                continue
            if record.artifact.sha256 == artifact.sha256.lower():
                local[artifact.artifact_id] = record.artifact.sha256
        return local

    def prepare_offline_pack(self, *, owner_id: str = "owner"):
        package = self.active_restore_package()
        if package is None:
            raise RuntimeError("no active restore package")
        if package.owner_id != owner_id:
            raise PermissionError("restore package owner mismatch")
        candidates = self.runtime_candidates()
        if not candidates:
            raise RuntimeError("active Intelligence Manifest has no runtime candidates")
        profile = self.hardware.probe(self.data_dir, online=False)
        target = self.offline_root / package.package_id
        if target.exists():
            return self.offline_packs.verify(target, expected_owner_id=owner_id, expected_restore_package=package)
        result = self.offline_packs.prepare(
            owner_id=owner_id,
            restore_package=package,
            hardware=profile,
            runtime_candidates=candidates,
            target=target,
        )
        if self.events is not None:
            self.events.emit("intelligence.offline_pack_prepared", pack_id=result.manifest.pack_id)
        return result

    def activation_preflight(self, *, owner_id: str = "owner", online: bool = False):
        package = self.active_restore_package()
        if package is None:
            raise RuntimeError("no active restore package")
        candidates = self.runtime_candidates()
        if not candidates:
            raise RuntimeError("active Intelligence Manifest has no runtime candidates")
        profile = self.hardware.probe(self.data_dir, online=bool(online))
        return self.activation.preflight(
            owner_id=owner_id,
            restore_package=package,
            hardware=profile,
            runtime_candidates=candidates,
            local_artifacts=self._vault_artifacts(package),
        )

    def activate(self, *, owner_id: str = "owner", online: bool = False):
        package = self.active_restore_package()
        if package is None:
            raise RuntimeError("no active restore package")
        preflight = self.activation_preflight(owner_id=owner_id, online=online)
        receipt = self.activation.activate(preflight=preflight, restore_package=package)
        if self.events is not None:
            self.events.emit("intelligence.runtime_activated", runtime_id=receipt.runtime_id, model_ref=receipt.model_ref)
        return receipt

    def status(self) -> dict[str, Any]:
        manifest = self.manifests.active()
        package = self.active_restore_package() if self.active_package_path.exists() else None
        candidates = runtime_candidates_from_manifest(manifest) if manifest is not None else ()
        profile = self.hardware.probe(self.data_dir, online=False)
        readiness = build_offline_readiness(profile, candidates) if candidates else None
        specialists = []
        if self.specialist_registry is not None:
            specialists = [item.public() for item in self.specialist_registry.active_bindings()]
        return {
            "manifest": manifest.public() if manifest is not None else None,
            "restore_package": package.public() if package is not None else None,
            "runtime_candidates": [runtime_candidate_public(item) for item in candidates],
            "hardware": profile.public(),
            "offline_readiness": readiness.public() if readiness is not None else {
                "ready": False,
                "blocked": ["runtime_catalog_missing"],
                "checks": [],
            },
            "vault": self.vault.status(),
            "activation": self.activation.status(),
            "specialist_bindings": specialists,
            "offline_pack_available": bool(package and (self.offline_root / package.package_id).is_dir()),
            "active_trained_model_artifact_included": bool(package and package.artifacts),
            "backup_restore_authority": "recovery.BackupService/continuity",
            "model_execution_authority": "models.GovernedModelRouter",
            "model_promotion_authority": "training.TrainingRegistry",
        }
