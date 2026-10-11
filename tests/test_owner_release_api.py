from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass
from future_intelligence.release_control.controller import GovernedReleaseController
from future_intelligence.release_control.policy_store import ReleasePolicyStore
from future_intelligence.release_control.runtime import ReleaseControlRuntime
from future_intelligence.release_control.store import JsonReleaseStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.owner_release_api import owner_release_router
from server.owner_release_ui import JS as OWNER_RELEASE_JS


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


class FakeAutomation:
    def active_release_ids(self):
        return ()


def runtime(tmp_path):
    policy_store = ReleasePolicyStore(tmp_path / "release-policy.json")
    store = JsonReleaseStore(tmp_path / "releases")
    controller = GovernedReleaseController(store=store, policy=policy_store.snapshot())
    release_control = ReleaseControlRuntime(controller=controller, policy_store=policy_store, providers={})
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


def seed_release(value):
    plan = ReleasePlan(
        id="release-owner-1",
        work_order_id="work-owner-1",
        attempt_id="attempt-owner-1",
        engineering_spec_id="spec-owner-1",
        repository="owner/repo",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        qualification_digest="digest-owner-1",
        provider="render",
        target="owner/repo",
        risk_class=ReleaseRiskClass.HIGH,
        affected_surfaces=("authentication",),
        approval_required=True,
    )
    value["release_control"].controller.store.save(plan)
    return plan


def test_owner_release_summary_requires_trusted_admin_device(tmp_path):
    value = runtime(tmp_path)
    app = app_for(value)
    anonymous = TestClient(app)
    assert anonymous.get("/iphone/api/owner/release/summary").status_code == 401

    client = owner_client(app)
    response = client.get("/iphone/api/owner/release/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["policy"]["mode"] == "approval_required"
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


def test_owner_release_approval_is_bound_to_existing_release_and_fresh_owner(tmp_path):
    value = runtime(tmp_path)
    plan = seed_release(value)
    client = owner_client(app_for(value, fresh=True))

    missing = client.post("/iphone/api/owner/release/not-a-release/approve")
    assert missing.status_code in {404, 409}

    response = client.post(f"/iphone/api/owner/release/{plan.id}/approve")
    assert response.status_code == 200
    release = response.json()["release"]
    assert release["candidate_revision"] == "b" * 40
    assert release["approved_by"] == "device:owner-device"


def test_owner_release_surface_has_no_arbitrary_plan_creation_route(tmp_path):
    value = runtime(tmp_path)
    client = owner_client(app_for(value, fresh=True))
    response = client.post(
        "/iphone/api/owner/release",
        json={"candidate_revision": "c" * 40, "repository": "attacker/repo", "provider": "render"},
    )
    assert response.status_code in {404, 405}


def test_owner_release_ui_exposes_governed_actions_and_no_sha_input():
    for label in ("Preview", "Approve", "Promote", "Rollback", "Cancel"):
        assert label in OWNER_RELEASE_JS
    assert "Release Control" in OWNER_RELEASE_JS
    assert "candidate_revision" not in OWNER_RELEASE_JS
    assert "repository" not in OWNER_RELEASE_JS.lower() or "data-release-repository-input" not in OWNER_RELEASE_JS
    assert "create release" not in OWNER_RELEASE_JS.lower()
