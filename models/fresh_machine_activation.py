from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from models.hardware_profile import HardwareProfile
from models.intelligence_restore import IntelligenceRestorePackage, RestoreAction, build_restore_preflight
from models.portable_intelligence import (
    ExecutionTarget,
    FilesystemIntelligenceManifestStore,
    IntelligenceManifest,
    ModelTier,
    RuntimeCandidate,
    RuntimeSelection,
    select_runtime,
)


_SCHEMA_VERSION = 1


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _maximum_tier(policy: Mapping[str, Any]) -> ModelTier | None:
    raw = str(policy.get("maximum_tier") or "").strip().lower()
    if not raw:
        return None
    try:
        return ModelTier(raw)
    except ValueError as exc:
        raise ValueError("intelligence manifest runtime_policy maximum_tier is invalid") from exc


@dataclass(frozen=True)
class ActivationBlocker:
    code: str
    detail: str

    def public(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class FreshMachineActivationPreflight:
    owner_id: str
    package_id: str
    manifest_id: str
    manifest_fingerprint: str
    ready: bool
    runtime_selection: RuntimeSelection | None
    blockers: tuple[ActivationBlocker, ...]
    local_artifacts: dict[str, str]

    def require_ready(self) -> None:
        if not self.ready:
            codes = ",".join(blocker.code for blocker in self.blockers) or "unknown"
            raise RuntimeError(f"fresh-machine activation blocked: {codes}")

    def public(self) -> dict[str, Any]:
        selection = self.runtime_selection
        return {
            "owner_id": self.owner_id,
            "package_id": self.package_id,
            "manifest_id": self.manifest_id,
            "manifest_fingerprint": self.manifest_fingerprint,
            "ready": self.ready,
            "runtime_id": selection.candidate.runtime_id if selection else None,
            "model_ref": selection.candidate.model_ref if selection else None,
            "target": selection.candidate.target.value if selection else None,
            "blockers": [item.public() for item in self.blockers],
            "local_artifacts": dict(self.local_artifacts),
        }


@dataclass(frozen=True)
class RuntimeActivationProof:
    ready: bool
    runtime_id: str
    model_ref: str
    detail: str = ""


class RuntimeActivationBackend(Protocol):
    def activate(
        self,
        candidate: RuntimeCandidate,
        *,
        manifest: IntelligenceManifest,
        local_artifacts: Mapping[str, str],
    ) -> RuntimeActivationProof: ...


class UnavailableRuntimeActivationBackend:
    def activate(self, candidate, *, manifest, local_artifacts) -> RuntimeActivationProof:
        return RuntimeActivationProof(
            ready=False,
            runtime_id=candidate.runtime_id,
            model_ref=candidate.model_ref,
            detail="runtime_activation_backend_unavailable",
        )


@dataclass(frozen=True)
class FreshMachineActivationReceipt:
    schema_version: int
    receipt_id: str
    fingerprint: str
    owner_id: str
    package_id: str
    manifest_id: str
    manifest_fingerprint: str
    runtime_id: str
    model_ref: str
    target: str
    artifact_inventory_sha256: str

    def unsigned(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "owner_id": self.owner_id,
            "package_id": self.package_id,
            "manifest_id": self.manifest_id,
            "manifest_fingerprint": self.manifest_fingerprint,
            "runtime_id": self.runtime_id,
            "model_ref": self.model_ref,
            "target": self.target,
            "artifact_inventory_sha256": self.artifact_inventory_sha256,
        }

    def verify(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("unsupported activation receipt schema")
        expected = sha256(_canonical_json(self.unsigned()).encode("utf-8")).hexdigest()
        if self.fingerprint != expected:
            raise RuntimeError("activation receipt fingerprint mismatch")
        if self.receipt_id != f"var-{expected[:24]}":
            raise RuntimeError("activation receipt id mismatch")

    def public(self) -> dict[str, Any]:
        self.verify()
        payload = self.unsigned()
        payload.update({"receipt_id": self.receipt_id, "fingerprint": self.fingerprint})
        return payload

    @classmethod
    def create(
        cls,
        *,
        preflight: FreshMachineActivationPreflight,
        selection: RuntimeSelection,
    ) -> "FreshMachineActivationReceipt":
        inventory_digest = sha256(
            _canonical_json(dict(sorted(preflight.local_artifacts.items()))).encode("utf-8")
        ).hexdigest()
        unsigned = {
            "schema_version": _SCHEMA_VERSION,
            "owner_id": preflight.owner_id,
            "package_id": preflight.package_id,
            "manifest_id": preflight.manifest_id,
            "manifest_fingerprint": preflight.manifest_fingerprint,
            "runtime_id": selection.candidate.runtime_id,
            "model_ref": selection.candidate.model_ref,
            "target": selection.candidate.target.value,
            "artifact_inventory_sha256": inventory_digest,
        }
        fingerprint = sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
        return cls(
            schema_version=_SCHEMA_VERSION,
            receipt_id=f"var-{fingerprint[:24]}",
            fingerprint=fingerprint,
            owner_id=preflight.owner_id,
            package_id=preflight.package_id,
            manifest_id=preflight.manifest_id,
            manifest_fingerprint=preflight.manifest_fingerprint,
            runtime_id=selection.candidate.runtime_id,
            model_ref=selection.candidate.model_ref,
            target=selection.candidate.target.value,
            artifact_inventory_sha256=inventory_digest,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FreshMachineActivationReceipt":
        receipt = cls(
            schema_version=int(payload.get("schema_version", 0)),
            receipt_id=str(payload.get("receipt_id") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            package_id=str(payload.get("package_id") or ""),
            manifest_id=str(payload.get("manifest_id") or ""),
            manifest_fingerprint=str(payload.get("manifest_fingerprint") or ""),
            runtime_id=str(payload.get("runtime_id") or ""),
            model_ref=str(payload.get("model_ref") or ""),
            target=str(payload.get("target") or ""),
            artifact_inventory_sha256=str(payload.get("artifact_inventory_sha256") or ""),
        )
        receipt.verify()
        return receipt


class FreshMachineActivationService:
    """Post-restore gate for activating the same qualified Vishnu on a new host.

    DisasterRecoveryService / BackupService remain the mutation authority for
    restoring owner state. This service operates only after that restore: it
    verifies the restored active Intelligence Manifest, verifies the immutable
    artifact inventory, selects a feasible registered runtime under manifest
    policy, requires exact runtime startup proof, and then records a tamper-
    evident activation receipt. It is not a provider router or model promoter.
    """

    def __init__(
        self,
        manifest_store: FilesystemIntelligenceManifestStore,
        runtime_backend: RuntimeActivationBackend | None = None,
    ) -> None:
        self.manifest_store = manifest_store
        self.runtime_backend = runtime_backend or UnavailableRuntimeActivationBackend()
        self.receipt_path = self.manifest_store.root / "intelligence" / "activation" / "active-runtime.json"

    def preflight(
        self,
        *,
        owner_id: str,
        restore_package: IntelligenceRestorePackage,
        hardware: HardwareProfile,
        runtime_candidates: Iterable[RuntimeCandidate],
        local_artifacts: Mapping[str, str],
    ) -> FreshMachineActivationPreflight:
        restore_package.verify()
        owner = str(owner_id or "").strip()
        if not owner:
            raise ValueError("owner_id is required")
        if restore_package.owner_id != owner:
            raise PermissionError("restore package does not belong to activation owner")

        blockers: list[ActivationBlocker] = []
        active = self.manifest_store.active()
        if active is None:
            blockers.append(ActivationBlocker("restored_manifest_missing", "no active Intelligence Manifest exists after restore"))
        elif active.manifest_id != restore_package.manifest.manifest_id or active.fingerprint != restore_package.manifest.fingerprint:
            blockers.append(ActivationBlocker("restored_manifest_mismatch", "active Intelligence Manifest does not match restore package"))

        inventory = {str(key): str(value).lower() for key, value in dict(local_artifacts).items()}
        restore_check = build_restore_preflight(
            restore_package,
            inventory,
            online=False,
            allow_fetch=False,
            expected_owner_id=owner,
        )
        for item in restore_check.items:
            if item.artifact.required and item.action is not RestoreAction.REUSE:
                blockers.append(
                    ActivationBlocker(
                        "required_artifact_not_verified",
                        f"{item.artifact.artifact_id}:{item.reason}",
                    )
                )

        policy = restore_package.manifest.runtime_policy
        local_only = bool(policy.get("local_only", False))
        maximum_tier = _maximum_tier(policy)
        selection: RuntimeSelection | None = None
        try:
            selection = select_runtime(
                tuple(runtime_candidates),
                hardware.device_capabilities(online=hardware.online),
                local_only=local_only,
                maximum_tier=maximum_tier,
            )
        except RuntimeError as exc:
            blockers.append(ActivationBlocker("no_feasible_runtime", str(exc)))

        return FreshMachineActivationPreflight(
            owner_id=owner,
            package_id=restore_package.package_id,
            manifest_id=restore_package.manifest.manifest_id,
            manifest_fingerprint=restore_package.manifest.fingerprint,
            ready=not blockers,
            runtime_selection=selection,
            blockers=tuple(blockers),
            local_artifacts=inventory,
        )

    def activate(
        self,
        *,
        preflight: FreshMachineActivationPreflight,
        restore_package: IntelligenceRestorePackage,
    ) -> FreshMachineActivationReceipt:
        preflight.require_ready()
        restore_package.verify()
        if restore_package.owner_id != preflight.owner_id:
            raise PermissionError("activation preflight owner mismatch")
        if restore_package.package_id != preflight.package_id:
            raise RuntimeError("activation preflight package mismatch")
        if restore_package.manifest.manifest_id != preflight.manifest_id:
            raise RuntimeError("activation preflight manifest mismatch")
        if restore_package.manifest.fingerprint != preflight.manifest_fingerprint:
            raise RuntimeError("activation preflight manifest fingerprint mismatch")

        active = self.manifest_store.active()
        if active is None or active.manifest_id != preflight.manifest_id or active.fingerprint != preflight.manifest_fingerprint:
            raise RuntimeError("active Intelligence Manifest changed after activation preflight")

        selection = preflight.runtime_selection
        if selection is None:
            raise RuntimeError("activation preflight has no runtime selection")
        proof = self.runtime_backend.activate(
            selection.candidate,
            manifest=restore_package.manifest,
            local_artifacts=preflight.local_artifacts,
        )
        if not proof.ready:
            raise RuntimeError(proof.detail or "runtime activation did not become ready")
        if proof.runtime_id != selection.candidate.runtime_id:
            raise RuntimeError("runtime activation proof runtime id mismatch")
        if proof.model_ref != selection.candidate.model_ref:
            raise RuntimeError("runtime activation proof model ref mismatch")

        receipt = FreshMachineActivationReceipt.create(preflight=preflight, selection=selection)
        self._write_receipt(receipt)
        return self.load_receipt()

    def _write_receipt(self, receipt: FreshMachineActivationReceipt) -> None:
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.receipt_path.with_name(f".{self.receipt_path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                json.dump(receipt.public(), handle, sort_keys=True, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.receipt_path)
        finally:
            temporary.unlink(missing_ok=True)

    def load_receipt(self) -> FreshMachineActivationReceipt:
        if not self.receipt_path.is_file() or self.receipt_path.is_symlink():
            raise FileNotFoundError(self.receipt_path)
        try:
            payload = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("activation receipt is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("activation receipt must be an object")
        return FreshMachineActivationReceipt.from_dict(payload)

    def status(self) -> dict[str, Any]:
        try:
            receipt = self.load_receipt()
        except FileNotFoundError:
            return {"activated": False, "receipt": None}
        active = self.manifest_store.active()
        exact = bool(
            active is not None
            and active.manifest_id == receipt.manifest_id
            and active.fingerprint == receipt.manifest_fingerprint
        )
        return {
            "activated": exact,
            "receipt": receipt.public(),
            "active_manifest_matches_receipt": exact,
        }
