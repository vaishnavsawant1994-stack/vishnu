from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _validated_intelligence_binding(manifest_id: str, fingerprint: str) -> dict[str, str]:
    manifest_id = str(manifest_id or "").strip()
    fingerprint = str(fingerprint or "").strip().lower()
    if bool(manifest_id) != bool(fingerprint):
        raise ValueError("intelligence manifest id and fingerprint must be supplied together")
    if not manifest_id:
        return {}
    if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
        raise ValueError("intelligence manifest fingerprint must be a 64-character hexadecimal digest")
    expected_id = f"vim-{fingerprint[:24]}"
    if manifest_id != expected_id:
        raise ValueError("intelligence manifest id does not match its fingerprint")
    return {
        "intelligence_manifest_id": manifest_id,
        "intelligence_manifest_fingerprint": fingerprint,
    }


class AuthorityStatus(StrEnum):
    ACTIVE = "active"
    FENCED = "fenced"


class TransferGrantStatus(StrEnum):
    PREPARED = "prepared"
    CONSUMED = "consumed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CheckpointStatus(StrEnum):
    CREATED = "created"
    EXPORTED = "exported"
    RESTORED = "restored"
    VERIFIED = "verified"


@dataclass(frozen=True)
class AuthorityLease:
    host_id: str
    epoch: int
    token: str
    acquired_at: str
    expires_at: str
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class TransferGrant:
    id: str
    checkpoint_id: str
    source_host_id: str
    target_host_id: str
    source_epoch: int
    token: str
    created_at: str
    expires_at: str

    @property
    def token_hash(self) -> str:
        return hashlib.sha256(self.token.encode("utf-8")).hexdigest()

    def public_dict(self, *, include_token: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "checkpoint_id": self.checkpoint_id,
            "source_host_id": self.source_host_id,
            "target_host_id": self.target_host_id,
            "source_epoch": self.source_epoch,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if include_token:
            data["token"] = self.token
        return data


@dataclass(frozen=True)
class ContinuityCheckpoint:
    id: str
    source_host_id: str
    authority_epoch: int
    backup_filename: str
    backup_sha256: str
    backup_size: int
    payload_sha256: str
    data_manifest_hash: str
    active_body_revision_id: str | None
    active_body_git_revision: str | None
    intelligence_manifest_id: str = ""
    intelligence_manifest_fingerprint: str = ""
    schema_versions: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    state_summary: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def intelligence_binding(self) -> dict[str, str]:
        return _validated_intelligence_binding(
            self.intelligence_manifest_id,
            self.intelligence_manifest_fingerprint,
        )

    @property
    def checkpoint_hash(self) -> str:
        payload = {
            "id": self.id,
            "source_host_id": self.source_host_id,
            "authority_epoch": self.authority_epoch,
            "backup_filename": self.backup_filename,
            "backup_sha256": self.backup_sha256,
            "backup_size": self.backup_size,
            "payload_sha256": self.payload_sha256,
            "data_manifest_hash": self.data_manifest_hash,
            "active_body_revision_id": self.active_body_revision_id,
            "active_body_git_revision": self.active_body_git_revision,
            "schema_versions": {key: list(value) for key, value in sorted(self.schema_versions.items())},
            "state_summary": dict(self.state_summary),
            "created_at": self.created_at,
        }
        payload.update(self.intelligence_binding())
        return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "source_host_id": self.source_host_id,
            "authority_epoch": self.authority_epoch,
            "backup_filename": self.backup_filename,
            "backup_sha256": self.backup_sha256,
            "backup_size": self.backup_size,
            "payload_sha256": self.payload_sha256,
            "data_manifest_hash": self.data_manifest_hash,
            "active_body_revision_id": self.active_body_revision_id,
            "active_body_git_revision": self.active_body_git_revision,
            "schema_versions": {key: list(value) for key, value in self.schema_versions.items()},
            "state_summary": dict(self.state_summary),
            "created_at": self.created_at,
        }
        data.update(self.intelligence_binding())
        data["checkpoint_hash"] = self.checkpoint_hash
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContinuityCheckpoint":
        checkpoint = cls(
            id=str(data["id"]),
            source_host_id=str(data["source_host_id"]),
            authority_epoch=int(data["authority_epoch"]),
            backup_filename=str(data["backup_filename"]),
            backup_sha256=str(data["backup_sha256"]),
            backup_size=int(data["backup_size"]),
            payload_sha256=str(data["payload_sha256"]),
            data_manifest_hash=str(data["data_manifest_hash"]),
            active_body_revision_id=data.get("active_body_revision_id"),
            active_body_git_revision=data.get("active_body_git_revision"),
            intelligence_manifest_id=str(data.get("intelligence_manifest_id") or ""),
            intelligence_manifest_fingerprint=str(data.get("intelligence_manifest_fingerprint") or ""),
            schema_versions={
                str(key): tuple(int(version) for version in value)
                for key, value in dict(data.get("schema_versions") or {}).items()
            },
            state_summary=dict(data.get("state_summary") or {}),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )
        supplied = str(data.get("checkpoint_hash") or "")
        if supplied and supplied != checkpoint.checkpoint_hash:
            raise ValueError("checkpoint hash mismatch")
        return checkpoint
