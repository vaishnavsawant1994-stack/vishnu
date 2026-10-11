from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from future_intelligence.engineering.owner_policy import EngineeringOwnerPolicyStore
from future_intelligence.work_orchestration import DurableWorkStore, GoalSpec, WorkOrder, WorkPlan
from server.owner_engineering_api import EngineeringPolicyBody, owner_engineering_router
from server.owner_engineering_ui import owner_engineering_ui_router


class TrustedRegistry:
    def authenticate(self, device_id, token):
        return device_id == "device-1" and token == "token-1"

    def is_active(self, device_id):
        return device_id == "device-1"

    def authorize(self, device_id, capability):
        return device_id == "device-1" and capability == "device:admin"


class NeverCalledExecutor:
    def execute(self, *args, **kwargs):  # pragma: no cover - scope gate must stop first
        raise AssertionError("unscoped Engineering Work must not execute")


def route_endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"route missing: {method} {path}")


def make_runtime(tmp_path):
    store = DurableWorkStore(tmp_path / "work.sqlite3")
    policy = EngineeringOwnerPolicyStore(tmp_path / "engineering-policy.json")
    engineering = SimpleNamespace(
        work_store=store,
        owner_policy=policy,
        repository_provider=SimpleNamespace(repository="owner/repo"),
    )
    return {
        "device_registry": TrustedRegistry(),
        "engineering": engineering,
        "engineering_executor": NeverCalledExecutor(),
        "pwa_sessions": None,
        "events": None,
        "code_worker_epoch": 1,
    }


def test_owner_engineering_summary_policy_and_authority_boundaries(tmp_path):
    runtime = make_runtime(tmp_path)
    router = owner_engineering_router(runtime)
    summary = route_endpoint(router, "/iphone/api/owner/engineering/summary", "GET")
    update = route_endpoint(router, "/iphone/api/owner/engineering/policy", "PATCH")

    payload = summary(pa_device="device-1", pa_token="token-1")
    assert payload["available"] is True
    assert payload["repository"] == "owner/repo"
    assert payload["policy"]["mode"] == "analyze"
    assert payload["authorities"] == {
        "remote_push": False,
        "merge": False,
        "deploy": False,
        "body_activation": False,
    }

    changed = update(
        EngineeringPolicyBody(mode="workspace", max_files=7, max_repair_cycles=2),
        pa_device="device-1",
        pa_token="token-1",
    )
    assert changed["policy"]["mode"] == "workspace"
    assert changed["policy"]["max_files"] == 7
    assert changed["policy"]["max_repair_cycles"] == 2
    assert EngineeringOwnerPolicyStore(tmp_path / "engineering-policy.json").snapshot().mode.value == "workspace"

    with pytest.raises(HTTPException) as denied:
        summary(pa_device="device-1", pa_token="wrong")
    assert denied.value.status_code == 401


def test_owner_engineering_mutation_requires_fresh_owner_verification(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime["pwa_sessions"] = object()
    router = owner_engineering_router(runtime)
    update = route_endpoint(router, "/iphone/api/owner/engineering/policy", "PATCH")

    with pytest.raises(HTTPException) as exc:
        update(EngineeringPolicyBody(mode="auto_fix"), pa_device="device-1", pa_token="token-1")
    assert exc.value.status_code == 401
    detail = exc.value.detail
    assert isinstance(detail, dict) and detail["code"] == "reauthentication_required"


def test_owner_engineering_execute_rejects_unscoped_canonical_work(tmp_path):
    runtime = make_runtime(tmp_path)
    store = runtime["engineering"].work_store
    goal = GoalSpec(
        id="goal-owner-eng",
        title="Engineering request",
        objective="Inspect a regression",
        desired_outcome="A governed engineering decision",
    )
    store.upsert_goal(goal)
    order = WorkOrder(
        id="work-owner-eng",
        plan_id="plan-owner-eng",
        title="Unscoped engineering request",
        objective="Do not mutate anything without explicit scope",
        worker_type="software_engineer",
    )
    store.save_plan(WorkPlan(
        id="plan-owner-eng",
        goal_id=goal.id,
        version=1,
        summary="Unscoped test plan",
        work_orders=(order,),
    ))
    runtime["engineering"].owner_policy.update(mode="auto_fix")
    router = owner_engineering_router(runtime)
    execute = route_endpoint(router, "/iphone/api/owner/engineering/work/{work_order_id}/execute", "POST")

    with pytest.raises(HTTPException) as exc:
        execute(
            "work-owner-eng",
            BackgroundTasks(),
            pa_device="device-1",
            pa_token="token-1",
        )
    assert exc.value.status_code == 409
    assert "explicit repository and path scope" in str(exc.value.detail)


def test_owner_engineering_ui_exposes_governed_controls_and_no_release_authority():
    router = owner_engineering_ui_router()
    endpoint = route_endpoint(router, "/iphone/owner-engineering-ui.js", "GET")
    response = endpoint()
    body = response.body.decode("utf-8")
    assert "Engineering Autonomy" in body
    assert "Auto-Fix" in body
    assert "Review Candidate" in body
    assert "No auto merge" in body
    assert "No auto deploy" in body
    assert "/owner/engineering/policy" in body
