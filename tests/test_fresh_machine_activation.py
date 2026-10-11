from __future__ import annotations

from hashlib import sha256
import json

import pytest

from models.fresh_machine_activation import (
    FreshMachineActivationService,
    RuntimeActivationProof,
)
from models.hardware_profile import HardwareProfile
from models.intelligence_restore import IntelligenceRestorePackage, RestoreArtifact, RestoreArtifactKind
from models.portable_intelligence import (
    ExecutionTarget,
    FilesystemIntelligenceManifestStore,
    IntelligenceManifest,
    ModelTier,
    RuntimeCandidate,
)


class ReadyBackend:
    def __init__(self, *, runtime_id: str | None = None, model_ref: str | None = None, ready: bool = True) -> None:
        self.runtime_id = runtime_id
        self.model_ref = model_ref
        self.ready = ready
        self.calls = 0

    def activate(self, candidate, *, manifest, local_artifacts):
        self.calls += 1
        return RuntimeActivationProof(
            ready=self.ready,
            runtime_id=self.runtime_id or candidate.runtime_id,
            model_ref=self.model_ref or candidate.model_ref,
            detail="ready" if self.ready else "startup_failed",
        )


def _hardware(*, online: bool = False, ram_gb: float = 16.0) -> HardwareProfile:
    return HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=8,
        ram_gb=ram_gb,
        disk_free_gb=100.0,
        accelerator="none",
        online=online,
    )


def _local() -> RuntimeCandidate:
    return RuntimeCandidate(
        runtime_id="local-small",
        model_ref="vishnu-small-v1",
        tier=ModelTier.SMALL,
        target=ExecutionTarget.LOCAL,
        minimum_ram_gb=8.0,
    )


def _remote() -> RuntimeCandidate:
    return RuntimeCandidate(
        runtime_id="remote-large",
        model_ref="vishnu-large-v3",
        tier=ModelTier.LARGE,
        target=ExecutionTarget.REMOTE,
    )


def _state(tmp_path, *, runtime_policy=None, with_artifact: bool = True):
    manifest = IntelligenceManifest.create(
        owner_id="owner-1",
        core_version="1.0",
        runtime_policy=runtime_policy or {},
        created_at="2026-10-11T00:00:00+00:00",
    )
    artifacts = ()
    local = {}
    if with_artifact:
        data = b"verified-local-model"
        digest = sha256(data).hexdigest()
        artifact = RestoreArtifact(
            name="model",
            artifact_id="model-v1",
            version="1",
            sha256=digest,
            locator="vault://sha256/" + digest,
            kind=RestoreArtifactKind.MODEL,
            required=True,
            size_bytes=len(data),
        )
        artifacts = (artifact,)
        local = {artifact.artifact_id: artifact.sha256}
    package = IntelligenceRestorePackage.create(
        manifest=manifest,
        artifacts=artifacts,
        owner_id="owner-1",
        created_at="2026-10-11T00:01:00+00:00",
    )
    store = FilesystemIntelligenceManifestStore(tmp_path / "data")
    return store, manifest, package, local


def test_exact_restored_manifest_artifacts_and_runtime_can_activate(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    backend = ReadyBackend()
    service = FreshMachineActivationService(store, backend)

    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    assert preflight.ready is True
    assert preflight.runtime_selection.candidate.runtime_id == "local-small"

    receipt = service.activate(preflight=preflight, restore_package=package)
    assert backend.calls == 1
    assert receipt.manifest_id == manifest.manifest_id
    assert receipt.runtime_id == "local-small"
    assert service.status()["activated"] is True


def test_missing_restored_active_manifest_blocks(tmp_path):
    store, _, package, local = _state(tmp_path)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    assert preflight.ready is False
    assert "restored_manifest_missing" in {item.code for item in preflight.blockers}


def test_wrong_restored_active_manifest_blocks(tmp_path):
    store, _, package, local = _state(tmp_path)
    other = IntelligenceManifest.create(
        owner_id="owner-1",
        core_version="2.0",
        created_at="2026-10-11T00:02:00+00:00",
    )
    store.activate(other)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    assert preflight.ready is False
    assert "restored_manifest_mismatch" in {item.code for item in preflight.blockers}


def test_missing_required_artifact_blocks_activation(tmp_path):
    store, manifest, package, _ = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts={},
    )
    assert preflight.ready is False
    assert "required_artifact_not_verified" in {item.code for item in preflight.blockers}


def test_local_only_policy_rejects_remote_only_runtime(tmp_path):
    store, manifest, package, local = _state(tmp_path, runtime_policy={"local_only": True}, with_artifact=False)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(online=True),
        runtime_candidates=(_remote(),),
        local_artifacts=local,
    )
    assert preflight.ready is False
    assert "no_feasible_runtime" in {item.code for item in preflight.blockers}


def test_online_machine_can_select_stronger_remote_runtime_when_policy_allows(tmp_path):
    store, manifest, package, local = _state(tmp_path, with_artifact=False)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(online=True),
        runtime_candidates=(_local(), _remote()),
        local_artifacts=local,
    )
    assert preflight.ready is True
    assert preflight.runtime_selection.candidate.runtime_id == "remote-large"


def test_maximum_tier_policy_caps_runtime_selection(tmp_path):
    store, manifest, package, local = _state(tmp_path, runtime_policy={"maximum_tier": "small"}, with_artifact=False)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(online=True),
        runtime_candidates=(_local(), _remote()),
        local_artifacts=local,
    )
    assert preflight.ready is True
    assert preflight.runtime_selection.candidate.runtime_id == "local-small"


def test_runtime_backend_must_prove_exact_runtime_and_model(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend(runtime_id="wrong-runtime"))
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    with pytest.raises(RuntimeError, match="runtime id mismatch"):
        service.activate(preflight=preflight, restore_package=package)

    service = FreshMachineActivationService(store, ReadyBackend(model_ref="wrong-model"))
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    with pytest.raises(RuntimeError, match="model ref mismatch"):
        service.activate(preflight=preflight, restore_package=package)


def test_runtime_backend_not_ready_does_not_write_receipt(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend(ready=False))
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    with pytest.raises(RuntimeError, match="startup_failed"):
        service.activate(preflight=preflight, restore_package=package)
    assert service.receipt_path.exists() is False


def test_manifest_change_after_preflight_fails_closed(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    other = IntelligenceManifest.create(
        owner_id="owner-1",
        core_version="2.0",
        created_at="2026-10-11T00:03:00+00:00",
    )
    store.activate(other)

    with pytest.raises(RuntimeError, match="changed after activation preflight"):
        service.activate(preflight=preflight, restore_package=package)


def test_activation_receipt_tampering_is_detected(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    preflight = service.preflight(
        owner_id="owner-1",
        restore_package=package,
        hardware=_hardware(),
        runtime_candidates=(_local(),),
        local_artifacts=local,
    )
    service.activate(preflight=preflight, restore_package=package)

    payload = json.loads(service.receipt_path.read_text(encoding="utf-8"))
    payload["model_ref"] = "tampered-model"
    service.receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        service.load_receipt()


def test_owner_mismatch_is_rejected_before_activation_planning(tmp_path):
    store, manifest, package, local = _state(tmp_path)
    store.activate(manifest)
    service = FreshMachineActivationService(store, ReadyBackend())
    with pytest.raises(PermissionError, match="owner"):
        service.preflight(
            owner_id="owner-2",
            restore_package=package,
            hardware=_hardware(),
            runtime_candidates=(_local(),),
            local_artifacts=local,
        )
