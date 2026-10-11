from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import zipfile

from evidence.migrations import EVIDENCE_SCHEMA_VERSION
from evolution.migrations import EVOLUTION_SCHEMA_VERSION
from future_intelligence.work_orchestration.durability_migrations import WORK_DURABILITY_SCHEMA_VERSION
from identity.migrations import IDENTITY_SCHEMA_VERSION
from identity.store import IdentityStore
from models.portable_intelligence import IntelligenceManifest
from recovery.backup import BackupService

from .authority import HostContinuationAuthority
from .migrations import AGENT_CONTINUITY_SCHEMA_VERSION
from .models import ContinuityCheckpoint
from .store import ContinuityStore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_hash(manifest: dict) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _snapshot_intelligence_manifest(payload: Path) -> IntelligenceManifest | None:
    """Read the active intelligence manifest from the already-authenticated snapshot.

    Binding the checkpoint to the snapshot rather than to the live data directory
    prevents a concurrent manifest activation from creating a checkpoint that
    describes state different from the bytes actually being transported.
    """

    active_name = "intelligence/active-manifest.json"
    with zipfile.ZipFile(payload) as archive:
        names = set(archive.namelist())
        if active_name not in names:
            return None
        try:
            pointer = json.loads(archive.read(active_name))
        except Exception as exc:
            raise ValueError("snapshot active intelligence manifest pointer is unreadable") from exc
        if not isinstance(pointer, dict):
            raise ValueError("snapshot active intelligence manifest pointer must be an object")
        manifest_id = str(pointer.get("manifest_id") or "")
        fingerprint = str(pointer.get("fingerprint") or "").lower()
        if not manifest_id:
            raise ValueError("snapshot active intelligence manifest id is missing")
        manifest_name = f"intelligence/manifests/{manifest_id}.json"
        if manifest_name not in names:
            raise ValueError("snapshot active intelligence manifest is missing")
        try:
            manifest_payload = json.loads(archive.read(manifest_name))
        except Exception as exc:
            raise ValueError("snapshot active intelligence manifest is unreadable") from exc
        if not isinstance(manifest_payload, dict):
            raise ValueError("snapshot active intelligence manifest must be an object")
        manifest = IntelligenceManifest.from_dict(manifest_payload)
        if manifest.manifest_id != manifest_id or manifest.fingerprint != fingerprint:
            raise RuntimeError("snapshot active intelligence manifest pointer mismatch")
        return manifest


@dataclass(frozen=True)
class CheckpointArtifact:
    checkpoint: ContinuityCheckpoint
    backup_path: Path


class ContinuityCheckpointService:
    """Creates immutable checkpoint metadata over the existing encrypted backup system."""

    def __init__(
        self,
        *,
        store: ContinuityStore,
        authority: HostContinuationAuthority,
        backups: BackupService,
        identity_store: IdentityStore,
        running_git_revision: str,
    ) -> None:
        self.store = store
        self.authority = authority
        self.backups = backups
        self.identity_store = identity_store
        self.running_git_revision = str(running_git_revision or "").strip()
        if not self.running_git_revision:
            raise ValueError("running_git_revision is required for cross-host continuity")

    @staticmethod
    def supported_schema_versions() -> dict[str, tuple[int, ...]]:
        return {
            "identity": (IDENTITY_SCHEMA_VERSION,),
            "evidence": (EVIDENCE_SCHEMA_VERSION,),
            "evolution": (EVOLUTION_SCHEMA_VERSION,),
            "work": (WORK_DURABILITY_SCHEMA_VERSION,),
            "agent_continuity": (AGENT_CONTINUITY_SCHEMA_VERSION,),
        }

    def create(self) -> CheckpointArtifact:
        lease = self.authority.assert_active()
        active_body = self.identity_store.active_body_revision()
        if active_body is not None and str(active_body["git_revision"]) != self.running_git_revision:
            raise RuntimeError("running revision does not match the active Body revision")

        checkpoint_id = f"ccp_{uuid4().hex}"
        backup = self.backups.create(f"continuity-{checkpoint_id}.paibackup")
        manifest = self.backups.inspect(backup)
        payload = self.backups._decrypt_payload(backup)
        try:
            payload_sha = _sha256(payload)
            intelligence_manifest = _snapshot_intelligence_manifest(payload)
        finally:
            payload.unlink(missing_ok=True)

        files = tuple(manifest.get("files") or ())
        total_bytes = sum(int(item.get("size", 0)) for item in files if isinstance(item, dict))
        checkpoint = ContinuityCheckpoint(
            id=checkpoint_id,
            source_host_id=lease.host_id,
            authority_epoch=lease.epoch,
            backup_filename=backup.name,
            backup_sha256=_sha256(backup),
            backup_size=backup.stat().st_size,
            payload_sha256=payload_sha,
            data_manifest_hash=_manifest_hash(manifest),
            active_body_revision_id=(str(active_body["revision_id"]) if active_body else None),
            active_body_git_revision=self.running_git_revision,
            intelligence_manifest_id=(intelligence_manifest.manifest_id if intelligence_manifest else ""),
            intelligence_manifest_fingerprint=(
                intelligence_manifest.fingerprint if intelligence_manifest else ""
            ),
            schema_versions=self.supported_schema_versions(),
            state_summary={
                "file_count": len(files),
                "snapshot_bytes": total_bytes,
                "backup_encrypted": bool(manifest.get("encrypted")),
                "credentials_rebind_required": True,
                "security_authority_restored": False,
                "intelligence_manifest_bound": intelligence_manifest is not None,
            },
        )
        self.store.record_checkpoint(checkpoint)
        return CheckpointArtifact(checkpoint=checkpoint, backup_path=backup)

    def verify_source_artifact(self, artifact: CheckpointArtifact) -> dict:
        checkpoint = artifact.checkpoint
        backup = Path(artifact.backup_path)
        if not backup.is_file():
            raise FileNotFoundError(backup)
        if backup.name != checkpoint.backup_filename:
            raise ValueError("checkpoint backup filename mismatch")
        if backup.stat().st_size != checkpoint.backup_size:
            raise ValueError("checkpoint backup size mismatch")
        if _sha256(backup) != checkpoint.backup_sha256:
            raise ValueError("checkpoint backup digest mismatch")
        manifest = self.backups.inspect(backup)
        if _manifest_hash(manifest) != checkpoint.data_manifest_hash:
            raise ValueError("checkpoint data manifest mismatch")
        payload = self.backups._decrypt_payload(backup)
        try:
            if _sha256(payload) != checkpoint.payload_sha256:
                raise ValueError("checkpoint portable payload digest mismatch")
            snapshot_manifest = _snapshot_intelligence_manifest(payload)
            binding = checkpoint.intelligence_binding()
            if not binding:
                if snapshot_manifest is not None:
                    raise ValueError("checkpoint is missing snapshot intelligence manifest binding")
            elif snapshot_manifest is None:
                raise ValueError("checkpoint-bound intelligence manifest is missing from snapshot")
            elif (
                snapshot_manifest.manifest_id != checkpoint.intelligence_manifest_id
                or snapshot_manifest.fingerprint != checkpoint.intelligence_manifest_fingerprint
            ):
                raise ValueError("checkpoint intelligence manifest does not match snapshot")
        finally:
            payload.unlink(missing_ok=True)
        return manifest
