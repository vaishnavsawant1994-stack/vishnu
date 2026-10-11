from __future__ import annotations

from hashlib import sha256

import pytest

from models.intelligence_restore import RestoreArtifact, RestoreArtifactKind
from models.intelligence_vault import FilesystemIntelligenceVault


def _artifact(path, *, artifact_id: str = "recovery-1", private: bool = True) -> RestoreArtifact:
    data = path.read_bytes()
    return RestoreArtifact(
        name="owner-recovery",
        artifact_id=artifact_id,
        version="1",
        sha256=sha256(data).hexdigest(),
        locator="staging://owner-recovery",
        kind=RestoreArtifactKind.DATABASE,
        required=True,
        encrypted=private,
        contains_private_data=private,
        size_bytes=len(data),
    )


def test_vault_put_verify_and_materialize_round_trip(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"encrypted-vishnu-recovery-bundle")
    vault = FilesystemIntelligenceVault(tmp_path / "vault", persistent=True)

    record = vault.put("owner-1", _artifact(source), source)

    assert record.artifact.locator == f"vault://sha256/{record.object_sha256}"
    assert record.artifact.contains_private_data is True
    assert record.artifact.encrypted is True
    assert vault.verify("owner-1", "recovery-1") == record
    restored = vault.materialize("owner-1", "recovery-1", tmp_path / "download.vdr")
    assert restored.read_bytes() == source.read_bytes()
    assert vault.status()["production_durable"] is True


def test_owner_identifier_is_not_used_as_directory_name(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"encrypted")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")
    vault.put("private-owner-email@example.test", _artifact(source), source)

    paths = [str(path.relative_to(vault.root)) for path in vault.root.rglob("*")]
    assert all("private-owner-email@example.test" not in path for path in paths)


def test_different_owner_cannot_resolve_private_record(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"encrypted")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")
    vault.put("owner-1", _artifact(source), source)

    with pytest.raises(FileNotFoundError):
        vault.verify("owner-2", "recovery-1")


def test_vault_rejects_source_digest_mismatch(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"one")
    artifact = _artifact(source)
    source.write_bytes(b"two")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")

    with pytest.raises(RuntimeError, match="digest"):
        vault.put("owner-1", artifact, source)


def test_artifact_id_is_immutable_for_owner(tmp_path):
    first = tmp_path / "first.vdr"
    second = tmp_path / "second.vdr"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")
    vault.put("owner-1", _artifact(first, artifact_id="same-id"), first)

    with pytest.raises(RuntimeError, match="different immutable content"):
        vault.put("owner-1", _artifact(second, artifact_id="same-id"), second)


def test_vault_detects_object_tampering(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"encrypted")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")
    record = vault.put("owner-1", _artifact(source), source)
    object_path = vault.objects / record.object_sha256[:2] / record.object_sha256
    object_path.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="integrity failure"):
        vault.verify("owner-1", "recovery-1")


def test_materialize_fails_closed_on_existing_target(tmp_path):
    source = tmp_path / "source.vdr"
    source.write_bytes(b"encrypted")
    target = tmp_path / "target.vdr"
    target.write_bytes(b"existing")
    vault = FilesystemIntelligenceVault(tmp_path / "vault")
    vault.put("owner-1", _artifact(source), source)

    with pytest.raises(FileExistsError):
        vault.materialize("owner-1", "recovery-1", target)
    assert target.read_bytes() == b"existing"

    vault.materialize("owner-1", "recovery-1", target, overwrite=True)
    assert target.read_bytes() == b"encrypted"


def test_private_artifacts_cannot_enter_vault_unencrypted(tmp_path):
    source = tmp_path / "private.db"
    source.write_bytes(b"private")
    digest = sha256(source.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="must be encrypted"):
        RestoreArtifact(
            name="private-db",
            artifact_id="private-db-1",
            version="1",
            sha256=digest,
            locator="staging://private-db",
            kind=RestoreArtifactKind.DATABASE,
            encrypted=False,
            contains_private_data=True,
            size_bytes=source.stat().st_size,
        )
