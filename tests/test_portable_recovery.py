from __future__ import annotations

import json
from pathlib import Path
import stat
import zipfile

import pytest

from models.portable_intelligence import IntelligenceManifest, IntelligenceReference
from models.portable_recovery import PortableRecoveryBundle


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
        registries={"agents": "32", "models": "20"},
        created_at="2026-10-11T10:00:00+00:00",
    )


def _prepared_snapshot(root: Path) -> None:
    (root / "memory").mkdir(parents=True)
    (root / "knowledge").mkdir(parents=True)
    (root / "agents").mkdir(parents=True)
    (root / "memory" / "memory.snapshot.db").write_bytes(b"sqlite-memory-snapshot")
    (root / "knowledge" / "index.json").write_text('{"version": 10}\n', encoding="utf-8")
    (root / "agents" / "learned-strategies.json").write_text(
        '{"coding": ["verify-before-promote"]}\n',
        encoding="utf-8",
    )


def _create_bundle(tmp_path: Path, *, name: str = "vishnu-recovery.zip") -> tuple[Path, IntelligenceManifest]:
    source = tmp_path / "prepared"
    source.mkdir()
    _prepared_snapshot(source)
    manifest = _manifest()
    bundle = tmp_path / name
    PortableRecoveryBundle.create(
        source_root=source,
        output_path=bundle,
        intelligence_manifest=manifest,
        components={
            "memory": ("memory",),
            "knowledge": ("knowledge/index.json",),
            "agent-learning": ("agents/learned-strategies.json",),
        },
        created_at="2026-10-11T11:00:00+00:00",
    )
    return bundle, manifest


def test_recovery_bundle_round_trip_verifies_and_restores(tmp_path):
    bundle, manifest = _create_bundle(tmp_path)

    verified = PortableRecoveryBundle.verify(bundle, expected_manifest=manifest)
    destination = tmp_path / "restored"
    restored = PortableRecoveryBundle.restore(
        bundle,
        destination_root=destination,
        expected_manifest=manifest,
    )

    assert verified.bundle_id == restored.bundle_id
    assert restored.intelligence_manifest["manifest_id"] == manifest.manifest_id
    assert (destination / "memory" / "memory.snapshot.db").read_bytes() == b"sqlite-memory-snapshot"
    assert json.loads((destination / "knowledge" / "index.json").read_text(encoding="utf-8")) == {"version": 10}
    assert "verify-before-promote" in (destination / "agents" / "learned-strategies.json").read_text(encoding="utf-8")


def test_recovery_bundle_manifest_is_stable_for_same_snapshot(tmp_path):
    source = tmp_path / "prepared"
    source.mkdir()
    _prepared_snapshot(source)
    manifest = _manifest()

    first = PortableRecoveryBundle.create(
        source_root=source,
        output_path=tmp_path / "first.zip",
        intelligence_manifest=manifest,
        components={"state": ("memory", "knowledge", "agents")},
        created_at="2026-10-11T11:00:00+00:00",
    )
    second = PortableRecoveryBundle.create(
        source_root=source,
        output_path=tmp_path / "second.zip",
        intelligence_manifest=manifest,
        components={"state": ("agents", "knowledge", "memory")},
        created_at="2026-10-11T11:00:00+00:00",
    )

    assert first.bundle_id == second.bundle_id
    assert first.fingerprint == second.fingerprint
    assert first.public() == second.public()


def test_recovery_bundle_detects_tampered_payload(tmp_path):
    bundle, manifest = _create_bundle(tmp_path)
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(bundle, "r") as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "payload/memory/memory.snapshot.db":
                data = b"tampered-memory"
            replacement = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            replacement.compress_type = zipfile.ZIP_DEFLATED
            replacement.create_system = 3
            replacement.external_attr = (stat.S_IFREG | 0o600) << 16
            target.writestr(replacement, data)

    with pytest.raises(RuntimeError, match="size mismatch|hash mismatch"):
        PortableRecoveryBundle.verify(tampered, expected_manifest=manifest)


def test_recovery_bundle_rejects_wrong_intelligence_manifest(tmp_path):
    bundle, _ = _create_bundle(tmp_path)
    different = _manifest(core_version="9.1.0")

    with pytest.raises(RuntimeError, match="intelligence manifest mismatch"):
        PortableRecoveryBundle.verify(bundle, expected_manifest=different)


def test_recovery_bundle_rejects_archive_path_traversal(tmp_path):
    bundle, _ = _create_bundle(tmp_path)
    malicious = tmp_path / "malicious.zip"

    with zipfile.ZipFile(bundle, "r") as source, zipfile.ZipFile(malicious, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info.filename))
        evil = zipfile.ZipInfo("payload/../escape.txt", date_time=(1980, 1, 1, 0, 0, 0))
        evil.compress_type = zipfile.ZIP_DEFLATED
        evil.create_system = 3
        evil.external_attr = (stat.S_IFREG | 0o600) << 16
        target.writestr(evil, b"escape")

    with pytest.raises(ValueError, match="traversal"):
        PortableRecoveryBundle.verify(malicious)


def test_recovery_bundle_rejects_source_symlinks(tmp_path):
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "real.txt").write_text("canonical", encoding="utf-8")
    link = source / "link.txt"
    try:
        link.symlink_to(source / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(ValueError, match="symlink"):
        PortableRecoveryBundle.create(
            source_root=source,
            output_path=tmp_path / "bundle.zip",
            intelligence_manifest=_manifest(),
            components={"memory": ("link.txt",)},
        )


def test_recovery_restore_fails_closed_on_existing_target_by_default(tmp_path):
    bundle, manifest = _create_bundle(tmp_path)
    destination = tmp_path / "restored"
    existing = destination / "memory" / "memory.snapshot.db"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"do-not-replace")

    with pytest.raises(FileExistsError):
        PortableRecoveryBundle.restore(
            bundle,
            destination_root=destination,
            expected_manifest=manifest,
        )
    assert existing.read_bytes() == b"do-not-replace"


def test_recovery_restore_overwrite_is_explicit(tmp_path):
    bundle, manifest = _create_bundle(tmp_path)
    destination = tmp_path / "restored"
    existing = destination / "memory" / "memory.snapshot.db"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")

    PortableRecoveryBundle.restore(
        bundle,
        destination_root=destination,
        expected_manifest=manifest,
        overwrite=True,
    )

    assert existing.read_bytes() == b"sqlite-memory-snapshot"
