from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.execution_bridge import CapabilityForgeExecutionBridge
from future_intelligence.capability_forge.models import (
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    RiskAssessment,
)
from future_intelligence.work_orchestration.models import ResourceScope, WorkOrder, WorkOrderStatus


def _spec():
    return CapabilitySpec(
        id="spec-1",
        gap_id="gap-1",
        name="Pure calculator",
        purpose="Calculate a normalized score",
        inputs={"type": "object"},
        outputs={"type": "object"},
        acceptance_criteria=("returns the expected score",),
    )


def _plan(spec):
    return CapabilityPlan(
        id="plan-1",
        spec_id=spec.id,
        route=CapabilityRoute.GENERATED,
        rationale="No existing capability",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False),
        owner_review_required=True,
        created_at="2026-10-13T00:00:00+00:00",
    )


def _order(spec, plan, status=WorkOrderStatus.QUEUED):
    return WorkOrder(
        id="work-1",
        plan_id="workplan-1",
        title="Build calculator",
        objective=spec.purpose,
        worker_type="engineering",
        status=status,
        resource_scope=ResourceScope(
            allowed_repositories=("vaishnavsawant1994-stack/vishnu",),
            allowed_paths=("generated-capabilities/pure-calculator",),
            metadata={
                "forge_spec_id": spec.id,
                "forge_plan_id": plan.id,
                "forge_activation_authority": False,
            },
        ),
        approval_policy={"activation_authority": False},
    )


class Store:
    def __init__(self, order):
        self.order = order

    def get_order(self, order_id):
        return self.order if order_id == self.order.id else None


class Executor:
    def __init__(self):
        self.calls = []

    def execute(self, work_order_id, **kwargs):
        self.calls.append((work_order_id, kwargs))
        return SimpleNamespace(
            work_order_id=work_order_id,
            attempt_id="attempt-1",
            candidate_revision="candidate-sha",
            changed_paths=("generated-capabilities/pure-calculator/capability.py",),
            qualification={"qualified": True},
            review={"decision": "approved", "reviewer": "independent"},
            status="qualified",
        )


def test_forge_execution_bridge_uses_existing_engineering_executor_only_after_queue():
    spec = _spec()
    plan = _plan(spec)
    executor = Executor()
    bridge = CapabilityForgeExecutionBridge(Store(_order(spec, plan)), executor)

    result = bridge.execute_candidate(spec, plan, work_order_id="work-1", runtime_epoch=7)

    assert result.qualified is True
    assert result.candidate_revision == "candidate-sha"
    assert executor.calls[0][0] == "work-1"
    assert executor.calls[0][1]["worker_id"] == "vishnu-capability-forge"
    assert executor.calls[0][1]["runtime_epoch"] == 7


def test_forge_execution_bridge_refuses_draft_or_lineage_mismatch():
    spec = _spec()
    plan = _plan(spec)
    executor = Executor()

    draft = CapabilityForgeExecutionBridge(Store(_order(spec, plan, WorkOrderStatus.DRAFT)), executor)
    with pytest.raises(PermissionError, match="advanced by Canonical Work"):
        draft.execute_candidate(spec, plan, work_order_id="work-1", runtime_epoch=1)

    wrong = _order(spec, plan)
    wrong = WorkOrder.from_dict(
        {
            **wrong.to_dict(),
            "resource_scope": {
                **wrong.resource_scope.to_dict(),
                "metadata": {
                    "forge_spec_id": "other",
                    "forge_plan_id": plan.id,
                    "forge_activation_authority": False,
                },
            },
        }
    )
    mismatch = CapabilityForgeExecutionBridge(Store(wrong), executor)
    with pytest.raises(PermissionError, match="lineage"):
        mismatch.execute_candidate(spec, plan, work_order_id="work-1", runtime_epoch=1)


def test_discovery_route_can_never_enter_engineering_executor():
    spec = _spec()
    plan = CapabilityPlan(
        id="plan-openapi",
        spec_id=spec.id,
        route=CapabilityRoute.OPENAPI_DISCOVERY,
        rationale="API-backed",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False),
    )
    bridge = CapabilityForgeExecutionBridge(Store(_order(spec, _plan(spec))), Executor())
    with pytest.raises(PermissionError, match="discovery/composition"):
        bridge.execute_candidate(spec, plan, work_order_id="work-1", runtime_epoch=1)
