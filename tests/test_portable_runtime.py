from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.hardware_profile import HardwareProfile
from models.portable_intelligence import IntelligenceManifest
from models.portable_runtime import PortableIntelligenceRuntime, runtime_candidates_from_manifest
from models.router import Provider


class FakeResponse:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeRouter:
    def __init__(self, *, privacy: str = "local_only") -> None:
        self.providers = {
            "self_hosted": Provider(
                id="self_hosted",
                base_url="http://127.0.0.1:11434/v1",
                api_key="",
                model="vishnu-small-v1",
                private=True,
                capabilities=("chat",),
                cost_rank=1,
                latency_rank=1,
            )
        }
        self.owner_privacy = privacy
        self.disabled = set()
        self.owner_allowed = ()
        self.health_timeout = 1.0
        self.requests = []

    def _request(self, provider, method, path, *, timeout=None, **kwargs):
        self.requests.append((provider.id, method, path, timeout))
        return FakeResponse()


class FixedHardwareProfiler:
    def probe(self, path=".", *, online=False):
        return HardwareProfile(
            platform="linux",
            architecture="x86_64",
            cpu_logical_cores=8,
            ram_gb=16.0,
            disk_free_gb=100.0,
            accelerator="none",
            online=bool(online),
        )


def _runtime(tmp_path, *, privacy="local_only"):
    router = FakeRouter(privacy=privacy)
    settings = SimpleNamespace(
        local_ai_model_tier="small",
        local_ai_min_ram_gb=1.0,
        local_ai_min_vram_gb=0.0,
    )
    runtime = PortableIntelligenceRuntime(
        tmp_path,
        model_router=router,
        settings=settings,
        vault_persistent=True,
    )
    runtime.hardware = FixedHardwareProfiler()
    return runtime, router


def test_runtime_candidate_catalog_is_authenticated_and_strict():
    manifest = IntelligenceManifest.create(
        owner_id="owner",
        core_version="1",
        runtime_policy={
            "runtime_candidates": [
                {
                    "runtime_id": "self_hosted",
                    "model_ref": "vishnu-small-v1",
                    "tier": "small",
                    "target": "local",
                    "minimum_ram_gb": 8,
                    "minimum_vram_gb": 0,
                    "enabled": True,
                }
            ]
        },
        created_at="2026-10-11T00:00:00+00:00",
    )
    candidates = runtime_candidates_from_manifest(manifest)
    assert len(candidates) == 1
    assert candidates[0].runtime_id == "self_hosted"
    assert candidates[0].model_ref == "vishnu-small-v1"

    bad = IntelligenceManifest.create(
        owner_id="owner",
        core_version="1",
        runtime_policy={
            "runtime_candidates": [
                {
                    "runtime_id": "self_hosted",
                    "model_ref": "vishnu-small-v1",
                    "tier": "small",
                    "target": "local",
                    "unexpected": "no",
                }
            ]
        },
        created_at="2026-10-11T00:00:01+00:00",
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        runtime_candidates_from_manifest(bad)


def test_publish_restore_package_offline_pack_and_activate_round_trip(tmp_path):
    runtime, router = _runtime(tmp_path)

    package = runtime.publish_current_restore_package(core_version="test-revision")
    package.verify()
    active = runtime.active_restore_package()
    assert active is not None
    assert active.package_id == package.package_id
    assert active.manifest.manifest_id == runtime.manifests.active().manifest_id
    assert active.manifest.runtime_policy["local_only"] is True

    candidates = runtime.runtime_candidates()
    assert len(candidates) == 1
    assert candidates[0].runtime_id == "self_hosted"
    assert candidates[0].model_ref == "vishnu-small-v1"

    offline = runtime.prepare_offline_pack()
    assert offline.manifest.restore_package_id == package.package_id
    assert offline.manifest.runtime_id == "self_hosted"
    assert offline.local_artifacts == {}

    preflight = runtime.activation_preflight(online=False)
    assert preflight.ready is True
    assert preflight.runtime_selection.candidate.runtime_id == "self_hosted"

    receipt = runtime.activate(online=False)
    assert receipt.runtime_id == "self_hosted"
    assert receipt.model_ref == "vishnu-small-v1"
    assert router.requests[-1][1:3] == ("GET", "/models")
    assert runtime.activation.status()["activated"] is True

    status = runtime.status()
    assert status["offline_readiness"]["ready"] is True
    assert status["offline_pack_available"] is True
    assert status["vault"]["production_durable"] is True
    assert status["model_execution_authority"] == "models.GovernedModelRouter"


def test_local_only_manifest_does_not_gain_remote_authority(tmp_path):
    runtime, _ = _runtime(tmp_path, privacy="local_only")
    package = runtime.publish_current_restore_package(core_version="test-revision")
    assert package.manifest.runtime_policy["local_only"] is True
    preflight = runtime.activation_preflight(online=True)
    assert preflight.ready is True
    assert preflight.runtime_selection.candidate.target.value == "local"


def test_tampered_active_restore_pointer_fails_closed(tmp_path):
    runtime, _ = _runtime(tmp_path)
    runtime.publish_current_restore_package(core_version="test-revision")
    runtime.active_package_path.write_text(
        '{"schema_version":1,"package_id":"virp-' + ('0' * 64) + '","fingerprint":"bad"}',
        encoding="utf-8",
    )
    with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
        runtime.active_restore_package()


def test_activation_proof_rejects_provider_model_drift(tmp_path):
    runtime, router = _runtime(tmp_path)
    runtime.publish_current_restore_package(core_version="test-revision")
    router.providers["self_hosted"] = Provider(
        id="self_hosted",
        base_url="http://127.0.0.1:11434/v1",
        api_key="",
        model="different-model",
        private=True,
        capabilities=("chat",),
        cost_rank=1,
        latency_rank=1,
    )
    preflight = runtime.activation_preflight(online=False)
    assert preflight.ready is True
    with pytest.raises(RuntimeError, match="runtime_model_mismatch"):
        runtime.activate(online=False)
