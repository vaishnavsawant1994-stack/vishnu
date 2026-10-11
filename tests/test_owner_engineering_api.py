from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from future_intelligence.engineering.owner_policy import EngineeringOwnerPolicyStore
from future_intelligence.work_orchestration import (
    DurableWorkStore,
    GoalSpec,
    ResourceScope,
    WorkOrder,
    WorkOrderStatus,
    WorkPlan,
)
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.owner_engineering_api import owner_engineering_router
from server.owner_engineering_ui import JS as OWNER_ENGINEERING_JS


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


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, work_order_id, **kwargs):
        self.calls.append((work_order_id, kwargs))
        return SimpleNamespace(status="verifying", candidate_revision="b" * 40)


def runtime(tmp_path, *, with_executor=True):
    store = DurableWorkStore(tmp_path / "work.sqlite3")
    policy = EngineeringOwnerPolicyStore(tmp_path / "engineering-owner-policy.json")
    engineering = SimpleNamespace(
        owner_policy=policy,
        repository_provider=SimpleNamespace(repository="owner/repo"),
        work_store=store,
    )
    return {
        "device_registry": FakeRegistry(),
        "events": FakeEvents(),
        "engineering": engineering,
        "engineering_executor": FakeExecutor() if with_executor else None,
        "engineering_finalizer": object(),
        "pwa_sessions": object(),
        "agent_executor": SimpleNamespace(reauth_ttl_seconds=300),
        "code_worker_epoch": 7,
    }


def app_for(runtime_value, *, fresh=False):
    app = FastAPI()
    if fresh:
        @app.middleware("http")
        async def trusted_request(request, call_next):
            token = set_trusted_request(TrustedRequestContext(
                device_id="owner-device",
                session_id="session-1",
                reauthenticated_at=time.time(),
            ))
            try:
                return await call_next(request)
            finally:
                reset_trusted_request(token)
    app.include_router(owner_engineering_router(runtime_value))
    return app


def owner_client(app):
    client = TestClient(app)
    client.cookies.set("pa_device", "owner-device")
    client.cookies.set("pa_token", "owner-token")
    return client


def seed_scoped_work(store: DurableWorkStore):
    goal = GoalSpec(id="goal-owner-eng", title="Owner engineering", objective="Modify scoped source", desired_outcome="Candidate")
    store.upsert_goal(goal)
    order = WorkOrder(
        id="work-owner-eng",
        plan_id="plan-owner-eng",
        title="Scoped engineering",
        objective="Modify scoped source",
        worker_type="software_engineer",
        status=WorkOrderStatus.QUEUED,
        resource_scope=ResourceScope(allowed_repositories=("owner/repo",), allowed_paths=("src/",)),
    )
    store.save_plan(WorkPlan(id="plan-owner-eng", goal_id=goal.id, version=1, summary="Scoped plan", work_orders=(order,)))
    return order


def test_owner_engineering_summary_requires_trusted_admin_device(tmp_path):
    value = runtime(tmp_path)
    app = app_for(value)
    anonymous = TestClient(app)
    assert anonymous.get("/iphone/api/owner/engineering/summary").status_code == 401

    client = owner_client(app)
    response = client.get("/iphone/api/owner/engineering/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["repository"] == "owner/repo"
    assert payload["final_qualification_available"] is True
    assert payload["policy"]["mode"] == "analyze"
    assert payload["authorities"] == {"remote_push": False, "merge": False, "deploy": False, "body_activation": False}


def test_owner_engineering_policy_change_requires_fresh_owner_verification(tmp_path):
    value = runtime(tmp_path)
    stale = owner_client(app_for(value, fresh=False))
    response = stale.patch("/iphone/api/owner/engineering/policy", json={"mode": "workspace"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "reauthentication_required"

    fresh = owner_client(app_for(value, fresh=True))
    response = fresh.patch("/iphone/api/owner/engineering/policy", json={"mode": "workspace", "max_files": 8})
    assert response.status_code == 200
    assert response.json()["policy"]["mode"] == "workspace"
    assert response.json()["policy"]["max_files"] == 8
    assert response.json()["policy"]["merge_authority"] is False


def test_owner_engineering_execute_requires_autonomous_mode_and_scoped_work(tmp_path):
    value = runtime(tmp_path)
    order = seed_scoped_work(value["engineering"].work_store)
    client = owner_client(app_for(value, fresh=True))

    denied = client.post(f"/iphone/api/owner/engineering/work/{order.id}/execute")
    assert denied.status_code == 409

    value["engineering"].owner_policy.update(mode="auto_fix")
    allowed = client.post(f"/iphone/api/owner/engineering/work/{order.id}/execute")
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["scheduled"] is True
    assert payload["remote_push"] is False
    assert payload["merge"] is False
    assert payload["deploy"] is False
    assert payload["body_activation"] is False
    assert value["engineering_executor"].calls


def test_owner_engineering_ui_exposes_all_governed_modes_without_release_controls():
    for label in ("Off", "Analyze", "Workspace", "Auto-Fix", "Review Candidate"):
        assert label in OWNER_ENGINEERING_JS
    assert "Engineering Autonomy" in OWNER_ENGINEERING_JS
    assert "merge" not in OWNER_ENGINEERING_JS.lower()
    assert "deploy" not in OWNER_ENGINEERING_JS.lower()
