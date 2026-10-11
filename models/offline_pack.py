from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from models.hardware_profile import HardwareProfile, OfflineReadinessReport, build_offline_readiness
from models.intelligence_restore import IntelligenceRestorePackage
from models.intelligence_vault import IntelligenceVault
from models.portable_intelligence import RuntimeCandidate


_SCHEMA_VERSION = 1
_GIB = 1024 ** 3


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _artifact_filename(artifact_id: str, digest: str) -> str:
    artifact_key = sha256(str(artifact_id).encode("utf-8")).hexdigest()[:20]
    return f"{artifact_key}-{digest[:20]}.bin"


def _safe_relative(value: str) -> Path:
    raw = Path(str(value))
    if raw.is_absolute() or ".." in raw.parts or not raw.parts:
        raise ValueError("offline pack artifact path is unsafe")
    if raw.parts[0] != "artifacts":
        raise ValueError("offline pack artifact must live under artifacts/")
    return raw


@dataclass(frozen=True)
class OfflinePackArtifact:
    artifact_id: str
    name: str
    kind: str
    sha256: str
    size_bytes: int
    relative_path: str
    required: bool
    encrypted: bool
    contains_private_data: bool

    def public(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "kind": self.kind,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "relative_path": self.relative_path,
            "required": self.required,
            "encrypted": self.encrypted,
            "contains_private_data": self.contains_private_data,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OfflinePackArtifact":
        item = cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            name=str(payload.get("name") or ""),
            kind=str(payload.get("kind") or "other"),
            sha256=str(payload.get("sha256") or "").lower(),
            size_bytes=int(payload.get("size_bytes", -1)),
            relative_path=str(payload.get("relative_path") or ""),
            required=bool(payload.get("required", True)),
            encrypted=bool(payload.get("encrypted", False)),
            contains_private_data=bool(payload.get("contains_private_data", False)),
        )
        if not item.artifact_id or not item.name:
            raise ValueError("offline pack artifact metadata is incomplete")
        if len(item.sha256) != 64 or any(char not in "0123456789abcdef" for char in item.sha256):
            raise ValueError("offline pack artifact digest is invalid")
        if item.size_bytes < 0:
            raise ValueError("offline pack artifact size is invalid")
        if item.contains_private_data and not item.encrypted:
            raise ValueError("private offline pack artifacts must remain encrypted")
        _safe_relative(item.relative_path)
        return item


@dataclass(frozen=True)
class OfflinePackManifest:
    schema_version: int
    pack_id: str
    fingerprint: str
    owner_id: str
    restore_package_id: str
    restore_package_fingerprint: str
    intelligence_manifest_id: str
    intelligence_manifest_fingerprint: str
    runtime_id: str
    model_ref: str
    artifacts: tuple[OfflinePackArtifact, ...]

    def unsigned(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "owner_id": self.owner_id,
            "restore_package_id": self.restore_package_id,
            "restore_package_fingerprint": self.restore_package_fingerprint,
            "intelligence_manifest_id": self.intelligence_manifest_id,
            "intelligence_manifest_fingerprint": self.intelligence_manifest_fingerprint,
            "runtime_id": self.runtime_id,
            "model_ref": self.model_ref,
            "artifacts": [item.public() for item in sorted(self.artifacts, key=lambda value: value.artifact_id)],
        }

    def verify_metadata(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("unsupported offline pack schema")
        if not all(
            (
                self.owner_id,
                self.restore_package_id,
                self.restore_package_fingerprint,
                self.intelligence_manifest_id,
                self.intelligence_manifest_fingerprint,
                self.runtime_id,
                self.model_ref,
            )
        ):
            raise ValueError("offline pack metadata is incomplete")
        expected = sha256(_canonical_json(self.unsigned()).encode("utf-8")).hexdigest()
        if expected != self.fingerprint:
            raise RuntimeError("offline pack fingerprint mismatch")
        if self.pack_id != f"vop-{expected[:24]}":
            raise RuntimeError("offline pack id mismatch")

    def public(self) -> dict[str, Any]:
        self.verify_metadata()
        payload = self.unsigned()
        payload.update({"pack_id": self.pack_id, "fingerprint": self.fingerprint})
        return payload

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        restore_package: IntelligenceRestorePackage,
        readiness: OfflineReadinessReport,
        artifacts: Iterable[OfflinePackArtifact],
    ) -> "OfflinePackManifest":
        restore_package.verify()
        readiness.require_ready()
        if restore_package.owner_id != str(owner_id):
            raise PermissionError("offline pack owner mismatch")
        selection = readiness.runtime_selection
        if selection is None:
            raise RuntimeError("offline pack requires a selected local runtime")
        normalized = tuple(sorted(tuple(artifacts), key=lambda item: item.artifact_id))
        unsigned = {
            "schema_version": _SCHEMA_VERSION,
            "owner_id": restore_package.owner_id,
            "restore_package_id": restore_package.package_id,
            "restore_package_fingerprint": restore_package.fingerprint,
            "intelligence_manifest_id": restore_package.manifest.manifest_id,
            "intelligence_manifest_fingerprint": restore_package.manifest.fingerprint,
            "runtime_id": selection.candidate.runtime_id,
            "model_ref": selection.candidate.model_ref,
            "artifacts": [item.public() for item in normalized],
        }
        fingerprint = sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
        return cls(
            schema_version=_SCHEMA_VERSION,
            pack_id=f"vop-{fingerprint[:24]}",
            fingerprint=fingerprint,
            owner_id=restore_package.owner_id,
            restore_package_id=restore_package.package_id,
            restore_package_fingerprint=restore_package.fingerprint,
            intelligence_manifest_id=restore_package.manifest.manifest_id,
            intelligence_manifest_fingerprint=restore_package.manifest.fingerprint,
            runtime_id=selection.candidate.runtime_id,
            model_ref=selection.candidate.model_ref,
            artifacts=normalized,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OfflinePackManifest":
        raw_artifacts = payload.get("artifacts") or ()
        if not isinstance(raw_artifacts, (list, tuple)):
            raise ValueError("offline pack artifacts must be a list")
        manifest = cls(
            schema_version=int(payload.get("schema_version", 0)),
            pack_id=str(payload.get("pack_id") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            restore_package_id=str(payload.get("restore_package_id") or ""),
            restore_package_fingerprint=str(payload.get("restore_package_fingerprint") or ""),
            intelligence_manifest_id=str(payload.get("intelligence_manifest_id") or ""),
            intelligence_manifest_fingerprint=str(payload.get("intelligence_manifest_fingerprint") or ""),
            runtime_id=str(payload.get("runtime_id") or ""),
            model_ref=str(payload.get("model_ref") or ""),
            artifacts=tuple(OfflinePackArtifact.from_dict(dict(item)) for item in raw_artifacts),
        )
        manifest.verify_metadata()
        return manifest


@dataclass(frozen=True)
class OfflinePackVerification:
    manifest: OfflinePackManifest
    local_artifacts: dict[str, str]

    def public(self) -> dict[str, Any]:
        return {
            "ready": True,
            "pack_id": self.manifest.pack_id,
            "owner_id": self.manifest.owner_id,
            "runtime_id": self.manifest.runtime_id,
            "model_ref": self.manifest.model_ref,
            "local_artifacts": dict(self.local_artifacts),
        }


class OfflinePackManager:
    """Prepare immutable Vishnu artifacts for a disconnected session.

    The pack is a verified staging surface only. It does not decrypt private
    state, change the active Intelligence Manifest, or bypass BackupService /
    continuity restore authority. Its local-artifact index can be supplied to
    the existing restore preflight after transport.
    """

    def __init__(self, vault: IntelligenceVault) -> None:
        self.vault = vault

    def prepare(
        self,
        *,
        owner_id: str,
        restore_package: IntelligenceRestorePackage,
        hardware: HardwareProfile,
        runtime_candidates: Sequence[RuntimeCandidate],
        target: str | Path,
        required_artifact_ids: Iterable[str] = (),
    ) -> OfflinePackVerification:
        restore_package.verify()
        if restore_package.owner_id != str(owner_id):
            raise PermissionError("restore package does not belong to offline pack owner")
        destination = Path(target).expanduser().resolve()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)

        readiness = build_offline_readiness(hardware, runtime_candidates)
        readiness.require_ready()
        required_ids = {str(value) for value in required_artifact_ids}
        package_ids = {artifact.artifact_id for artifact in restore_package.artifacts}
        unknown_required = required_ids - package_ids
        if unknown_required:
            raise ValueError(f"required offline artifacts are not in restore package: {sorted(unknown_required)}")

        records: dict[str, Any] = {}
        total_bytes = 0
        for artifact in restore_package.artifacts:
            try:
                record = self.vault.verify(owner_id, artifact.artifact_id)
            except FileNotFoundError:
                if artifact.required or artifact.artifact_id in required_ids:
                    raise RuntimeError(f"required offline artifact missing from vault: {artifact.artifact_id}")
                continue
            if record.artifact.sha256.lower() != artifact.sha256.lower():
                raise RuntimeError(f"vault artifact does not match restore package: {artifact.artifact_id}")
            if record.artifact.contains_private_data and not record.artifact.encrypted:
                raise RuntimeError(f"private vault artifact is not encrypted: {artifact.artifact_id}")
            records[artifact.artifact_id] = record
            total_bytes += int(record.object_size)

        missing_explicit = required_ids - set(records)
        if missing_explicit:
            raise RuntimeError(f"required offline artifacts unavailable: {sorted(missing_explicit)}")
        if total_bytes > int(hardware.disk_free_gb * _GIB):
            raise RuntimeError("insufficient free disk for offline pack")

        staging = destination.with_name(f".{destination.name}.{uuid4().hex}.staging")
        if staging.exists():
            shutil.rmtree(staging)
        artifacts_root = staging / "artifacts"
        artifacts_root.mkdir(parents=True, exist_ok=False)
        materialized: list[OfflinePackArtifact] = []
        try:
            for artifact in restore_package.artifacts:
                record = records.get(artifact.artifact_id)
                if record is None:
                    continue
                filename = _artifact_filename(artifact.artifact_id, artifact.sha256.lower())
                relative = Path("artifacts") / filename
                target_path = staging / relative
                self.vault.materialize(owner_id, artifact.artifact_id, target_path)
                digest, size = _sha256_file(target_path)
                if digest != artifact.sha256.lower() or size != int(record.object_size):
                    raise RuntimeError(f"offline pack materialization verification failed: {artifact.artifact_id}")
                materialized.append(
                    OfflinePackArtifact(
                        artifact_id=artifact.artifact_id,
                        name=artifact.name,
                        kind=artifact.kind.value,
                        sha256=digest,
                        size_bytes=size,
                        relative_path=relative.as_posix(),
                        required=artifact.required,
                        encrypted=artifact.encrypted,
                        contains_private_data=artifact.contains_private_data,
                    )
                )

            pack_manifest = OfflinePackManifest.create(
                owner_id=owner_id,
                restore_package=restore_package,
                readiness=readiness,
                artifacts=materialized,
            )
            manifest_path = staging / "offline-pack.json"
            manifest_path.write_text(
                json.dumps(pack_manifest.public(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.verify(destination, expected_owner_id=owner_id, expected_restore_package=restore_package)

    @staticmethod
    def verify(
        root: str | Path,
        *,
        expected_owner_id: str | None = None,
        expected_restore_package: IntelligenceRestorePackage | None = None,
    ) -> OfflinePackVerification:
        pack_root = Path(root).expanduser().resolve()
        if not pack_root.is_dir() or pack_root.is_symlink():
            raise ValueError("offline pack root is invalid")
        manifest_path = pack_root / "offline-pack.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("offline pack manifest is missing or unsafe")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("offline pack manifest is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("offline pack manifest must be an object")
        manifest = OfflinePackManifest.from_dict(payload)
        if expected_owner_id is not None and manifest.owner_id != str(expected_owner_id):
            raise PermissionError("offline pack owner mismatch")
        if expected_restore_package is not None:
            expected_restore_package.verify()
            if manifest.restore_package_id != expected_restore_package.package_id:
                raise RuntimeError("offline pack restore package id mismatch")
            if manifest.restore_package_fingerprint != expected_restore_package.fingerprint:
                raise RuntimeError("offline pack restore package fingerprint mismatch")
            if manifest.intelligence_manifest_id != expected_restore_package.manifest.manifest_id:
                raise RuntimeError("offline pack intelligence manifest id mismatch")
            if manifest.intelligence_manifest_fingerprint != expected_restore_package.manifest.fingerprint:
                raise RuntimeError("offline pack intelligence manifest fingerprint mismatch")

        local: dict[str, str] = {}
        for artifact in manifest.artifacts:
            relative = _safe_relative(artifact.relative_path)
            path = (pack_root / relative).resolve()
            try:
                path.relative_to(pack_root)
            except ValueError as exc:
                raise ValueError("offline pack artifact escaped pack root") from exc
            if not path.is_file() or path.is_symlink():
                raise RuntimeError(f"offline pack artifact missing or unsafe: {artifact.artifact_id}")
            digest, size = _sha256_file(path)
            if digest != artifact.sha256 or size != artifact.size_bytes:
                raise RuntimeError(f"offline pack artifact integrity failure: {artifact.artifact_id}")
            local[artifact.artifact_id] = digest
        return OfflinePackVerification(manifest=manifest, local_artifacts=local)
