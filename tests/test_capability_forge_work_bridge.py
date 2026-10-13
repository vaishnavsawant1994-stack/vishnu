from pathlib import Path

import pytest

from future_intelligence.capability_forge import CapabilityForgeService, CapabilityForgeStore, CapabilityRoute
from future_intelligence.capability_forge.work_bridge import CapabilityForgeWorkBridge
from future_intelligence.work_orchestration.models import ReadinessStatus, WorkOrderStatus, WorkPlanStatus
from future_intelligence.work_orchestration.store import WorkStore


def _proposal(tmp_path: Path, *, route_signal=None):
    forge = CapabilityForgeService(CapabilityForgeStore(tmp_path / "forge.sqlite3"))
    payload = {
        "capability_gap": True,
        "capability_name": "Supplier price monitor",
        "requested_outcome": "Build a reusable monitor for supplier prices",
        "required_operations": ["fetch page", "extract price"],
        **(route_signal or {}),
    }
    result = forge.propose("project", payload, requirements={"acceptance_criteria": ["Detects a changed price from the qualification fixture."]})
    assert result is not None
    return result


def test_generated_route_projects_draft_canonical_work(tmp_path):
    _, spec, plan = _proposal(tmp_path)
    assert plan.route is CapabilityRoute.GENERATED
    work_store = WorkStore(tmp_path / "work.sqlite3")
    bridge = CapabilityForgeWorkBridge(work_store)

    projected = bridge.prepare_draft_work(
        spec,
        plan,
        repository="vaishnavsawant1994-stack/vishnu",
        allowed_paths=("generated-capabilities/supplier-price-monitor",),
        project_id="project-17",
    )

    assert projected.work_plan.status is WorkPlanStatus.DRAFT
    assert projected.work_plan.readiness is ReadinessStatus.HOLD
    assert projected.work_order.status is WorkOrderStatus.DRAFT
    assert projected.work_order.worker_type == "engineering"
    assert projected.work_order.resource_scope.allowed_repositories == ("vaishnavsawant1994-stack/vishnu",)
    assert projected.work_order.resource_scope.allowed_paths == ("generated-capabilities/supplier-price-monitor",)
    assert projected.work_order.approval_policy["activation_authority"] is False
    assert work_store.get_goal(projected.goal.id) == projected.goal
    assert work_store.get_plan(projected.work_plan.id) == projected.work_plan
    assert work_store.get_order(projected.work_order.id) == projected.work_order


def test_core_engineering_route_can_project_only_explicit_narrow_paths(tmp_path):
    _, spec, plan = _proposal(tmp_path, route_signal={"requires_core_change": True})
    assert plan.route is CapabilityRoute.CORE_ENGINEERING
    bridge = CapabilityForgeWorkBridge(WorkStore(tmp_path / "work.sqlite3"))

    projected = bridge.project(
        spec,
        plan,
        repository="vaishnavsawant1994-stack/vishnu",
        allowed_paths=("future_intelligence/capability_forge",),
    )

    assert projected.work_order.resource_scope.allowed_paths == ("future_intelligence/capability_forge",)
    assert projected.work_order.verification_strategy["forge_route"] == "core_engineering"


@pytest.mark.parametrize("route_signal", [
    {"external_api": True},
    {"mcp": True},
    {"preferred_route": "workflow"},
])
def test_discovery_and_composition_routes_cannot_create_engineering_work(tmp_path, route_signal):
    _, spec, plan = _proposal(tmp_path, route_signal=route_signal)
    bridge = CapabilityForgeWorkBridge(WorkStore(tmp_path / "work.sqlite3"))

    with pytest.raises(PermissionError):
        bridge.project(
            spec,
            plan,
            repository="vaishnavsawant1994-stack/vishnu",
            allowed_paths=("generated-capabilities/test",),
        )


@pytest.mark.parametrize("broad_path", [".", "./", "*", "**", "**/*", "/"])
def test_bridge_rejects_repository_wide_path_authority(tmp_path, broad_path):
    _, spec, plan = _proposal(tmp_path)
    bridge = CapabilityForgeWorkBridge(WorkStore(tmp_path / "work.sqlite3"))

    with pytest.raises(ValueError, match="repository-wide"):
        bridge.project(
            spec,
            plan,
            repository="vaishnavsawant1994-stack/vishnu",
            allowed_paths=(broad_path,),
        )


def test_bridge_has_no_execution_or_activation_operation(tmp_path):
    bridge = CapabilityForgeWorkBridge(WorkStore(tmp_path / "work.sqlite3"))
    for method in ("execute", "activate", "merge", "deploy", "push", "claim"):
        assert not hasattr(bridge, method)
