from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trust_continuity.future_extensions import GovernedFutureCapabilities
from trust_continuity.identity_continuity import MultiDeviceContinuity, UniversalOwnerRecovery
from trust_continuity.memory_intelligence import MemoryIntelligence
from trust_continuity.production import PhysicalL4Qualification, ProductionReadinessManager
from trust_continuity.services import EvaluationLab, OAuthLifecycleManager, OfflineIntelligence, TrustCenter
from trust_continuity.store import TrustContinuityStore
from trust_continuity.work_engine import WorkEngineV2


class FakeSecrets:
    def __init__(self):
        self.values = {}
        self.counter = 0

    def put(self, name, value):
        self.counter += 1
        handle = f"secret-{self.counter}"
        self.values[handle] = value
        return handle

    def get(self, handle):
        return self.values[handle]

    def delete(self, handle):
        self.values.pop(handle, None)


@pytest.fixture()
def store(tmp_path: Path):
    return TrustContinuityStore(tmp_path / "trust.sqlite3")


def test_production_readiness_is_fail_closed_until_external_evidence(store):
    manager = ProductionReadinessManager(store, commit_sha="a" * 40)
    manager.declare_software_check("campaign_tests", True)
    result = manager.readiness()
    assert result.software_ready is True
    assert result.production_ready is False
    assert "android_release_signing" in result.pending


def test_external_evidence_rejects_secrets(store):
    manager = ProductionReadinessManager(store, commit_sha="b" * 40)
    with pytest.raises(ValueError):
        manager.register_external_evidence(
            "android_release_signing",
            evidence_id="e1",
            provider="owner",
            artifact_digest="0" * 64,
            verified=True,
            metadata={"private_key": "do-not-store"},
        )


def test_l4_rejects_emulator_and_accepts_physical_evidence(store):
    l4 = PhysicalL4Qualification(store, commit_sha="c" * 40)
    metrics = {
        "battery": {"ok": True},
        "thermal": {"ok": True},
        "background_restrictions": {"ok": True},
        "permission_ui": {"ok": True},
        "disconnect_reconnect": {"ok": True},
    }
    with pytest.raises(ValueError):
        l4.record(
            device_id="emu-1",
            platform="android",
            provider_class="emulator",
            hardware_fingerprint="emulator",
            scenarios={"sensor": True},
            metrics=metrics,
            evidence_digest="1" * 64,
        )
    row = l4.record(
        device_id="phone-1",
        platform="android",
        provider_class="physical_device",
        hardware_fingerprint="hardware-model-serial-redacted",
        scenarios={"permissions": True, "camera_indicator": True, "gps": True},
        metrics=metrics,
        evidence_digest="2" * 64,
    )
    assert row["payload"]["qualification_level"] == "L4"


def test_owner_restore_has_no_master_device_dependency_and_revokes_lost_device(store):
    revoked = []
    recovery = UniversalOwnerRecovery(
        store,
        owner_authenticator=lambda owner, proof: owner == "owner-1" and proof == "valid-recovery-proof",
        register_device=lambda owner, metadata: "android-new" if owner == "owner-1" else "bad",
        revoke_device=revoked.append,
    )
    token = recovery.begin_restore("owner-1", method="recovery_code", destination_platform="android")
    result = recovery.complete_restore(
        token,
        owner_proof="valid-recovery-proof",
        device_metadata={"platform": "android"},
        lost_device_id="iphone-lost",
    )
    assert result.restored_device_id == "android-new"
    assert result.revoked_device_id == "iphone-lost"
    assert revoked == ["iphone-lost"]


def test_multi_device_continuity_enforces_all_data_policies(store):
    continuity = MultiDeviceContinuity(store, is_trusted_device=lambda device: device in {"a", "b"})
    local = continuity.create_task(owner_id="owner", device_id="a", title="local", data_policy="device_only")
    with pytest.raises(PermissionError):
        continuity.handoff(local, from_device="a", to_device="b")
    progress = continuity.create_task(owner_id="owner", device_id="a", title="progress", data_policy="progress_only")
    continuity.checkpoint(progress, device_id="a", state={"step": 3, "secret_context": "not-synced"}, online=False)
    row = store.get("continuity_task", progress)
    assert row["payload"]["checkpoint"] == {"step": 3}
    continuity.handoff(progress, from_device="a", to_device="b")
    on_demand = continuity.create_task(owner_id="owner", device_id="a", title="od", data_policy="on_demand")
    with pytest.raises(PermissionError):
        continuity.handoff(on_demand, from_device="a", to_device="b")
    continuity.handoff(on_demand, from_device="a", to_device="b", explicit_on_demand=True)


def test_work_engine_checkpoints_retries_budgets_and_approval(store):
    approved = set()
    engine = WorkEngineV2(store, approval_check=lambda job, step: (job, step["id"]) in approved)
    job = engine.create_job(
        owner_id="owner",
        title="deploy safely",
        steps=[
            {"id": "plan", "title": "plan"},
            {"id": "apply", "title": "apply", "depends_on": ["plan"], "requires_approval": True},
        ],
        max_retries=1,
        budget={"cost": 5},
    )
    assert engine.next_step(job)["id"] == "plan"
    engine.start_step(job, "plan")
    engine.checkpoint(job, "plan", {"percent": 50})
    engine.complete_step(job, "plan", cost={"cost": 1})
    blocked = engine.next_step(job)
    assert blocked["blocked"] == "approval_required"
    approved.add((job, "apply"))
    engine.start_step(job, "apply")
    engine.fail_step(job, "apply", error="temporary", retryable=True)
    engine.start_step(job, "apply")
    engine.complete_step(job, "apply", cost={"cost": 2})
    assert store.get("work_v2", job)["status"] == "completed"


def test_memory_provenance_contradictions_edit_forget_and_no_authority(store):
    memory = MemoryIntelligence(store)
    first = memory.remember(
        owner_id="owner",
        entity="Home Router",
        predicate="location",
        value="office",
        source={"kind": "owner", "message_id": "m1"},
        confidence=0.8,
    )
    second = memory.remember(
        owner_id="owner",
        entity="home   router",
        predicate="location",
        value="hall",
        source={"kind": "sensor", "observation_id": "o1"},
        confidence=0.6,
    )
    assert first in memory.why_known(second, owner_id="owner")["contradicts"]
    assert memory.why_known(first, owner_id="owner")["execution_authority"] is False
    replacement = memory.edit_fact(second, owner_id="owner", value="office", reason="owner corrected it")
    assert memory.why_known(replacement, owner_id="owner")["confidence"] == 1.0
    assert memory.forget(first, owner_id="owner") is True


def test_oauth_pkce_refresh_scope_and_revoke(store):
    secrets_store = FakeSecrets()
    oauth = OAuthLifecycleManager(store, secrets_store)
    start = oauth.begin(
        owner_id="owner",
        provider="example",
        account_hint="me@example.test",
        scopes=["mail.read"],
        redirect_uri="https://localhost.example/callback",
    )
    flow = store.get("oauth_flow", start["flow_id"])
    verifier = secrets_store.get(flow["payload"]["verifier_handle"])
    connection = oauth.complete(
        start["flow_id"],
        owner_id="owner",
        state=start["state"],
        authorization_code="code",
        exchange=lambda code, got_verifier, redirect: {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "scopes": ["mail.read"],
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "provider_verified": True,
        },
    )
    with pytest.raises(PermissionError):
        oauth.access_token(connection, owner_id="owner", required_scope="mail.write")
    token = oauth.access_token(
        connection,
        owner_id="owner",
        required_scope="mail.read",
        refresh=lambda refresh_token: {
            "access_token": "access-2",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    assert token == "access-2"
    revoked = []
    oauth.revoke(connection, owner_id="owner", provider_revoke=revoked.append)
    assert revoked == ["access-2"]


def test_offline_routing_and_reconciliation(store):
    offline = OfflineIntelligence(store)
    offline.register_capability(device_id="phone", name="local-ocr", kind="ocr", model="native", available=True, quality=0.9)
    assert offline.route(device_id="phone", kind="ocr", allow_cloud=False)["route"] == "local"
    task = offline.enqueue(owner_id="owner", device_id="phone", task_type="work", payload={"step": 2, "local": True})
    result = offline.reconcile(task, remote_version={"step": 1, "remote": True}, policy="merge_progress")
    assert result["resolved"]["step"] == 2
    assert result["resolved"]["remote"] is True


def test_trust_center_delegates_emergency_controls(store):
    calls = []
    center = TrustCenter(
        store,
        stop_sensing=lambda: calls.append("sense"),
        stop_actions=lambda: calls.append("actions"),
        revoke_device=lambda device: calls.append(f"revoke:{device}"),
        disconnect_provider=lambda provider: calls.append(f"disconnect:{provider}"),
        emergency_stop=lambda enabled: calls.append(f"emergency:{enabled}"),
        snapshot_sources={"devices": lambda: [{"id": "phone"}]},
    )
    center.stop_sensing(actor="owner")
    center.stop_actions(actor="owner")
    center.revoke_device("phone", actor="owner")
    center.disconnect_provider("oauth-1", actor="owner")
    center.emergency_stop(True, actor="owner")
    assert center.snapshot()["devices"] == [{"id": "phone"}]
    assert calls == ["sense", "actions", "revoke:phone", "disconnect:oauth-1", "emergency:True"]


def test_evaluation_lab_is_exact_sha_and_future_capabilities_never_gain_authority(store):
    lab = EvaluationLab(store, commit_sha="d" * 40)
    score = lab.record(
        suite="release",
        metrics={"task_success": 0.95, "hallucination_rate": 0.01, "privacy_violations": 0},
        thresholds={"task_success": {"min": 0.9}, "hallucination_rate": {"max": 0.05}, "privacy_violations": {"max": 0}},
    )
    assert score["passed"] is True
    assert score["commit_sha"] == "d" * 40
    future = GovernedFutureCapabilities(store, approval_check=lambda _proposal: True)
    proposal = future.propose(owner_id="owner", kind="robotics", description="observe and propose a robot movement", required_authorities=["device:robotics"])
    assert proposal.execution_authority is False
    future.mark_tested(proposal.proposal_id, owner_id="owner", evidence={"simulation": "passed"})
    activated = future.authorize_for_existing_runtime(proposal.proposal_id, owner_id="owner")
    assert activated["payload"]["execution_authority"] is False
