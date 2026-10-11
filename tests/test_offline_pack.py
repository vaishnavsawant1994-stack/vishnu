from __future__ import annotations

from hashlib import sha256

import pytest

from models.hardware_profile import HardwareProfile
from models.intelligence_restore import IntelligenceRestorePackage, RestoreArtifact, RestoreArtifactKind
from models.intelligence_vault import FilesystemIntelligenceVault
from models.offline_pack import OfflinePackManager
from models.portable_intelligence import (
    ExecutionTarget,
    IntelligenceManifest,
    ModelTier,
    RuntimeCandidate,
)


def _hardware(*, disk_free_gb: float = 100.0, ram_gb: float = 16.0) -> HardwareProfile:
    return HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=8,
        ram_gb=ram_gb,
        disk_free_gb=disk_free_gb,
        accelerator="none",
        online=True,
    )


def _runtime(*, minimum_ram_gb: float = 8.0) -> RuntimeCandidate:
    return RuntimeCandidate(
        runtime_id="vishnu-small-cpu",
        model_ref="vishnu-small-v1",
        tier=ModelTier.SMALL,
        target=ExecutionTarget.LOCAL,
        minimum_ram_gb=minimum_ram_gb,
    )


def _package(tmp_path, *, required: bool = True, private: bool = False, put_in_vault: bool = True):
    source = tmp_path / "source.bin"
    source.write_bytes(b"encrypted-owner-state" if private else b"offline-model-artifact")
    digest = sha256(source.read_bytes()).hexdigest()
    artifact = RestoreArtifact(
        name="owner-state" if private else "small-model",
        artifact_id="owner-state-v1" if private else "model-small-v1",
        version="1",
        sha256=digest,
        locator="staging://artifact",
        kind=RestoreArtifactKind.DATABASE if private else RestoreArtifactKind.MODEL,
        required=required,
        encrypted=private,
        contains_private_data=private,
        size_bytes=source.stat().st_size,
    )
    manifest = IntelligenceManifest.create(
        owner_id="owner-1",
        core_version="1.0",
        created_at="2026-10-11T00:00:00+00:00",
    )
    vault = FilesystemIntelligenceVault(tmp_path / "vault", persistent=True)
    canonical = vault.put("owner-1", artifact, source).artifact if put_in_vault else artifact
    package = IntelligenceRestorePackage.create(
        manifest=manifest,
        artifacts=(canonical,),
        owner_id="owner-1",
        created_at="2026-10-11T00:01:00+00:00",
    )
    return vault, package, canonical


def test_offline_pack_prepare_and_verify_round_trip(tmp_path):
    vault, package, artifact = _package(tmp_path)
    manager = OfflinePackManager(vault)

    verification = manager.prepare(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_runtime(),),
        target=tmp_path / "offline-pack",
    )

    assert verification.manifest.runtime_id == "vishnu-small-cpu"
    assert verification.manifest.model_ref == "vishnu-small-v1"
    assert verification.manifest.restore_package_id == package.package_id
    assert verification.manifest.intelligence_manifest_id == package.manifest.manifest_id
    assert verification.local_artifacts == {artifact.artifact_id: artifact.sha256}
    assert (tmp_path / "offline-pack" / "offline-pack.json").is_file()

    reverified = manager.verify(
        tmp_path / "offline-pack",
        expected_owner_id="owner-1",
        expected_restore_package=package,
    )
    assert reverified.local_artifacts == verification.local_artifacts


def test_offline_pack_detects_materialized_artifact_tampering(tmp_path):
    vault, package, _ = _package(tmp_path)
    manager = OfflinePackManager(vault)
    verification = manager.prepare(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_runtime(),),
        target=tmp_path / "offline-pack",
    )
    relative = verification.manifest.artifacts[0].relative_path
    (tmp_path / "offline-pack" / relative).write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="integrity failure"):
        manager.verify(tmp_path / "offline-pack")


def test_offline_pack_wrong_owner_fails_closed(tmp_path):
    vault, package, _ = _package(tmp_path)
    manager = OfflinePackManager(vault)

    with pytest.raises(PermissionError, match="owner"):
        manager.prepare(
            owner_id="owner-2",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_runtime(),),
            target=tmp_path / "offline-pack",
        )


def test_offline_pack_missing_required_vault_artifact_blocks(tmp_path):
    vault, package, artifact = _package(tmp_path, put_in_vault=False)
    manager = OfflinePackManager(vault)

    with pytest.raises(RuntimeError, match=artifact.artifact_id):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_runtime(),),
            target=tmp_path / "offline-pack",
        )


def test_offline_pack_optional_missing_artifact_is_skipped(tmp_path):
    vault, package, artifact = _package(tmp_path, required=False, put_in_vault=False)
    manager = OfflinePackManager(vault)

    verification = manager.prepare(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_runtime(),),
        target=tmp_path / "offline-pack",
    )

    assert artifact.artifact_id not in verification.local_artifacts
    assert verification.manifest.artifacts == ()


def test_explicit_optional_artifact_requirement_blocks_when_missing(tmp_path):
    vault, package, artifact = _package(tmp_path, required=False, put_in_vault=False)
    manager = OfflinePackManager(vault)

    with pytest.raises(RuntimeError, match="required offline artifact"):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_runtime(),),
            target=tmp_path / "offline-pack",
            required_artifact_ids=(artifact.artifact_id,),
        )


def test_unknown_explicit_artifact_requirement_is_rejected(tmp_path):
    vault, package, _ = _package(tmp_path)
    manager = OfflinePackManager(vault)

    with pytest.raises(ValueError, match="not in restore package"):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_runtime(),),
            target=tmp_path / "offline-pack",
            required_artifact_ids=("not-in-package",),
        )


def test_offline_pack_no_feasible_local_runtime_blocks(tmp_path):
    vault, package, _ = _package(tmp_path)
    manager = OfflinePackManager(vault)

    with pytest.raises(RuntimeError, match="offline readiness blocked"):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(ram_gb=4),
            runtime_candidates=(_runtime(minimum_ram_gb=8),),
            target=tmp_path / "offline-pack",
        )


def test_offline_pack_insufficient_disk_blocks(tmp_path):
    vault, package, artifact = _package(tmp_path)
    manager = OfflinePackManager(vault)
    too_small = (int(artifact.size_bytes or 0) - 1) / (1024 ** 3)

    with pytest.raises(RuntimeError, match="insufficient free disk"):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(disk_free_gb=max(0.0, too_small)),
            runtime_candidates=(_runtime(),),
            target=tmp_path / "offline-pack",
        )


def test_offline_pack_existing_target_fails_closed(tmp_path):
    vault, package, _ = _package(tmp_path)
    target = tmp_path / "offline-pack"
    target.mkdir()
    manager = OfflinePackManager(vault)

    with pytest.raises(FileExistsError):
        manager.prepare(
            owner_id="owner-1",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_runtime(),),
            target=target,
        )


def test_private_artifact_remains_encrypted_in_pack_metadata(tmp_path):
    vault, package, artifact = _package(tmp_path, private=True)
    manager = OfflinePackManager(vault)
    verification = manager.prepare(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_runtime(),),
        target=tmp_path / "offline-pack",
    )

    packed = verification.manifest.artifacts[0]
    assert packed.artifact_id == artifact.artifact_id
    assert packed.contains_private_data is True
    assert packed.encrypted is True


def test_offline_pack_manifest_tampering_is_detected(tmp_path):
    vault, package, _ = _package(tmp_path)
    manager = OfflinePackManager(vault)
    manager.prepare(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_runtime(),),
        target=tmp_path / "offline-pack",
    )
    manifest_path = tmp_path / "offline-pack" / "offline-pack.json"
    payload = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    payload["model_ref"] = "attacker-model"
    manifest_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        manager.verify(tmp_path / "offline-pack")
