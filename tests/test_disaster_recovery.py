from __future__ import annotations

import sqlite3

import pytest

from recovery.backup import BackupService
from recovery.disaster_recovery import (
    DisasterRecoveryError,
    DisasterRecoveryService,
    decrypt_recovery_key_file,
    encrypt_recovery_key_file,
    generate_recovery_key,
)
from security.owner_access import OwnerAccessStore


class _FixedRootKeyStore:
    def __init__(self, key: bytes):
        self.key = key

    def get_or_create(self) -> bytes:
        return self.key


def _sqlite(path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES(?)", (value,))
        connection.commit()


def _read_sqlite(path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM sample").fetchone()
    assert row is not None
    return str(row[0])


def test_disaster_recovery_restores_on_new_host_with_different_root_key(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    source_owner = OwnerAccessStore(source / 'owner-access.sqlite3')
    owner_identity, _ = source_owner.initialize_identity(first_name='Asha', last_name='Patel')
    source_owner.set_password('correct horse battery staple')
    source_owner.regenerate_recovery_codes()
    _sqlite(source / "memory.sqlite3", "same-vishnu-memory")
    _sqlite(source / "devices.sqlite3", "old-security-authority")
    (source / "notes.txt").write_text("portable owner state", encoding="utf-8")
    (source / ".env").write_text("SECRET_SHOULD_NOT_LEAVE_SOURCE=1", encoding="utf-8")

    source_backups = BackupService(source, root_key_store=_FixedRootKeyStore(b"s" * 32))
    source_service = DisasterRecoveryService(source_backups)
    recovery_key = generate_recovery_key()
    bundle = tmp_path / "owner-recovery.vdr"

    created = source_service.create_bundle(
        bundle,
        recovery_key=recovery_key,
        owner_id=owner_identity['owner_id'],
        key_id="recovery-set-1",
    )
    assert created["portable"] is True
    assert created["source_host_key_required_for_restore"] is False
    assert bundle.is_file()

    # The target deliberately has a different host root key. Restore must not
    # depend on the source machine's keychain.
    target_backups = BackupService(target, root_key_store=_FixedRootKeyStore(b"t" * 32))
    target_service = DisasterRecoveryService(target_backups, maintenance_mode=True)
    restored = target_service.restore_bundle(
        bundle,
        recovery_key=recovery_key,
        owner_id=owner_identity['owner_id'],
        expected_key_id="recovery-set-1",
    )

    assert restored["ok"] is True
    assert restored["portable_disaster_recovery"] is True
    assert restored["credentials_rebind_required"] is True
    assert _read_sqlite(target / "memory.sqlite3") == "same-vishnu-memory"
    assert (target / "notes.txt").read_text(encoding="utf-8") == "portable owner state"
    assert not (target / ".env").exists()
    # Security authority is intentionally recreated/rebound on the new host.
    assert not (target / "devices.sqlite3").exists()
    assert "devices.sqlite3" in restored["skipped_security_state"]
    restored_owner = OwnerAccessStore(target / 'owner-access.sqlite3')
    assert restored_owner.identity()['owner_id'] == owner_identity['owner_id']
    assert restored_owner.identity()['vishnu_id'] == owner_identity['vishnu_id']
    assert restored_owner.password_configured() is False
    assert restored_owner.recovery_codes_remaining() == 0


def test_recovery_bundle_does_not_embed_recovery_key(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.txt").write_text("owner-state", encoding="utf-8")
    key = bytes(range(32))
    bundle = tmp_path / "recovery.vdr"

    DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    ).create_bundle(
        bundle,
        recovery_key=key,
        owner_id="owner-private",
        key_id="recovery-set-2",
    )

    raw = bundle.read_bytes()
    assert key not in raw
    assert b"owner-private" not in raw
    assert b"owner-state" not in raw


def test_wrong_recovery_key_cannot_validate_bundle(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.txt").write_text("secret-state", encoding="utf-8")
    service = DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    )
    bundle = tmp_path / "recovery.vdr"
    service.create_bundle(
        bundle,
        recovery_key=b"a" * 32,
        owner_id="owner-1",
        key_id="recovery-set-1",
    )

    with pytest.raises((PermissionError, DisasterRecoveryError)):
        service.validate_bundle(
            bundle,
            recovery_key=b"b" * 32,
            owner_id="owner-1",
        )


def test_wrong_owner_cannot_restore_bundle(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "state.txt").write_text("secret-state", encoding="utf-8")
    key = b"a" * 32
    bundle = tmp_path / "recovery.vdr"
    DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    ).create_bundle(
        bundle,
        recovery_key=key,
        owner_id="owner-1",
        key_id="recovery-set-1",
    )

    target_service = DisasterRecoveryService(
        BackupService(target, root_key_store=_FixedRootKeyStore(b"y" * 32)),
        maintenance_mode=True,
    )
    with pytest.raises(PermissionError, match="owner mismatch"):
        target_service.restore_bundle(
            bundle,
            recovery_key=key,
            owner_id="owner-2",
        )


def test_tampered_recovery_bundle_fails_authentication(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.txt").write_text("important", encoding="utf-8")
    key = b"a" * 32
    bundle = tmp_path / "recovery.vdr"
    service = DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    )
    service.create_bundle(
        bundle,
        recovery_key=key,
        owner_id="owner-1",
        key_id="recovery-set-1",
    )

    raw = bytearray(bundle.read_bytes())
    raw[-20] ^= 0x01
    bundle.write_bytes(raw)

    with pytest.raises(DisasterRecoveryError, match="authentication failed"):
        service.validate_bundle(
            bundle,
            recovery_key=key,
            owner_id="owner-1",
        )


def test_restore_requires_maintenance_mode(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "state.txt").write_text("important", encoding="utf-8")
    key = b"a" * 32
    bundle = tmp_path / "recovery.vdr"
    DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    ).create_bundle(
        bundle,
        recovery_key=key,
        owner_id="owner-1",
        key_id="recovery-set-1",
    )

    target_service = DisasterRecoveryService(
        BackupService(target, root_key_store=_FixedRootKeyStore(b"y" * 32))
    )
    with pytest.raises(DisasterRecoveryError, match="maintenance mode"):
        target_service.restore_bundle(
            bundle,
            recovery_key=key,
            owner_id="owner-1",
        )


def test_recovery_key_must_be_high_entropy_key_material(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "state.txt").write_text("important", encoding="utf-8")
    service = DisasterRecoveryService(
        BackupService(source, root_key_store=_FixedRootKeyStore(b"x" * 32))
    )

    with pytest.raises(DisasterRecoveryError, match="exactly 32 bytes"):
        service.create_bundle(
            tmp_path / "bad.vdr",
            recovery_key=b"password",
            owner_id="owner-1",
            key_id="recovery-set-1",
        )


def test_recovery_key_file_is_passphrase_encrypted_and_authenticated():
    key = generate_recovery_key()
    passphrase = "correct horse battery staple"
    envelope = encrypt_recovery_key_file(key, passphrase)

    assert key not in envelope
    assert decrypt_recovery_key_file(envelope, passphrase) == key
    with pytest.raises(DisasterRecoveryError, match="could not be authenticated"):
        decrypt_recovery_key_file(envelope, "wrong recovery passphrase")
    tampered = bytearray(envelope)
    tampered[-1] ^= 1
    with pytest.raises(DisasterRecoveryError, match="could not be authenticated"):
        decrypt_recovery_key_file(bytes(tampered), passphrase)
    with pytest.raises(ValueError, match="at least 12"):
        encrypt_recovery_key_file(key, "short")
