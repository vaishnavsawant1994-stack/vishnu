from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from models.portable_intelligence import IntelligenceManifest


_RESTORE_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _valid_sha256(value: str) -> bool:
    digest = value.strip().lower()
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


class RestoreArtifactKind(str, Enum):
    MODEL = "model"
    ADAPTER = "adapter"
    DATABASE = "database"
    KNOWLEDGE = "knowledge"
    AGENT = "agent"
    SKILL = "skill"
    WORKFLOW = "workflow"
    INDEX = "index"
    OTHER = "other"


@dataclass(frozen=True)
class RestoreArtifact:
    """Reference to one immutable artifact needed to reconstruct Vishnu.

    The restore manifest stores references only. It must never embed model bytes,
    private databases, user documents, API keys, credentials, or signed URLs.
    Private-state artifacts must be encrypted before they are referenced here.
    """

    name: str
    artifact_id: str
    version: str
    sha256: str
    locator: str
    kind: RestoreArtifactKind = RestoreArtifactKind.OTHER
    required: bool = True
    encrypted: bool = False
    contains_private_data: bool = False
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("restore artifact name is required")
        if not self.artifact_id.strip():
            raise ValueError("restore artifact id is required")
        if not self.version.strip():
            raise ValueError("restore artifact version is required")
        if not _valid_sha256(self.sha256):
            raise ValueError("restore artifact sha256 must be a 64-character hexadecimal digest")
        if not self.locator.strip():
            raise ValueError("restore artifact locator is required")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("restore artifact size_bytes cannot be negative")
        if self.contains_private_data and not self.encrypted:
            raise ValueError("private restore artifacts must be encrypted")
        self._validate_locator()

    def _validate_locator(self) -> None:
        locator = self.locator.strip()
        parsed = urlsplit(locator)
        # Restore metadata is durable and may be exported. Persisting a signed
        # URL, userinfo, query token, or fragment could turn the manifest into a
        # credential leak, so locators must be stable credential-free references.
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("restore artifact locator must not contain credentials, query parameters, or fragments")
        lowered = locator.lower()
        if any(marker in lowered for marker in ("token=", "api_key=", "apikey=", "secret=", "signature=")):
            raise ValueError("restore artifact locator must not contain credential material")

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "sha256": self.sha256.lower(),
            "locator": self.locator,
            "kind": self.kind.value,
            "required": self.required,
            "encrypted": self.encrypted,
            "contains_private_data": self.contains_private_data,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RestoreArtifact":
        try:
            kind = RestoreArtifactKind(str(payload.get("kind") or RestoreArtifactKind.OTHER.value))
        except ValueError as exc:
            raise ValueError("unsupported restore artifact kind") from exc
        size = payload.get("size_bytes")
        return cls(
            name=str(payload.get("name") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            version=str(payload.get("version") or ""),
            sha256=str(payload.get("sha256") or ""),
            locator=str(payload.get("locator") or ""),
            kind=kind,
            required=bool(payload.get("required", True)),
            encrypted=bool(payload.get("encrypted", False)),
            contains_private_data=bool(payload.get("contains_private_data", False)),
            size_bytes=int(size) if size is not None else None,
        )


@dataclass(frozen=True)
class IntelligenceRestorePackage:
    """Tamper-evident reconstruction package for a qualified Vishnu manifest."""

    schema_version: int
    package_id: str
    fingerprint: str
    created_at: str
    owner_id: str
    manifest: IntelligenceManifest
    artifacts: tuple[RestoreArtifact, ...]

    @staticmethod
    def _artifacts(values: Iterable[RestoreArtifact]) -> tuple[RestoreArtifact, ...]:
        artifacts = tuple(values)
        names = [item.name for item in artifacts]
        ids = [item.artifact_id for item in artifacts]
        if len(names) != len(set(names)):
            raise ValueError("restore artifact names must be unique")
        if len(ids) != len(set(ids)):
            raise ValueError("restore artifact ids must be unique")
        return tuple(sorted(artifacts, key=lambda item: (item.kind.value, item.name, item.version, item.artifact_id)))

    @classmethod
    def create(
        cls,
        *,
        manifest: IntelligenceManifest,
        artifacts: Iterable[RestoreArtifact] = (),
        owner_id: str | None = None,
        created_at: str | None = None,
    ) -> "IntelligenceRestorePackage":
        manifest.verify()
        owner = str(owner_id or manifest.owner_id)
        if not owner.strip():
            raise ValueError("restore package owner_id is required")
        if owner != manifest.owner_id:
            raise ValueError("restore package owner must match intelligence manifest owner")
        normalized = cls._artifacts(artifacts)
        timestamp = str(created_at or _now())
        unsigned = {
            "schema_version": _RESTORE_SCHEMA_VERSION,
            "created_at": timestamp,
            "owner_id": owner,
            "manifest": manifest.public(),
            "artifacts": [item.public() for item in normalized],
        }
        fingerprint = sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
        return cls(
            schema_version=_RESTORE_SCHEMA_VERSION,
            package_id=f"virp-{fingerprint[:24]}",
            fingerprint=fingerprint,
            created_at=timestamp,
            owner_id=owner,
            manifest=manifest,
            artifacts=normalized,
        )

    def unsigned(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "owner_id": self.owner_id,
            "manifest": self.manifest.public(),
            "artifacts": [item.public() for item in self._artifacts(self.artifacts)],
        }

    def verify(self) -> None:
        if self.schema_version != _RESTORE_SCHEMA_VERSION:
            raise ValueError("unsupported intelligence restore package schema")
        self.manifest.verify()
        if self.owner_id != self.manifest.owner_id:
            raise RuntimeError("restore package owner mismatch")
        expected = sha256(_canonical_json(self.unsigned()).encode("utf-8")).hexdigest()
        if expected != self.fingerprint:
            raise RuntimeError("intelligence restore package fingerprint mismatch")
        if self.package_id != f"virp-{expected[:24]}":
            raise RuntimeError("intelligence restore package id mismatch")

    def public(self) -> dict[str, Any]:
        self.verify()
        payload = self.unsigned()
        payload.update({"package_id": self.package_id, "fingerprint": self.fingerprint})
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntelligenceRestorePackage":
        if int(payload.get("schema_version", 0)) != _RESTORE_SCHEMA_VERSION:
            raise ValueError("unsupported intelligence restore package schema")
        raw_manifest = payload.get("manifest")
        if not isinstance(raw_manifest, Mapping):
            raise ValueError("restore package manifest must be an object")
        raw_artifacts = payload.get("artifacts") or ()
        if not isinstance(raw_artifacts, (list, tuple)):
            raise ValueError("restore package artifacts must be a list")
        package = cls(
            schema_version=_RESTORE_SCHEMA_VERSION,
            package_id=str(payload.get("package_id") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            created_at=str(payload.get("created_at") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            manifest=IntelligenceManifest.from_dict(raw_manifest),
            artifacts=cls._artifacts(RestoreArtifact.from_dict(dict(item)) for item in raw_artifacts),
        )
        package.verify()
        return package


class RestoreAction(str, Enum):
    REUSE = "reuse"
    FETCH = "fetch"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RestorePlanItem:
    artifact: RestoreArtifact
    action: RestoreAction
    reason: str


@dataclass(frozen=True)
class RestorePreflight:
    package_id: str
    manifest_id: str
    owner_id: str
    ready: bool
    items: tuple[RestorePlanItem, ...]
    blocked_required: tuple[str, ...]
    fetch_bytes: int

    def require_ready(self) -> None:
        if not self.ready:
            blocked = ", ".join(self.blocked_required) or "unknown"
            raise RuntimeError(f"restore preflight blocked: {blocked}")


def build_restore_preflight(
    package: IntelligenceRestorePackage,
    local_artifacts: Mapping[str, str] | None = None,
    *,
    online: bool,
    allow_fetch: bool = True,
    expected_owner_id: str | None = None,
) -> RestorePreflight:
    """Plan restoration without mutating local state.

    `local_artifacts` maps immutable artifact IDs to their observed SHA-256.
    Matching artifacts are reused. Missing or corrupted artifacts may be fetched
    only when network and policy allow it. Required unavailable artifacts block
    the restore, which prevents a fresh installation from silently booting an
    incomplete intelligence state.
    """

    package.verify()
    if expected_owner_id is not None and str(expected_owner_id) != package.owner_id:
        raise PermissionError("restore package does not belong to expected owner")

    local = {str(key): str(value).lower() for key, value in dict(local_artifacts or {}).items()}
    items: list[RestorePlanItem] = []
    blocked: list[str] = []
    fetch_bytes = 0

    for artifact in package.artifacts:
        observed = local.get(artifact.artifact_id)
        if observed == artifact.sha256.lower():
            action = RestoreAction.REUSE
            reason = "verified_local_copy"
        elif online and allow_fetch:
            action = RestoreAction.FETCH
            reason = "local_hash_mismatch" if observed else "missing_local_copy"
            if artifact.size_bytes is not None:
                fetch_bytes += artifact.size_bytes
        else:
            action = RestoreAction.BLOCKED
            if observed:
                reason = "local_hash_mismatch_fetch_unavailable"
            elif not online:
                reason = "missing_local_copy_offline"
            else:
                reason = "missing_local_copy_fetch_disabled"
            if artifact.required:
                blocked.append(artifact.artifact_id)
        items.append(RestorePlanItem(artifact=artifact, action=action, reason=reason))

    return RestorePreflight(
        package_id=package.package_id,
        manifest_id=package.manifest.manifest_id,
        owner_id=package.owner_id,
        ready=not blocked,
        items=tuple(items),
        blocked_required=tuple(sorted(blocked)),
        fetch_bytes=fetch_bytes,
    )
