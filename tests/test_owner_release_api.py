from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from future_intelligence.engineering.canary import CanaryMetrics
from future_intelligence.engineering.contracts import (
    EngineeringSpec,
    QualificationGateResult,
    QualificationGateStatus,
    QualificationReport,
)
from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control.controller import GovernedReleaseController
from future_intelligence.release_control.policy_store import ReleasePolicyStore
from future_intelligence.release_control.providers import InMemoryReleaseProvider
from future_intelligence.release_control.runtime import ReleaseControlRuntime
from future_intelligence.release_control.store import InMemoryReleaseStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.owner_release_api import owner_release_router
from server.owner_release_ui import JS as OWNER_RELEASE_JS


BASE = "a" * 40
CANDIDATE = "b" * 40


class FakeRegistry:
    def authenticate(self, device_id, token):
        return device_id == "owner-device" and token == "owner-token"

    def is_active(self, device_id):
        return device_id == "owner-device"

    def authorize(self, device_id, scope):
        return device_id == "owner-device" and scope == "device:admin"


class FakeEvents:
    def __init__(self):
        self.rows = []

    def emit(self, name, **payload):
        self.rows.append((name, payload))


class HealthyEnvironment:
    def qualify_preview(self, *, target, spec_id, candidate_revision):
        return EnvironmentQualificationResult(
            environment="preview",
            target=target,
            healthy=True,
            checks={"revision": candidate_revision == CANDIDATE},
            evidence=("preview://healthy",),
            summary="preview healthy",
        )

    def smoke_production(self, *, target, release_revision):
        return EnvironmentQualificationResult(
            environment="production",
            target=target,
            healthy=True,
            checks={"revision": release_revision == CANDIDATE},
            evidence=("production://healthy",),
            summary="production healthy",
        )


class FakeAutomation:
    def active_release_ids(self):
        return ()


def engineering_spec(*, surfaces=("pwa/home",)):
    return EngineeringSpec(
        id="spec-release-api",
        work_order_id="work-release-api",
        attempt_id="attempt-release-api",
        repository="owner/repo",
        base_revision=BASE,
        objective="Release qualified owner API candidate",
        affected_surfaces=tuple(surfaces),
    )


def qualification_report():
    return QualificationReport(
        spec_id="spec-release-api",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        gates=(QualificationGateResult(
            gate="requirements",
            status=QualificationGateStatus.PASS,
            summary="passed",
            evidence=("ci://exact",),
        ),),
        reviewer="independent-reviewer",
        review_decision="approved",
    )


def runtime(tmp_path):
    provider = InMemoryReleaseProvider()
    policy_store = ReleasePolicyStore(tmp_path / "release-policy.json")
    environment = HealthyEnvironment()
    controller = GovernedReleaseController(
        store=InMemoryReleaseStore(),
        policy=policy_store.snapshot(),
        preview_qualifier=environment,
        production_smoke=environment,
    )
    release_control = ReleaseControlRuntime(
        controller=controller,
        policy_store=policy_store,
        providers={provider.name: provider},
    )
    return {
        "device_registry": FakeRegistry(),
        "events": FakeEvents(),
        "release_control": release_control,
        "release_automation": FakeAutomation(),
        "pwa_sessions": object(),
        "agent_executor": SimpleNamespace(reauth_ttl_seconds=300),
    }


def app_for(runtime_value, *, fresh=False):
    app = FastAPI()
    if fresh:
        @app.middleware("http")
        async def trusted_request(request, call_next):
            token = set_trusted_request(TrustedRequestContext(
                device_id="owner-device",
                session_id="session-release",
                reauthenticated_at=time.time(),
            ))
            try:
                return await call_next(request)
            finally:
                reset_trusted_request(token)
    app.include_router(owner_release_router(runtime_value))
    return app


def owner_client(app):
    client = TestClient(app)
    client.cookies.set("pa_device", "owner-device")
    client.cookies.set("pa_token", "owner-token")
    return client


def seed_release(value, *, surfaces=("pwa/home",)):
    return value["release_control"].controller.create_plan(
        spec=engineering_spec(surfaces=surfaces),
        report=qualification_report(),
        provider="memory",
        target="vishnu-production",
    )


def test_owner_release_summary_requires_trusted_admin_device(tmp_path):
    value = runtime(tmp_path)
    app = app_for(value)
    assert TestClient(app).get("/iphone/api/owner/release/summary").status_code == 401

    response = owner_client(app).get("/iphone/api/owner/release/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["policy"]["mode"] == "approval_required"
    assert payload["providers"] == ["memory"]
    assert payload["authorities"]["release_plan_creation_from_api"] is False
    assert payload["authorities"]["automatic_rollback"] is False
    assert payload["authorities"]["body_activation"] is False


def test_owner_release_policy_change_requires_fresh_owner_verification(tmp_path):
    value = runtime(tmp_path)
    stale = owner_client(app_for(value, fresh=False))
    denied = stale.patch("/iphone/api/owner/release/policy", json={"mode": "auto_low_risk"})
    assert denied.status_code == 401
    assert denied.json()["detail"]["code"] == "reauthentication_required"

    fresh = owner_client(app_for(value, fresh=True))
    allowed = fresh.patch(
        "/iphone/api/owner/release/policy",
        json={"mode": "auto_low_risk", "automatic_risk_ceiling": "low", "allow_automatic_rollback": False},
    )
    assert allowed.status_code == 200
    policy = allowed.json()["policy"]
    assert policy["mode"] == "auto_low_risk"
    assert policy["automatic_risk_ceiling"] == "low"
    assert policy["allow_automatic_rollback"] is False


def test_owner_release_surface_has_no_arbitrary_plan_creation_route(tmp_path):
    value = runtime(tmp_path)
    response = owner_client(app_for(value, fresh=True)).post(
        "/iphone/api/owner/release",
        json={"candidate_revision": "c" * 40, "repository": "attacker/repo", "provider": "memory"},
    )
    assert response.status_code in {404, 405}


def test_sensitive_release_requires_explicit_owner_approval_before_promotion(tmp_path):
    value = runtime(tmp_path)
    value["release_control"].update_policy(mode="auto_low_risk")
    plan = seed_release(value, surfaces=("authentication/session",))
    client = owner_client(app_for(value, fresh=True))

    preview = client.post(f"/iphone/api/owner/release/{plan.id}/preview")
    assert preview.status_code == 200
    denied = client.post(f"/iphone/api/owner/release/{plan.id}/promote")
    assert denied.status_code == 409

    approved = client.post(f"/iphone/api/owner/release/{plan.id}/approve")
    assert approved.status_code == 200
    assert approved.json()["release"]["approved_by"] == "device:owner-device"
    promoted = client.post(f"/iphone/api/owner/release/{plan.id}/promote")
    assert promoted.status_code == 200
    assert promoted.json()["release"]["status"] == "monitoring"


def test_rollback_requires_literal_confirmation_and_separate_policy_authority(tmp_path):
    value = runtime(tmp_path)
    control = value["release_control"]
    control.update_policy(mode="auto_low_risk")
    plan = seed_release(value)
    client = owner_client(app_for(value, fresh=True))
    assert client.post(f"/iphone/api/owner/release/{plan.id}/preview").status_code == 200
    assert client.post(f"/iphone/api/owner/release/{plan.id}/promote").status_code == 200
    control.controller.record_canary(
        plan.id,
        baseline=CanaryMetrics(100, 0.01, 100),
        candidate=CanaryMetrics(100, 0.25, 300),
    )

    assert client.post(f"/iphone/api/owner/release/{plan.id}/rollback", json={"confirm": False}).status_code == 422
    denied = client.post(f"/iphone/api/owner/release/{plan.id}/rollback", json={"confirm": True})
    assert denied.status_code == 409

    control.update_policy(allow_automatic_rollback=True)
    allowed = client.post(f"/iphone/api/owner/release/{plan.id}/rollback", json={"confirm": True})
    assert allowed.status_code == 200
    assert allowed.json()["release"]["status"] == "rolled_back"


def test_owner_release_ui_exposes_governed_modes_and_explicit_rollback_boundary():
    for label in ("Off", "Preview only", "Approval required", "Auto low-risk"):
        assert label in OWNER_RELEASE_JS
    for label in ("Preview", "Approve", "Promote", "Rollback", "Cancel"):
        assert label in OWNER_RELEASE_JS
    assert "Exact SHA bound" in OWNER_RELEASE_JS
    assert "silently roll production back" in OWNER_RELEASE_JS
    assert "No Body activation" in OWNER_RELEASE_JS
    assert "create release" not in OWNER_RELEASE_JS.lower()
