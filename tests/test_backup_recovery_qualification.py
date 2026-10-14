from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from memory.crypto import MemoryFieldCipher, VAULT_KEY_NAME
from recovery.backup import BACKUP_MAGIC, BackupError, BackupService, MEMORY_KEY_ENVELOPE
from recovery.disaster_recovery import (
    DR_MEMORY_KEY_KIND,
    DisasterRecoveryService,
    generate_recovery_key,
)
from security.vault import SecretVault


class _RootKeyStore:
    def __init__(self, key: bytes):
        self.active = key
        self.staged: dict[str, bytes] = {}

    def get(self) -> bytes:
        return self.active

    def get_or_create(self) -> bytes:
        return self.active

    def validate_rotation_id(self, rotation_id: str) -> str:
        if len(rotation_id) != 32 or any(c not in "0123456789abcdef" for c in rotation_id):
            raise ValueError("invalid rotation id")
        return rotation_id

    def stage_rotation(self, rotation_id: str) -> bytes:
        self.validate_rotation_id(rotation_id)
        return self.staged.setdefault(rotation_id, bytes([self.active[0] ^ 0xFF]) * 32)

    def promote_staged(self, rotation_id: str) -> bytes:
        self.active = self.staged[rotation_id]
        return self.active

    def discard_staged(self, rotation_id: str) -> None:
        self.staged.pop(rotation_id, None)


def test_encrypted_backup_round_trip_and_legacy_v1_restore(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    sentinel = "BACKUP_OWNER_CONTENT_SENTINEL"
    (source / "owner.txt").write_text(sentinel, encoding="utf-8")
    source_service = BackupService(source, root_key_store=_RootKeyStore(b"s" * 32))

    archive = source_service.create("encrypted")
    raw = archive.read_bytes()
    assert raw.startswith(BACKUP_MAGIC)
    assert sentinel.encode() not in raw
    assert source_service.inspect(archive)["encrypted"] is True

    target_service = BackupService(target, root_key_store=_RootKeyStore(b"s" * 32))
    assert target_service.restore(archive)["ok"] is True
    assert (target / "owner.txt").read_text(encoding="utf-8") == sentinel

    legacy = tmp_path / "legacy-v1.zip"
    payload = b"legacy owner state"
    manifest = {
        "version": 1,
        "created_at": 1,
        "files": [{
            "path": "legacy.txt",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }],
    }
    with zipfile.ZipFile(legacy, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
        archive_file.writestr("legacy.txt", payload)
        archive_file.writestr("manifest.json", json.dumps(manifest))
    result = target_service.restore(legacy)
    assert result["encrypted"] is False
    assert (target / "legacy.txt").read_bytes() == payload


def test_wrong_root_key_and_corruption_leave_existing_state_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "state.txt").write_text("backed up state", encoding="utf-8")
    protected = target / "state.txt"
    protected.write_text("healthy target state", encoding="utf-8")
    archive = BackupService(source, root_key_store=_RootKeyStore(b"a" * 32)).create()

    wrong_key_service = BackupService(target, root_key_store=_RootKeyStore(b"b" * 32))
    with pytest.raises(BackupError, match="authentication"):
        wrong_key_service.restore(archive)
    assert protected.read_text(encoding="utf-8") == "healthy target state"

    corrupt = tmp_path / "corrupt.paibackup"
    damaged = bytearray(archive.read_bytes())
    damaged[-1] ^= 0x01
    corrupt.write_bytes(damaged)
    with pytest.raises(BackupError, match="authentication"):
        BackupService(target, root_key_store=_RootKeyStore(b"a" * 32)).restore(corrupt)
    assert protected.read_text(encoding="utf-8") == "healthy target state"


def test_interrupted_restore_rolls_back_every_installed_file(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "alpha.txt").write_text("backup alpha", encoding="utf-8")
    (source / "beta.txt").write_text("backup beta", encoding="utf-8")
    archive = BackupService(source, root_key_store=_RootKeyStore(b"r" * 32)).create()

    (target / "alpha.txt").write_text("healthy alpha", encoding="utf-8")
    (target / "beta.txt").write_text("healthy beta", encoding="utf-8")
    service = BackupService(target, root_key_store=_RootKeyStore(b"r" * 32))
    original_copy = service._copy_fsynced

    def fail_second_install(source_path: Path, destination: Path) -> None:
        if source_path.name == "beta.txt" and destination.suffix == ".restore":
            raise OSError("injected interruption during restore")
        original_copy(source_path, destination)

    monkeypatch.setattr(service, "_copy_fsynced", fail_second_install)
    with pytest.raises(BackupError, match="rolled back"):
        service.restore(archive)
    assert (target / "alpha.txt").read_text(encoding="utf-8") == "healthy alpha"
    assert (target / "beta.txt").read_text(encoding="utf-8") == "healthy beta"


def test_disaster_restore_rewraps_memory_key_after_root_rotation_on_clean_host(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "clean-host"
    source.mkdir()
    target.mkdir()
    source_keys = _RootKeyStore(b"a" * 32)
    vault = SecretVault(source / "vault.json", root_key_store=source_keys)
    cipher = MemoryFieldCipher(vault)
    sentinel = "ENCRYPTED_MEMORY_RECOVERY_SENTINEL"
    encrypted_content = cipher.encrypt("messages", "message-1", "content", sentinel)
    database = source / "assistant.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE messages(content TEXT NOT NULL)")
        connection.execute("INSERT INTO messages(content) VALUES(?)", (encrypted_content,))
        connection.commit()

    # The existing root-key rotation path must keep both the vault and MemoryStore DEK usable.
    vault.rotate_root_key()
    assert source_keys.active != b"a" * 32
    assert MemoryFieldCipher(vault).decrypt(
        "messages", "message-1", "content", encrypted_content
    ) == sentinel
    dek = base64.b64decode(vault.get(VAULT_KEY_NAME), validate=True)

    backups = BackupService(source, root_key_store=source_keys, vault=vault)
    recovery = DisasterRecoveryService(backups)
    recovery_key = generate_recovery_key()
    bundle = tmp_path / "portable-recovery.vdr"
    recovery.create_bundle(
        bundle,
        recovery_key=recovery_key,
        owner_id="owner-1",
        key_id="recovery-set-1",
    )
    bundle_bytes = bundle.read_bytes()
    assert sentinel.encode() not in bundle_bytes
    assert dek not in bundle_bytes

    target_keys = _RootKeyStore(b"z" * 32)
    target_backups = BackupService(target, root_key_store=target_keys)
    restored = DisasterRecoveryService(
        target_backups,
        maintenance_mode=True,
    ).restore_bundle(
        bundle,
        recovery_key=recovery_key,
        owner_id="owner-1",
        expected_key_id="recovery-set-1",
    )
    assert restored["ok"] is True
    assert restored["portable_disaster_recovery"] is True

    target_vault = SecretVault(target / "vault.json", root_key_store=target_keys)
    target_cipher = MemoryFieldCipher(target_vault)
    with sqlite3.connect(target / "assistant.sqlite3") as connection:
        stored = connection.execute("SELECT content FROM messages").fetchone()[0]
    assert stored.startswith("v1:")
    assert sentinel not in stored
    assert target_cipher.decrypt("messages", "message-1", "content", stored) == sentinel
    assert base64.b64decode(target_vault.get(VAULT_KEY_NAME), validate=True) == dek

    payload, _header = recovery.codec.decrypt_payload(
        bundle,
        recovery_key=recovery_key,
        owner_id="owner-1",
        expected_key_id="recovery-set-1",
    )
    try:
        with zipfile.ZipFile(payload) as archive:
            envelope = json.loads(archive.read(MEMORY_KEY_ENVELOPE))
        assert envelope["kind"] == DR_MEMORY_KEY_KIND
        assert dek not in payload.read_bytes()
    finally:
        payload.unlink(missing_ok=True)
