from __future__ import annotations

import secrets
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.portable_intelligence import FilesystemIntelligenceManifestStore
from recovery.backup import BackupService

from .authority import HostContinuationAuthority
from .bundle import PortableContinuityBundleCodec
from .checkpoint import ContinuityCheckpointService
from .import_receipts import (
    ContinuityImportReceiptStore,
    ContinuityImportRecoveryRequired,
    IMPORT_RECEIPT_FILENAME,
    bundle_sha256,
)
from .models import ContinuityCheckpoint, TransferGrant
from .store import ContinuityAuthorityError, ContinuityStore
from .verifier import ContinuityCompatibilityVerifier


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContinuityExport:
    bundle_path: Path
    transfer_token: str
    checkpoint: ContinuityCheckpoint
    grant: TransferGrant

    def public_dict(self, *, include_transfer_token: bool = False) -> dict:
        data = {
            "bundle_path": str(self.bundle_path),
            "checkpoint": self.checkpoint.to_dict(),
            "grant": self.grant.public_dict(include_token=False),
            "source_fenced": True,
        }
        if include_transfer_token:
            data["transfer_token"] = self.transfer_token
        return data


class AgentContinuityService:
    """Cross-host continuation handoff over Vishnu's existing recovery system.

    Export may run on the live source, but it ends by fencing that host. Import is
    deliberately maintenance-only because the encrypted restore replaces durable
    databases and normal runtime connections must not remain open while that occurs.
    A target-local, non-restorable import receipt prevents blind replay after the
    restore boundary has been crossed.
    """

    def __init__(
        self,
        *,
        store: ContinuityStore,
        authority: HostContinuationAuthority,
        backups: BackupService,
        verifier: ContinuityCompatibilityVerifier,
        running_git_revision: str,
        checkpoint_service: ContinuityCheckpointService | None = None,
        codec: PortableContinuityBundleCodec | None = None,
        import_receipts: ContinuityImportReceiptStore | None = None,
        maintenance_mode: bool = False,
    ) -> None:
        self.store = store
        self.authority = authority
        self.backups = backups
        self.verifier = verifier
        self.running_git_revision = str(running_git_revision or "").strip()
        if not self.running_git_revision:
            raise ValueError("running_git_revision is required")
        self.checkpoint_service = checkpoint_service
        self.codec = codec or PortableContinuityBundleCodec()
        self.import_receipts = import_receipts or ContinuityImportReceiptStore(
            backups.data_dir / IMPORT_RECEIPT_FILENAME
        )
        self.maintenance_mode = bool(maintenance_mode)
        self._restart_required = False

    @property
    def restart_required(self) -> bool:
        return self._restart_required

    def bootstrap_or_resume(self):
        if self._restart_required:
            raise ContinuityAuthorityError("runtime restart is required after continuity import")
        return self.authority.bootstrap_or_resume()

    def assert_execution_authority(self):
        if self._restart_required:
            raise ContinuityAuthorityError("runtime restart is required after continuity import")
        return self.authority.assert_active()

    @staticmethod
    def _grant_from_header(header: dict, *, token: str) -> TransferGrant:
        data = dict(header.get("grant") or {})
        checkpoint = ContinuityCheckpoint.from_dict(dict(header.get("checkpoint") or {}))
        grant = TransferGrant(
            id=str(data["id"]),
            checkpoint_id=str(data["checkpoint_id"]),
            source_host_id=str(data["source_host_id"]),
            target_host_id=str(data["target_host_id"]),
            source_epoch=int(data["source_epoch"]),
            token=str(token),
            created_at=str(data["created_at"]),
            expires_at=str(data["expires_at"]),
        )
        if grant.checkpoint_id != checkpoint.id:
            raise ValueError("authenticated grant/checkpoint mismatch")
        if grant.source_host_id != checkpoint.source_host_id or grant.source_epoch != checkpoint.authority_epoch:
            raise ValueError("authenticated grant authority mismatch")
        return grant

    def export_to(
        self,
        *,
        target_host_id: str,
        bundle_path: str | Path,
        grant_ttl_seconds: int = 900,
    ) -> ContinuityExport:
        if self.checkpoint_service is None:
            raise RuntimeError("checkpoint service is unavailable on this host")
        target_host = str(target_host_id or "").strip()
        if not target_host or target_host == self.authority.host_id:
            raise ValueError("target_host_id must identify a different host")
        lease = self.authority.assert_active()
        artifact = self.checkpoint_service.create()
        self.checkpoint_service.verify_source_artifact(artifact)
        checkpoint = artifact.checkpoint
        if checkpoint.source_host_id != lease.host_id or checkpoint.authority_epoch != lease.epoch:
            raise ContinuityAuthorityError("checkpoint was not created under current authority")

        created = _now()
        grant = TransferGrant(
            id=f"ctg_{secrets.token_hex(16)}",
            checkpoint_id=checkpoint.id,
            source_host_id=lease.host_id,
            target_host_id=target_host,
            source_epoch=lease.epoch,
            token=secrets.token_urlsafe(48),
            created_at=_iso(created),
            expires_at=_iso(created + timedelta(seconds=max(60, int(grant_ttl_seconds)))),
        )
        self.store.prepare_transfer_grant(grant)

        payload = self.backups._decrypt_payload(artifact.backup_path)
        destination = Path(bundle_path).expanduser().resolve()
        try:
            manifest = self.backups._inspect_zip(payload, encrypted=True)
            self.verifier.verify_checkpoint(
                checkpoint,
                running_git_revision=self.running_git_revision,
            )
            self.verifier.verify_payload(checkpoint, payload=payload, manifest=manifest)
            self.codec.encrypt_payload(
                payload,
                destination,
                checkpoint=checkpoint,
                grant=grant,
            )
        finally:
            payload.unlink(missing_ok=True)

        try:
            # This is the irreversible handoff boundary: only after the fully
            # authenticated bundle exists do we disable the source's execution
            # authority. The transfer token is returned only after this succeeds.
            self.authority.fence_for_transfer(grant.id)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return ContinuityExport(destination, grant.token, checkpoint, grant)

    def validate_import(self, *, bundle_path: str | Path, transfer_token: str) -> dict:
        payload, header = self.codec.decrypt_payload(bundle_path, token=transfer_token)
        try:
            checkpoint = ContinuityCheckpoint.from_dict(dict(header["checkpoint"]))
            grant = self._grant_from_header(header, token=transfer_token)
            if grant.target_host_id != self.authority.host_id:
                raise ContinuityAuthorityError("continuity bundle targets another host")
            if datetime.fromisoformat(grant.expires_at).astimezone(timezone.utc) <= _now():
                raise ContinuityAuthorityError("continuity transfer grant expired")
            self.verifier.verify_checkpoint(
                checkpoint,
                running_git_revision=self.running_git_revision,
            )
            manifest = self.backups._inspect_zip(payload, encrypted=True)
            self.verifier.verify_payload(checkpoint, payload=payload, manifest=manifest)
            return {
                "checkpoint": checkpoint.to_dict(),
                "grant": grant.public_dict(include_token=False),
                "manifest_files": len(manifest.get("files") or ()),
                "target_host_id": self.authority.host_id,
                "valid": True,
            }
        finally:
            payload.unlink(missing_ok=True)

    @staticmethod
    def _verify_restored_body(data_dir: Path, checkpoint: ContinuityCheckpoint) -> None:
        revision_id = str(checkpoint.active_body_revision_id or "").strip()
        if not revision_id:
            return
        database = data_dir / "identity.sqlite3"
        if not database.is_file():
            raise RuntimeError("restored identity database is missing")
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT revision_id, git_revision, status FROM software_body_revisions WHERE revision_id=?",
                (revision_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("checkpoint Body revision is missing after restore")
        if str(row["git_revision"]) != str(checkpoint.active_body_git_revision):
            raise RuntimeError("restored Body revision does not match checkpoint")
        if str(row["status"]) != "active":
            raise RuntimeError("checkpoint Body revision is not active after restore")

    @staticmethod
    def _verify_restored_intelligence(data_dir: Path, checkpoint: ContinuityCheckpoint) -> None:
        binding = checkpoint.intelligence_binding()
        if not binding:
            return
        active_path = data_dir / "intelligence" / "active-manifest.json"
        if not active_path.is_file() or active_path.is_symlink():
            raise RuntimeError("restored active intelligence manifest is missing")
        store = FilesystemIntelligenceManifestStore(data_dir)
        active = store.active()
        if active is None:
            raise RuntimeError("restored active intelligence manifest is missing")
        if (
            active.manifest_id != checkpoint.intelligence_manifest_id
            or active.fingerprint != checkpoint.intelligence_manifest_fingerprint
        ):
            raise RuntimeError("restored intelligence manifest does not match checkpoint")

    def import_bundle(self, *, bundle_path: str | Path, transfer_token: str) -> dict:
        if not self.maintenance_mode:
            raise ContinuityAuthorityError(
                "continuity import requires a stopped runtime / maintenance process"
            )
        bundle = Path(bundle_path).expanduser().resolve()
        payload, header = self.codec.decrypt_payload(bundle, token=transfer_token)
        rewrapped_handle = tempfile.NamedTemporaryFile(
            prefix="vishnu-continuity-rewrapped-", suffix=".paibackup", delete=False
        )
        rewrapped = Path(rewrapped_handle.name)
        rewrapped_handle.close()
        claimed_grant_id: str | None = None
        try:
            checkpoint = ContinuityCheckpoint.from_dict(dict(header["checkpoint"]))
            grant = self._grant_from_header(header, token=transfer_token)
            if grant.target_host_id != self.authority.host_id:
                raise ContinuityAuthorityError("continuity bundle targets another host")
            if datetime.fromisoformat(grant.expires_at).astimezone(timezone.utc) <= _now():
                raise ContinuityAuthorityError("continuity transfer grant expired")
            self.verifier.verify_checkpoint(
                checkpoint,
                running_git_revision=self.running_git_revision,
            )
            manifest = self.backups._inspect_zip(payload, encrypted=True)
            self.verifier.verify_payload(checkpoint, payload=payload, manifest=manifest)

            # Cross-host import is a first-device handoff. Refuse an already
            # initialized target before claiming the one-time receipt or writing
            # any restored files; the owner must explicitly prepare that host.
            if self.import_receipts.get(grant.id) is not None:
                # Preserve the explicit replay/recovery classification even
                # though a completed import now has an active target authority.
                self.import_receipts.claim(
                    grant_id=grant.id,
                    checkpoint_id=checkpoint.id,
                    bundle_hash=bundle_sha256(bundle),
                )
            if self.store.current_authority() is not None:
                raise ContinuityAuthorityError(
                    "target continuation authority already exists; explicitly prepare this host before restoring"
                )

            # Rewrap the authenticated portable payload with the target host's
            # owner root key. The source root key never crosses the boundary.
            self.backups._encrypt_payload(payload, rewrapped)

            # Claim the destructive boundary in a target-local ledger that the
            # source checkpoint cannot overwrite. After this point any failure is
            # an uncertain import and requires explicit recovery, never replay.
            self.import_receipts.claim(
                grant_id=grant.id,
                checkpoint_id=checkpoint.id,
                bundle_hash=bundle_sha256(bundle),
            )
            claimed_grant_id = grant.id
            try:
                restore = self.backups.restore(rewrapped)
                self._verify_restored_intelligence(self.backups.data_dir, checkpoint)

                # The source snapshot intentionally predates checkpoint/grant rows
                # to avoid circular checkpoint hashes. Recreate those records from
                # the authenticated outer header, then consume the one-time grant.
                self.store.record_checkpoint(checkpoint)
                self.store.prepare_transfer_grant(grant)
                self.store.stage_import_authority(checkpoint=checkpoint)
                next_epoch = grant.source_epoch + 1
                target_token = self.authority.target_token(next_epoch)
                lease = self.store.consume_transfer(
                    grant_id=grant.id,
                    grant_token=transfer_token,
                    target_host_id=self.authority.host_id,
                    target_authority_token=target_token,
                    ttl_seconds=self.authority.ttl_seconds,
                )
                self._verify_restored_body(self.backups.data_dir, checkpoint)
                self.store.mark_checkpoint_verified(
                    checkpoint.id,
                    host_id=self.authority.host_id,
                    epoch=lease.epoch,
                )
                self.import_receipts.mark_completed(grant.id)
            except Exception as exc:
                self.import_receipts.mark_recovery_required(
                    grant.id,
                    error_type=type(exc).__name__,
                )
                raise

            self._restart_required = True
            return {
                "ok": True,
                "checkpoint_id": checkpoint.id,
                "authority_epoch": lease.epoch,
                "host_id": lease.host_id,
                "restored": int(restore.get("restored", 0)),
                "skipped_security_state": list(restore.get("skipped_security_state") or ()),
                "credentials_rebind_required": True,
                "restart_required": True,
            }
        except ContinuityImportRecoveryRequired:
            raise
        finally:
            payload.unlink(missing_ok=True)
            rewrapped.unlink(missing_ok=True)
