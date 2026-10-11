from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Protocol
from uuid import uuid4

from models.intelligence_restore import RestoreArtifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _owner_namespace(owner_id: str) -> str:
    owner = str(owner_id or "").strip()
    if not owner:
        raise ValueError("owner_id is required")
    return sha256(("vishnu-owner:" + owner).encode("utf-8")).hexdigest()


def _artifact_record_name(artifact_id: str) -> str:
    value = str(artifact_id or "").strip()
    if not value or len(value) > 256:
        raise ValueError("artifact_id is required and must be at most 256 characters")
    return sha256(("artifact:" + value).encode("utf-8")).hexdigest() + ".json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            json.dump(payload, handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class VaultArtifactRecord:
    schema_version: int
    owner_namespace: str
    artifact: RestoreArtifact
    object_sha256: str
    object_size: int
    created_at: str
    immutable: bool = True

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "owner_namespace": self.owner_namespace,
            "artifact": self.artifact.public(),
            "object_sha256": self.object_sha256,
            "object_size": self.object_size,
            "created_at": self.created_at,
            "immutable": self.immutable,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VaultArtifactRecord":
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported intelligence vault record schema")
        raw = payload.get("artifact")
        if not isinstance(raw, dict):
            raise ValueError("vault artifact record is invalid")
        record = cls(
            schema_version=1,
            owner_namespace=str(payload.get("owner_namespace") or ""),
            artifact=RestoreArtifact.from_dict(raw),
            object_sha256=str(payload.get("object_sha256") or ""),
            object_size=int(payload.get("object_size", -1)),
            created_at=str(payload.get("created_at") or ""),
            immutable=bool(payload.get("immutable", False)),
        )
        if record.object_sha256 != record.artifact.sha256.lower():
            raise RuntimeError("vault record object digest mismatch")
        if record.object_size < 0 or not record.created_at or not record.owner_namespace:
            raise ValueError("vault artifact record metadata is incomplete")
        if record.artifact.size_bytes is not None and record.artifact.size_bytes != record.object_size:
            raise RuntimeError("vault record object size mismatch")
        if not record.immutable:
            raise RuntimeError("vault artifact record must be immutable")
        return record


class IntelligenceVault(Protocol):
    persistent: bool

    def put(self, owner_id: str, artifact: RestoreArtifact, source: str | Path) -> VaultArtifactRecord: ...
    def verify(self, owner_id: str, artifact_id: str) -> VaultArtifactRecord: ...
    def materialize(self, owner_id: str, artifact_id: str, target: str | Path, *, overwrite: bool = False) -> Path: ...
    def status(self) -> dict[str, Any]: ...


class FilesystemIntelligenceVault:
    """Content-addressed immutable vault backend.

    This backend is production durable only when its root lives on a durable
    volume. Cloud/object-store implementations can satisfy the same protocol
    without changing restore-package semantics.
    """

    def __init__(self, root: str | Path, *, persistent: bool = False) -> None:
        self.root = Path(root).expanduser().resolve()
        self.objects = self.root / "objects"
        self.owners = self.root / "owners"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.owners.mkdir(parents=True, exist_ok=True)
        self.persistent = bool(persistent)

    def _record_path(self, owner_id: str, artifact_id: str) -> Path:
        return self.owners / _owner_namespace(owner_id) / "records" / _artifact_record_name(artifact_id)

    def _object_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid vault object digest")
        return self.objects / digest[:2] / digest

    @staticmethod
    def _safe_source(path: str | Path) -> Path:
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.is_symlink():
            raise ValueError("vault source must be a real regular file")
        return source

    def put(self, owner_id: str, artifact: RestoreArtifact, source: str | Path) -> VaultArtifactRecord:
        source_path = self._safe_source(source)
        digest, size = _sha256_file(source_path)
        if digest != artifact.sha256.lower():
            raise RuntimeError("vault source digest does not match restore artifact")
        if artifact.size_bytes is not None and int(artifact.size_bytes) != size:
            raise RuntimeError("vault source size does not match restore artifact")
        namespace = _owner_namespace(owner_id)
        object_path = self._object_path(digest)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if object_path.exists():
            if object_path.is_symlink() or not object_path.is_file():
                raise RuntimeError("vault object path is unsafe")
            existing_digest, existing_size = _sha256_file(object_path)
            if existing_digest != digest or existing_size != size:
                raise RuntimeError("immutable vault object was modified")
        else:
            staging = object_path.with_name(f".{object_path.name}.{uuid4().hex}.tmp")
            try:
                with source_path.open("rb") as src, staging.open("wb") as dst:
                    try:
                        os.chmod(staging, 0o600)
                    except OSError:
                        pass
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                copied_digest, copied_size = _sha256_file(staging)
                if copied_digest != digest or copied_size != size:
                    raise RuntimeError("vault object copy verification failed")
                try:
                    os.replace(staging, object_path)
                except FileExistsError:
                    pass
            finally:
                staging.unlink(missing_ok=True)

        canonical = RestoreArtifact(
            name=artifact.name,
            artifact_id=artifact.artifact_id,
            version=artifact.version,
            sha256=digest,
            locator=f"vault://sha256/{digest}",
            kind=artifact.kind,
            required=artifact.required,
            encrypted=artifact.encrypted,
            contains_private_data=artifact.contains_private_data,
            size_bytes=size,
        )
        record = VaultArtifactRecord(
            schema_version=1,
            owner_namespace=namespace,
            artifact=canonical,
            object_sha256=digest,
            object_size=size,
            created_at=_now(),
            immutable=True,
        )
        record_path = self._record_path(owner_id, artifact.artifact_id)
        if record_path.exists():
            existing = self.verify(owner_id, artifact.artifact_id)
            if existing.artifact.sha256 != canonical.sha256:
                raise RuntimeError("artifact id is already bound to different immutable content")
            return existing
        _atomic_json(record_path, record.public())
        return self.verify(owner_id, artifact.artifact_id)

    def verify(self, owner_id: str, artifact_id: str) -> VaultArtifactRecord:
        record_path = self._record_path(owner_id, artifact_id)
        if not record_path.is_file() or record_path.is_symlink():
            raise FileNotFoundError(artifact_id)
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("intelligence vault record is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("intelligence vault record is invalid")
        record = VaultArtifactRecord.from_dict(payload)
        expected_namespace = _owner_namespace(owner_id)
        if record.owner_namespace != expected_namespace:
            raise PermissionError("intelligence vault owner mismatch")
        if record.artifact.artifact_id != str(artifact_id):
            raise RuntimeError("intelligence vault artifact id mismatch")
        object_path = self._object_path(record.object_sha256)
        if not object_path.is_file() or object_path.is_symlink():
            raise RuntimeError("intelligence vault object is missing")
        digest, size = _sha256_file(object_path)
        if digest != record.object_sha256 or size != record.object_size:
            raise RuntimeError("intelligence vault object integrity failure")
        return record

    def materialize(
        self,
        owner_id: str,
        artifact_id: str,
        target: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        record = self.verify(owner_id, artifact_id)
        source = self._object_path(record.object_sha256)
        destination = Path(target).expanduser().resolve()
        if destination.exists() or destination.is_symlink():
            if not overwrite:
                raise FileExistsError(destination)
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("vault materialization target must be a regular file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with source.open("rb") as src, temporary.open("wb") as dst:
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            digest, size = _sha256_file(temporary)
            if digest != record.object_sha256 or size != record.object_size:
                raise RuntimeError("materialized vault artifact integrity failure")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def status(self) -> dict[str, Any]:
        return {
            "backend": "filesystem",
            "root": str(self.root),
            "persistent": self.persistent,
            "production_durable": self.persistent,
            "content_addressed": True,
            "immutable": True,
            "integrity": "sha256",
            "owner_namespace": "sha256",
        }
