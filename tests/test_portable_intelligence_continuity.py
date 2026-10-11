from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from continuity.checkpoint import _snapshot_intelligence_manifest
from continuity.models import ContinuityCheckpoint
from continuity.service import AgentContinuityService
from models.portable_intelligence import (
    FilesystemIntelligenceManifestStore,
    IntelligenceManifest,
    IntelligenceReference,
)


def _manifest(*, core_version: str = "9.0.0") -> IntelligenceManifest:
    return IntelligenceManifest.create(
        owner_id="owner-test",
        core_version=core_version,
        models=(
            IntelligenceReference(
                name="general",
                ref_id="vishnu-general-20",
                version="20",
                sha256="a" * 64,
            ),
        ),
        agents=(
            IntelligenceReference(
                name="coding-agent",
                ref_id="coding-agent-32",
                version="32",
                sha256="b" * 64,
            ),
        ),
        schemas={"memory": "13", "knowledge": "10"},
        registries={"models": "20", "agents": "32"},
        created_at="2026-10-11T10:00:00+00:00",
    )


def _checkpoint(**overrides) -> ContinuityCheckpoint:
    values = {
        "id": "ccp_test",
        "source_host_id": "host-a",
        "authority_epoch": 7,
        "backup_filename": "continuity-test.paibackup",
        "backup_sha256": "c" * 64,
        "backup_size": 123,
        "payload_sha256": "d" * 64,
        "data_manifest_hash": "e" * 64,
        "active_body_revision_id": "body-1",
        "active_body_git_revision": "abc123",
        "schema_versions": {"identity": (1,), "agent_continuity": (1,)},
        "state_summary": {"file_count": 2},
        "created_at": "2026-10-11T10:00:00+00:00",
    }
    values.update(overrides)
    return ContinuityCheckpoint(**values)


def _legacy_checkpoint_hash(checkpoint: ContinuityCheckpoint) -> str:
    payload = {
        "id": checkpoint.id,
        "source_host_id": checkpoint.source_host_id,
        "authority_epoch": checkpoint.authority_epoch,
        "backup_filename": checkpoint.backup_filename,
        "backup_sha256": checkpoint.backup_sha256,
        "backup_size": checkpoint.backup_size,
        "payload_sha256": checkpoint.payload_sha256,
        "data_manifest_hash": checkpoint.data_manifest_hash,
        "active_body_revision_id": checkpoint.active_body_revision_id,
        "active_body_git_revision": checkpoint.active_body_git_revision,
        "schema_versions": {
            key: list(value) for key, value in sorted(checkpoint.schema_versions.items())
        },
        "state_summary": dict(checkpoint.state_summary),
        "created_at": checkpoint.created_at,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write_snapshot(path: Path, manifest: IntelligenceManifest, *, pointer_fingerprint: str | None = None) -> None:
    pointer = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "fingerprint": pointer_fingerprint or manifest.fingerprint,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("intelligence/active-manifest.json", json.dumps(pointer))
        archive.writestr(
            f"intelligence/manifests/{manifest.manifest_id}.json",
            json.dumps(manifest.public()),
        )


def test_legacy_checkpoint_hash_and_wire_shape_remain_compatible():
    checkpoint = _checkpoint()

    assert checkpoint.checkpoint_hash == _legacy_checkpoint_hash(checkpoint)
    wire = checkpoint.to_dict()
    assert "intelligence_manifest_id" not in wire
    assert "intelligence_manifest_fingerprint" not in wire
    assert ContinuityCheckpoint.from_dict(wire) == checkpoint


def test_legacy_positional_checkpoint_constructor_remains_compatible():
    checkpoint = ContinuityCheckpoint(
        "ccp_positional",
        "host-a",
        7,
        "continuity-test.paibackup",
        "c" * 64,
        123,
        "d" * 64,
        "e" * 64,
        "body-1",
        "abc123",
        {"identity": (1,)},
        {"file_count": 2},
        "2026-10-11T10:00:00+00:00",
    )

    assert checkpoint.schema_versions == {"identity": (1,)}
    assert checkpoint.state_summary == {"file_count": 2}
    assert checkpoint.created_at == "2026-10-11T10:00:00+00:00"
    assert checkpoint.intelligence_binding() == {}


def test_manifest_binding_is_authenticated_by_checkpoint_hash():
    manifest = _manifest()
    checkpoint = _checkpoint(
        intelligence_manifest_id=manifest.manifest_id,
        intelligence_manifest_fingerprint=manifest.fingerprint,
    )

    wire = checkpoint.to_dict()
    assert wire["intelligence_manifest_id"] == manifest.manifest_id
    assert wire["intelligence_manifest_fingerprint"] == manifest.fingerprint
    assert ContinuityCheckpoint.from_dict(wire) == checkpoint

    tampered = dict(wire)
    tampered["intelligence_manifest_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match="manifest id does not match|checkpoint hash mismatch"):
        ContinuityCheckpoint.from_dict(tampered)


def test_partial_manifest_binding_is_rejected():
    manifest = _manifest()
    checkpoint = _checkpoint(intelligence_manifest_id=manifest.manifest_id)

    with pytest.raises(ValueError, match="must be supplied together"):
        checkpoint.to_dict()


def test_snapshot_manifest_reader_verifies_active_pointer(tmp_path):
    manifest = _manifest()
    payload = tmp_path / "snapshot.zip"
    _write_snapshot(payload, manifest)

    restored = _snapshot_intelligence_manifest(payload)

    assert restored is not None
    assert restored.manifest_id == manifest.manifest_id
    assert restored.fingerprint == manifest.fingerprint


def test_snapshot_manifest_reader_rejects_tampered_pointer(tmp_path):
    manifest = _manifest()
    payload = tmp_path / "tampered-snapshot.zip"
    _write_snapshot(payload, manifest, pointer_fingerprint="f" * 64)

    with pytest.raises(RuntimeError, match="pointer mismatch"):
        _snapshot_intelligence_manifest(payload)


def test_restored_intelligence_must_match_checkpoint(tmp_path):
    data_dir = tmp_path / "restored"
    data_dir.mkdir()
    manifest = _manifest()
    store = FilesystemIntelligenceManifestStore(data_dir)
    store.activate(manifest)
    checkpoint = _checkpoint(
        intelligence_manifest_id=manifest.manifest_id,
        intelligence_manifest_fingerprint=manifest.fingerprint,
    )

    AgentContinuityService._verify_restored_intelligence(data_dir, checkpoint)

    different = _manifest(core_version="9.1.0")
    store.activate(different)
    with pytest.raises(RuntimeError, match="does not match checkpoint"):
        AgentContinuityService._verify_restored_intelligence(data_dir, checkpoint)


def test_restored_intelligence_binding_fails_closed_when_active_pointer_is_missing(tmp_path):
    data_dir = tmp_path / "restored"
    data_dir.mkdir()
    manifest = _manifest()
    checkpoint = _checkpoint(
        intelligence_manifest_id=manifest.manifest_id,
        intelligence_manifest_fingerprint=manifest.fingerprint,
    )

    with pytest.raises(RuntimeError, match="active intelligence manifest is missing"):
        AgentContinuityService._verify_restored_intelligence(data_dir, checkpoint)
