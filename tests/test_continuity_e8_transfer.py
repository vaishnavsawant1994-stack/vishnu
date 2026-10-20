from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from continuity import (
    AgentContinuityService,
    ContinuityAuthorityError,
    ContinuityCheckpointService,
    ContinuityCompatibilityError,
    ContinuityCompatibilityVerifier,
    ContinuityStore,
    HostContinuationAuthority,
)
from continuity.import_receipts import (
    ContinuityImportRecoveryRequired,
    IMPORT_RECEIPT_FILENAME,
)
from identity import BodyManifest, BodyRevisionStatus, IdentityStore
from recovery.backup import BackupService, NON_RESTORABLE_SECURITY_NAMES


REVISION = "0123456789abcdef0123456789abcdef01234567"


class FixedKeyStore:
    def __init__(self, byte: bytes):
        self.key = byte * 32

    def get_or_create(self):
        return self.key


def _simple_db(path: Path, table: str, value: str):
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE {table}(value TEXT NOT NULL)")
        connection.execute(f"INSERT INTO {table}(value) VALUES (?)", (value,))


def _read_value(path: Path, table: str) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute(f"SELECT value FROM {table}").fetchone()[0])


def _source_export(tmp_path: Path, *, target_host: str):
    source_dir = tmp_path / f"source-{target_host}"
    source_dir.mkdir()
    _simple_db(source_dir / "assistant.sqlite3", "memory_rows", "source-memory")
    _simple_db(source_dir / "devices.sqlite3", "security_rows", "source-security")

    source_keys = FixedKeyStore(b"S")
    source_backups = BackupService(source_dir, root_key_store=source_keys)
    source_store = ContinuityStore(source_dir / "agent-continuity.sqlite3")
    source_authority = HostContinuationAuthority(
        source_store,
        host_id="source-host",
        root_key_store=source_keys,
    )
    source_authority.bootstrap_or_resume()

    identity = IdentityStore(source_dir / "identity.sqlite3")
    manifest = BodyManifest.from_dict(
        {
            "body_version": 1,
            "identity": {"name": "Vishnu", "role": "personal_ai"},
            "contracts": {"work": 1, "evidence": 1, "evolution": 1, "continuity": 1},
            "mission": ["preserve governed continuity"],
            "principles": ["owner authority remains external"],
        }
    )
    revision_id = identity.record_body_revision(
        manifest,
        git_revision=REVISION,
        status=BodyRevisionStatus.CANDIDATE,
    )
    identity.activate_body_revision(revision_id, actor="test-owner")

    verifier = ContinuityCompatibilityVerifier(
        ContinuityCheckpointService.supported_schema_versions()
    )
    checkpoints = ContinuityCheckpointService(
        store=source_store,
        authority=source_authority,
        backups=source_backups,
        identity_store=identity,
        running_git_revision=REVISION,
    )
    service = AgentContinuityService(
        store=source_store,
        authority=source_authority,
        backups=source_backups,
        verifier=verifier,
        running_git_revision=REVISION,
        checkpoint_service=checkpoints,
    )
    bundle = tmp_path / f"{target_host}.vcontinuity"
    exported = service.export_to(target_host_id=target_host, bundle_path=bundle)
    identity.close()
    return source_dir, source_authority, exported, verifier


def _target_service(target_dir: Path, *, host_id: str, verifier, key_byte: bytes = b"T"):
    target_dir.mkdir(exist_ok=True)
    keys = FixedKeyStore(key_byte)
    backups = BackupService(target_dir, root_key_store=keys)
    store = ContinuityStore(target_dir / "agent-continuity.sqlite3")
    authority = HostContinuationAuthority(
        store,
        host_id=host_id,
        root_key_store=keys,
    )
    service = AgentContinuityService(
        store=store,
        authority=authority,
        backups=backups,
        verifier=verifier,
        running_git_revision=REVISION,
        maintenance_mode=True,
    )
    return service, authority


def test_cross_host_transfer_uses_different_root_keys_and_preserves_target_security(tmp_path):
    source_dir, source_authority, exported, verifier = _source_export(
        tmp_path, target_host="target-host"
    )
    with pytest.raises(ContinuityAuthorityError):
        source_authority.assert_active()

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    _simple_db(target_dir / "devices.sqlite3", "security_rows", "target-security")
    target_service, target_authority = _target_service(
        target_dir, host_id="target-host", verifier=verifier
    )

    validation = target_service.validate_import(
        bundle_path=exported.bundle_path,
        transfer_token=exported.transfer_token,
    )
    assert validation["valid"] is True
    result = target_service.import_bundle(
        bundle_path=exported.bundle_path,
        transfer_token=exported.transfer_token,
    )
    assert result["ok"] is True
    assert result["authority_epoch"] == 2
    assert result["credentials_rebind_required"] is True
    assert result["restart_required"] is True
    assert "devices.sqlite3" in result["skipped_security_state"]
    assert "agent-continuity.sqlite3" in result["skipped_security_state"]
    assert IMPORT_RECEIPT_FILENAME in NON_RESTORABLE_SECURITY_NAMES
    assert "agent-continuity.sqlite3" in NON_RESTORABLE_SECURITY_NAMES

    assert _read_value(target_dir / "assistant.sqlite3", "memory_rows") == "source-memory"
    assert _read_value(target_dir / "devices.sqlite3", "security_rows") == "target-security"
    assert target_authority.assert_active().epoch == 2
    with sqlite3.connect(target_dir / IMPORT_RECEIPT_FILENAME) as connection:
        receipt = connection.execute(
            "SELECT status FROM continuity_import_receipts WHERE grant_id=?",
            (exported.grant.id,),
        ).fetchone()
    assert receipt == ("completed",)

    # A successful bundle cannot rewind target data on replay.
    with sqlite3.connect(target_dir / "assistant.sqlite3") as connection:
        connection.execute("UPDATE memory_rows SET value='post-import-change'")
    with pytest.raises(ContinuityImportRecoveryRequired):
        target_service.import_bundle(
            bundle_path=exported.bundle_path,
            transfer_token=exported.transfer_token,
        )
    assert _read_value(target_dir / "assistant.sqlite3", "memory_rows") == "post-import-change"

    # Source and target root keys are intentionally different; successful import
    # therefore proves the source root key did not have to cross the boundary.
    assert source_dir != target_dir


def test_target_body_mismatch_fails_before_restore(tmp_path):
    _source_dir, _source_authority, exported, verifier = _source_export(
        tmp_path, target_host="target-mismatch"
    )
    target_dir = tmp_path / "target-mismatch-dir"
    target_dir.mkdir()
    _simple_db(target_dir / "assistant.sqlite3", "memory_rows", "target-original")
    keys = FixedKeyStore(b"M")
    backups = BackupService(target_dir, root_key_store=keys)
    store = ContinuityStore(target_dir / "agent-continuity.sqlite3")
    authority = HostContinuationAuthority(
        store,
        host_id="target-mismatch",
        root_key_store=keys,
    )
    service = AgentContinuityService(
        store=store,
        authority=authority,
        backups=backups,
        verifier=verifier,
        running_git_revision="f" * 40,
        maintenance_mode=True,
    )
    with pytest.raises(ContinuityCompatibilityError, match="Body revision"):
        service.import_bundle(
            bundle_path=exported.bundle_path,
            transfer_token=exported.transfer_token,
        )
    assert _read_value(target_dir / "assistant.sqlite3", "memory_rows") == "target-original"


def test_import_refuses_initialized_target_before_restoring_any_data(tmp_path):
    _source_dir, _source_authority, exported, verifier = _source_export(
        tmp_path, target_host="target-already-initialized"
    )
    target_dir = tmp_path / "target-already-initialized-dir"
    target_dir.mkdir()
    _simple_db(target_dir / "assistant.sqlite3", "memory_rows", "target-original")
    target_service, target_authority = _target_service(
        target_dir, host_id="target-already-initialized", verifier=verifier
    )
    target_authority.bootstrap_or_resume()

    with pytest.raises(ContinuityAuthorityError, match="target continuation authority already exists"):
        target_service.import_bundle(
            bundle_path=exported.bundle_path,
            transfer_token=exported.transfer_token,
        )

    assert _read_value(target_dir / "assistant.sqlite3", "memory_rows") == "target-original"
    assert target_service.import_receipts.get(exported.grant.id) is None


def test_failure_after_restore_boundary_requires_manual_recovery_not_replay(tmp_path, monkeypatch):
    _source_dir, _source_authority, exported, verifier = _source_export(
        tmp_path, target_host="target-failure"
    )
    target_dir = tmp_path / "target-failure-dir"
    target_service, _target_authority = _target_service(
        target_dir, host_id="target-failure", verifier=verifier, key_byte=b"F"
    )

    original_restore = target_service.backups.restore

    def fail_restore(_archive):
        raise RuntimeError("simulated restore interruption")

    monkeypatch.setattr(target_service.backups, "restore", fail_restore)
    with pytest.raises(RuntimeError, match="simulated restore interruption"):
        target_service.import_bundle(
            bundle_path=exported.bundle_path,
            transfer_token=exported.transfer_token,
        )
    receipt = target_service.import_receipts.get(exported.grant.id)
    assert receipt is not None
    assert receipt["status"] == "recovery_required"

    monkeypatch.setattr(target_service.backups, "restore", original_restore)
    with pytest.raises(ContinuityImportRecoveryRequired, match="manual recovery"):
        target_service.import_bundle(
            bundle_path=exported.bundle_path,
            transfer_token=exported.transfer_token,
        )
