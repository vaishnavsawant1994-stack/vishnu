from __future__ import annotations

import json

import pytest

from models.portable_intelligence import (
    DeviceCapabilities,
    ExecutionTarget,
    FilesystemIntelligenceManifestStore,
    IntelligenceManifest,
    IntelligenceReference,
    ModelTier,
    RuntimeCandidate,
    select_runtime,
)


def _reference(name: str, version: str = "1") -> IntelligenceReference:
    return IntelligenceReference(
        name=name,
        ref_id=f"{name}-{version}",
        version=version,
        sha256="a" * 64,
    )


def _manifest(*, created_at: str = "2026-10-11T00:00:00+00:00") -> IntelligenceManifest:
    return IntelligenceManifest.create(
        owner_id="owner-test",
        core_version="8.4.0",
        models=(_reference("general", "18"), _reference("coding", "23")),
        agents=(_reference("coding-agent", "31"), _reference("research-agent", "21")),
        schemas={"memory": "12", "knowledge": "9"},
        registries={"skills": "19", "training": "28"},
        runtime_policy={"local_only": False, "family": "vishnu-20"},
        created_at=created_at,
    )


def test_manifest_is_deterministic_and_tamper_evident():
    first = _manifest()
    second = IntelligenceManifest.create(
        owner_id="owner-test",
        core_version="8.4.0",
        models=(_reference("coding", "23"), _reference("general", "18")),
        agents=(_reference("research-agent", "21"), _reference("coding-agent", "31")),
        schemas={"knowledge": "9", "memory": "12"},
        registries={"training": "28", "skills": "19"},
        runtime_policy={"family": "vishnu-20", "local_only": False},
        created_at="2026-10-11T00:00:00+00:00",
    )

    assert first.manifest_id == second.manifest_id
    assert first.fingerprint == second.fingerprint
    assert first.public() == second.public()

    tampered = first.public()
    tampered["models"][0]["version"] = "999"
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        IntelligenceManifest.from_dict(tampered)


def test_manifest_rejects_invalid_or_duplicate_references():
    with pytest.raises(ValueError, match="sha256"):
        IntelligenceReference(name="general", ref_id="model", version="1", sha256="bad")

    duplicate = _reference("general")
    with pytest.raises(ValueError, match="unique"):
        IntelligenceManifest.create(
            owner_id="owner-test",
            core_version="1",
            models=(duplicate, duplicate),
        )


def test_manifest_store_keeps_immutable_history_and_atomic_active_pointer(tmp_path):
    store = FilesystemIntelligenceManifestStore(tmp_path)
    first = _manifest()
    second = IntelligenceManifest.create(
        owner_id="owner-test",
        core_version="8.5.0",
        models=(_reference("general", "19"),),
        created_at="2026-10-12T00:00:00+00:00",
    )

    assert store.active() is None
    store.activate(first)
    assert store.active() == first
    assert store.load(first.manifest_id) == first

    store.activate(second)
    assert store.active() == second
    assert store.load(first.manifest_id) == first
    assert store.load(second.manifest_id) == second


def test_manifest_store_detects_active_pointer_tampering(tmp_path):
    store = FilesystemIntelligenceManifestStore(tmp_path)
    manifest = store.activate(_manifest())
    pointer = json.loads(store.active_path.read_text(encoding="utf-8"))
    pointer["fingerprint"] = "0" * 64
    store.active_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(RuntimeError, match="pointer fingerprint mismatch"):
        store.active()
    assert store.load(manifest.manifest_id) == manifest


def _runtimes() -> tuple[RuntimeCandidate, ...]:
    return (
        RuntimeCandidate(
            runtime_id="mobile-local",
            model_ref="vishnu-mobile-20",
            tier=ModelTier.MOBILE,
            target=ExecutionTarget.LOCAL,
            minimum_ram_gb=4,
        ),
        RuntimeCandidate(
            runtime_id="medium-local",
            model_ref="vishnu-medium-20",
            tier=ModelTier.MEDIUM,
            target=ExecutionTarget.LOCAL,
            minimum_ram_gb=24,
            minimum_vram_gb=12,
        ),
        RuntimeCandidate(
            runtime_id="large-local",
            model_ref="vishnu-large-20",
            tier=ModelTier.LARGE,
            target=ExecutionTarget.LOCAL,
            minimum_ram_gb=48,
            minimum_vram_gb=24,
        ),
        RuntimeCandidate(
            runtime_id="large-remote",
            model_ref="vishnu-large-20",
            tier=ModelTier.LARGE,
            target=ExecutionTarget.REMOTE,
        ),
    )


def test_phone_uses_remote_large_model_online_but_local_mobile_offline():
    online_phone = DeviceCapabilities(ram_gb=8, online=True, accelerator="mobile-npu", platform="ios")
    offline_phone = DeviceCapabilities(ram_gb=8, online=False, accelerator="mobile-npu", platform="ios")

    online = select_runtime(_runtimes(), online_phone)
    offline = select_runtime(_runtimes(), offline_phone)

    assert online.candidate.runtime_id == "large-remote"
    assert offline.candidate.runtime_id == "mobile-local"
    assert "offline" in offline.reason_codes


def test_local_only_never_selects_remote_model():
    phone = DeviceCapabilities(ram_gb=8, online=True, platform="ios")

    selection = select_runtime(_runtimes(), phone, local_only=True)

    assert selection.candidate.runtime_id == "mobile-local"
    assert selection.candidate.target is ExecutionTarget.LOCAL
    assert "local_only_enforced" in selection.reason_codes


def test_powerful_workstation_prefers_equivalent_local_large_model():
    workstation = DeviceCapabilities(
        ram_gb=64,
        gpu_vram_gb=24,
        online=True,
        accelerator="nvidia",
        platform="linux",
    )

    selection = select_runtime(_runtimes(), workstation)

    assert selection.candidate.runtime_id == "large-local"
    assert "gpu_capable" in selection.reason_codes


def test_runtime_selection_can_cap_model_family_tier():
    workstation = DeviceCapabilities(ram_gb=64, gpu_vram_gb=24, online=True)

    selection = select_runtime(_runtimes(), workstation, maximum_tier=ModelTier.MEDIUM)

    assert selection.candidate.runtime_id == "medium-local"


def test_local_only_fails_closed_when_device_cannot_run_any_local_model():
    tiny_device = DeviceCapabilities(ram_gb=2, online=True)

    with pytest.raises(RuntimeError, match="no feasible local runtime"):
        select_runtime(_runtimes(), tiny_device, local_only=True)
