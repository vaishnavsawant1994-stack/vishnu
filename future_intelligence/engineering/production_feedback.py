from __future__ import annotations

import hashlib
from dataclasses import dataclass

from future_intelligence.work_orchestration.models import (
    EvidenceContract,
    EvidenceRequirement,
    GoalSpec,
    ReadinessStatus,
    ResourceScope,
    WorkOrder,
    WorkOrderStatus,
    WorkPlan,
    WorkPlanStatus,
)

from .release_qualification import ProductionRegression


@dataclass(frozen=True)
class ProductionFeedbackWork:
    goal_id: str
    plan_id: str
    work_order_id: str
    created: bool


class ProductionRegressionWorkBridge:
    """Create idempotent Canonical Work from production observations only.

    The generated Work intentionally receives no repository path, mutation,
    deployment or release authority. Reproduction/diagnosis can proceed through
    planning, but any source edit still needs an explicitly scoped engineering
    WorkOrder produced by the normal governed planning flow.
    """

    def __init__(self, work_store) -> None:
        self.work_store = work_store

    @staticmethod
    def _ids(regression: ProductionRegression) -> tuple[str, str, str]:
        seed = "|".join((regression.release_revision, regression.target, regression.signal)).encode("utf-8")
        digest = hashlib.sha256(seed).hexdigest()[:24]
        return f"goal-prod-{digest}", f"plan-prod-{digest}", f"work-prod-{digest}"

    def create(self, regression: ProductionRegression) -> ProductionFeedbackWork:
        goal_id, plan_id, work_id = self._ids(regression)
        existing = self.work_store.get_order(work_id)
        if existing is not None:
            return ProductionFeedbackWork(goal_id, plan_id, work_id, False)

        proposal = regression.to_work_proposal()
        metadata = dict(proposal.get("metadata") or {})
        scope = ResourceScope(
            metadata={
                "source": "production_regression_observation",
                "release_revision": regression.release_revision,
                "target": regression.target,
                "signal": regression.signal,
                "evidence": list(regression.evidence),
                "severity": regression.severity,
                "automatic_mutation_authority": False,
                "automatic_deploy_authority": False,
            }
        )
        goal = GoalSpec(
            id=goal_id,
            title=str(proposal["title"]),
            objective=str(proposal["objective"]),
            desired_outcome="A reproduced and diagnosed regression with evidence and a separately governed repair plan if code changes are required.",
            deliverables=("reproduction evidence", "root-cause diagnosis", "governed repair recommendation"),
            success_criteria=("regression signal is reproduced or falsified", "diagnosis is evidence-backed"),
            constraints=("no automatic source mutation", "no automatic deployment", "no automatic rollback"),
            resource_scope=scope,
            priority=90 if regression.severity in {"critical", "high"} else 70,
            data_classification="internal",
            approval_policy={"automatic_mutation": False, "automatic_deploy": False},
            created_from="production_regression_observation",
        )
        order = WorkOrder(
            id=work_id,
            plan_id=plan_id,
            title=str(proposal["title"]),
            objective=str(proposal["objective"]),
            worker_type="reviewer",
            status=WorkOrderStatus.QUEUED,
            priority=goal.priority,
            allowed_capabilities=(),
            resource_scope=scope,
            expected_output="Evidence-backed production regression diagnosis and a recommendation for separately scoped repair Work.",
            success_criteria=goal.success_criteria,
            evidence_contract=EvidenceContract(
                requirements=(EvidenceRequirement("production_observation", min_count=1),),
                require_review=True,
                require_retest=True,
            ),
            verification_strategy={
                "production_observation": True,
                "release_revision": regression.release_revision,
                "target": regression.target,
            },
            approval_policy={"automatic_mutation": False, "automatic_deploy": False},
            retry_policy={"max_attempts": 1},
        )
        plan = WorkPlan(
            id=plan_id,
            goal_id=goal_id,
            version=1,
            summary="Investigate a production regression before any repair or release action is considered.",
            work_orders=(order,),
            assumptions=("production observation is untrusted until reproduced",),
            evidence_contract=order.evidence_contract,
            readiness=ReadinessStatus.READY,
            status=WorkPlanStatus.READY,
        )
        self.work_store.upsert_goal(goal)
        self.work_store.save_plan(plan)
        self.work_store.append_work_event(
            work_id,
            "production.regression_observed",
            {
                **metadata,
                "automatic_mutation_authority": False,
                "automatic_deploy_authority": False,
            },
        )
        return ProductionFeedbackWork(goal_id, plan_id, work_id, True)
