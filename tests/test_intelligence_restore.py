from __future__ import annotations

import pytest

from models.intelligence_restore import (
    IntelligenceRestorePackage,
    RestoreAction,
    RestoreArtifact,
    RestoreArtifactKind,
    build_restore_preflight,
)
from models.portable_intelligence import IntelligenceManifest, IntelligenceReference


def _reference(name: str, version: str) -> IntelligenceReference:
    return IntelligenceReference(
        name=name,
        ref_id=f"{name}-{version}",
        version=version,
        sha256="a" * 64,
    )


def _manifest() -> IntelligenceManifest:
    return IntelligenceManifest.create(
        owner_id="owner-test",
        core_version="9.0.0",
        models=(_reference("general", "20"),),
        agents=(_reference("coding-agent", "32"),),
        schemas={"memory": "13", "knowledge": "10"},
        registries={"skills": "20", "training": "29"},
        runtime_policy={"family": "vishnu-21"},
        created_at="2026-10-11T08:00:00+00:00",
    )


def _artifacts() -> tuple[RestoreArtifact, ...]:
    return (
        RestoreArtifact(
            name="general-model",
            artifact_id="model-general-20",
            version="20",
            sha256="1" * 64,
            locator="vault://models/general/20",
            kind=RestoreArtifactKind.MODEL,
            size_bytes=4_000_000_000,
        ),
        RestoreArtifact(
            name="memory-snapshot",
            artifact_id="memory-snapshot-13",
            version="13",
            sha256="2" * 64,
            locator="vault://snapshots/memory/13",
            kind=RestoreArtifactKind.DATABASE,
            encrypted=True,
            contains_private_data=True,
            size_bytes=200_000_000,
        ),
    )


def _package() -> IntelligenceRestorePackage:
    return IntelligenceRestorePackage.create(
        manifest=_manifest(),
        artifacts=_artifacts(),
        created_at="2026-10-11T08:01:00+00:00",
    )


def test_restore_package_is_deterministic_round_trip_and_tamper_evident():
    first = _package()
    second = IntelligenceRestorePackage.create(
        manifest=_manifest(),
        artifacts=reversed(_artifacts()),
        created_at="2026-10-11T08:01:00+00:00",
    )

    assert first.package_id == second.package_id
    assert first.fingerprint == second.fingerprint
    assert IntelligenceRestorePackage.from_dict(first.public()) == first

    tampered = first.public()
    tampered["artifacts"][0]["version"] = "999"
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        IntelligenceRestorePackage.from_dict(tampered)


def test_restore_package_requires_same_owner_as_manifest():
    with pytest.raises(ValueError, match="owner must match"):
        IntelligenceRestorePackage.create(
            manifest=_manifest(),
            owner_id="different-owner",
            artifacts=_artifacts(),
        )


def test_private_restore_artifact_must_be_encrypted():
    with pytest.raises(ValueError, match="must be encrypted"):
        RestoreArtifact(
            name="private-memory",
            artifact_id="memory-private",
            version="1",
            sha256="3" * 64,
            locator="vault://snapshots/private-memory/1",
            kind=RestoreArtifactKind.DATABASE,
            contains_private_data=True,
        )


def test_restore_artifact_rejects_signed_or_credential_bearing_locator():
    with pytest.raises(ValueError, match="must not contain"):
        RestoreArtifact(
            name="unsafe",
            artifact_id="unsafe-artifact",
            version="1",
            sha256="4" * 64,
            locator="https://example.invalid/object?token=secret",
        )


def test_preflight_reuses_verified_local_artifacts_and_fetches_missing_ones():
    package = _package()
    plan = build_restore_preflight(
        package,
        {"model-general-20": "1" * 64},
        online=True,
        expected_owner_id="owner-test",
    )

    assert plan.ready is True
    assert plan.blocked_required == ()
    assert plan.fetch_bytes == 200_000_000
    actions = {item.artifact.artifact_id: item.action for item in plan.items}
    assert actions == {
        "memory-snapshot-13": RestoreAction.FETCH,
        "model-general-20": RestoreAction.REUSE,
    }
    plan.require_ready()


def test_preflight_refetches_corrupt_local_artifact_when_online():
    package = _package()
    plan = build_restore_preflight(
        package,
        {
            "model-general-20": "9" * 64,
            "memory-snapshot-13": "2" * 64,
        },
        online=True,
    )

    by_id = {item.artifact.artifact_id: item for item in plan.items}
    assert by_id["model-general-20"].action is RestoreAction.FETCH
    assert by_id["model-general-20"].reason == "local_hash_mismatch"
    assert plan.fetch_bytes == 4_000_000_000
    assert plan.ready is True


def test_offline_restore_fails_closed_when_required_artifact_is_missing():
    package = _package()
    plan = build_restore_preflight(
        package,
        {"model-general-20": "1" * 64},
        online=False,
    )

    assert plan.ready is False
    assert plan.blocked_required == ("memory-snapshot-13",)
    with pytest.raises(RuntimeError, match="memory-snapshot-13"):
        plan.require_ready()


def test_fetch_policy_can_block_restore_even_when_online():
    package = _package()
    plan = build_restore_preflight(package, {}, online=True, allow_fetch=False)

    assert plan.ready is False
    assert set(plan.blocked_required) == {"memory-snapshot-13", "model-general-20"}
    assert all(item.action is RestoreAction.BLOCKED for item in plan.items)


def test_restore_preflight_rejects_wrong_owner():
    with pytest.raises(PermissionError, match="expected owner"):
        build_restore_preflight(
            _package(),
            {},
            online=True,
            expected_owner_id="someone-else",
        )
