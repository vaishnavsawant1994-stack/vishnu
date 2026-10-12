from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from future_intelligence.work_orchestration.models import (
    EvidenceContract,
    EvidenceRequirement,
    ExecutionBudget,
    GoalSpec,
    ReadinessStatus,
    ResourceScope,
    WorkOrder,
    WorkOrderStatus,
    WorkPlan,
    WorkPlanStatus,
)

from .models import CapabilityPlan, CapabilityRisk, CapabilityRoute, CapabilitySpec


@dataclass(frozen=True)
class ForgeWorkProjection:
    goal: GoalSpec
    work_plan: WorkPlan
    work_order: WorkOrder


class CapabilityForgeWorkBridge:
    """Project approved Forge specifications into *draft* Canonical Work.

    This bridge creates no engineering workspace and holds no execution,
    repository mutation, push, merge, deployment, or capability activation
    authority. The resulting WorkOrder remains DRAFT/HOLD until existing Vishnu
    governance explicitly advances it.
    """

    ENGINEERING_ROUTES = frozenset({CapabilityRoute.GENERATED, CapabilityRoute.CORE_ENGINEERING})

    def __init__(self, work_store, *, events=None):
        self.work_store = work_store
        self.events = events

    @staticmethod
    def _clean_tuple(values: Sequence[str] | None, *, label: str) -> tuple[str, ...]:
        out: list[str] = []
        for raw in values or ():
            value = str(raw or "").strip().replace("\\", "/")
            if not value:
                continue
            if value in {".", "./", "*", "**", "**/*", "/"}:
                raise ValueError(f"{label} must not grant repository-wide authority")
            if value not in out:
                out.append(value)
        return tuple(out)

    @staticmethod
    def _id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}-{digest}"

    @staticmethod
    def _risk_value(plan: CapabilityPlan) -> str:
        return plan.risk.risk.value if plan.risk is not None else CapabilityRisk.WRITE.value

    @staticmethod
    def _verification(spec: CapabilitySpec, plan: CapabilityPlan) -> dict[str, Any]:
        security_class = "ordinary"
        if plan.risk is not None and plan.risk.risk is CapabilityRisk.DESTRUCTIVE:
            security_class = "authority"
        elif plan.risk is not None and (plan.risk.risk is CapabilityRisk.WRITE or plan.risk.authority_expansion):
            security_class = "sensitive"
        surfaces = ["backend"]
        if spec.ui_required:
            surfaces.append("ui")
        return {
            "affected_surfaces": surfaces,
            "ui_required": bool(spec.ui_required),
            "accessibility_required": bool(spec.ui_required),
            "visual_review_required": bool(spec.ui_required),
            "security_class": security_class,
            "tests": ["forge capability contract", "regression"],
            "api_impacts": [],
            "schema_impacts": [],
            "forge_spec_id": spec.id,
            "forge_plan_id": plan.id,
            "forge_route": plan.route.value,
        }

    def project(
        self,
        spec: CapabilitySpec,
        plan: CapabilityPlan,
        *,
        repository: str,
        allowed_paths: Sequence[str],
        project_id: str | None = None,
        priority: int = 50,
        max_runtime_seconds: int = 1800,
        max_attempts: int = 3,
        prohibited_paths: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> ForgeWorkProjection:
        if plan.spec_id != spec.id:
            raise ValueError("Forge plan does not belong to the supplied capability specification")
        if plan.route not in self.ENGINEERING_ROUTES:
            raise PermissionError("this Forge route must reuse discovery/composition and cannot create engineering work")
        repository = str(repository or "").strip()
        if not repository:
            raise ValueError("an explicit engineering repository is required")
        paths = self._clean_tuple(allowed_paths, label="allowed_paths")
        if not paths:
            raise ValueError("at least one explicit engineering path is required")
        prohibited = self._clean_tuple(prohibited_paths, label="prohibited_paths") if prohibited_paths else ()
        if not 0 <= int(priority) <= 100:
            raise ValueError("priority must be between 0 and 100")
        if int(max_runtime_seconds) <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if not 1 <= int(max_attempts) <= 5:
            raise ValueError("max_attempts must be between 1 and 5")

        lineage = {
            "forge_spec_id": spec.id,
            "forge_plan_id": plan.id,
            "forge_route": plan.route.value,
            "forge_capability_name": spec.name,
            "forge_activation_authority": False,
            "network_hosts": list(spec.network_hosts),
            "filesystem_read": list(spec.filesystem_read),
            "filesystem_write": list(spec.filesystem_write),
            "secret_names": list(spec.secret_names),
            "prohibited_paths": list(prohibited),
            **dict(metadata or {}),
        }
        scope = ResourceScope(
            allowed_repositories=(repository,),
            allowed_paths=paths,
            allowed_connectors=tuple(spec.connector_ids),
            allowed_destinations=tuple(spec.network_hosts),
            metadata=lineage,
        )
        goal_id = self._id("goal-forge", spec.id, plan.id)
        canonical_plan_id = self._id("workplan-forge", spec.id, plan.id, repository, json.dumps(paths))
        order_id = self._id("work-forge", canonical_plan_id, spec.id)
        constraints = (
            "Work remains inside the explicitly scoped repository and paths.",
            "No push, merge, deployment, production activation, or capability activation is authorized.",
            "Any permission or authority expansion requires a new owner review.",
            "Generated capability work must preserve the frozen CapabilitySpec acceptance criteria.",
        )
        goal = GoalSpec(
            id=goal_id,
            project_id=project_id,
            title=f"Forge capability: {spec.name}",
            objective=spec.purpose,
            desired_outcome=f"Produce a qualified candidate for {spec.name} without activating it.",
            deliverables=("qualified capability candidate", "qualification evidence", "permission manifest"),
            success_criteria=tuple(spec.acceptance_criteria),
            constraints=constraints,
            resource_scope=scope,
            priority=int(priority),
            data_classification=str(dict(spec.metadata or {}).get("data_classification", "internal")),
            budget=ExecutionBudget(max_runtime_seconds=int(max_runtime_seconds), max_attempts=int(max_attempts)),
            approval_policy={
                "requires_owner_review": True,
                "allow_authority_paths": False,
                "activation_authority": False,
                "forge_plan_id": plan.id,
            },
            created_from="capability_forge",
        )
        evidence = EvidenceContract(
            requirements=(
                EvidenceRequirement(kind="tests", min_count=1),
                EvidenceRequirement(kind="security_review", min_count=1),
                EvidenceRequirement(kind="capability_contract", min_count=1),
            ),
            require_review=True,
            require_retest=True,
        )
        order = WorkOrder(
            id=order_id,
            plan_id=canonical_plan_id,
            project_id=project_id,
            title=f"Build and qualify {spec.name}",
            objective=spec.purpose,
            worker_type="engineering",
            status=WorkOrderStatus.DRAFT,
            priority=int(priority),
            resource_scope=scope,
            expected_output="A qualified, reviewable candidate plus evidence; not an activated capability.",
            success_criteria=tuple(spec.acceptance_criteria),
            evidence_contract=evidence,
            verification_strategy=self._verification(spec, plan),
            falsifier="Any undeclared authority use, failed mandatory qualification, or acceptance-criteria failure invalidates the candidate.",
            retest_strategy={"full_regression": True, "after_repair": True},
            approval_policy={
                "requires_owner_review": True,
                "allow_authority_paths": False,
                "activation_authority": False,
                "forge_risk": self._risk_value(plan),
            },
            retry_policy={"max_attempts": int(max_attempts), "automatic_repair": True},
            time_budget_seconds=int(max_runtime_seconds),
        )
        work_plan = WorkPlan(
            id=canonical_plan_id,
            goal_id=goal.id,
            project_id=project_id,
            version=1,
            summary=f"Governed engineering candidate for Forge spec {spec.id}",
            work_orders=(order,),
            assumptions=(
                "The CapabilitySpec is frozen for this work candidate.",
                "Existing Engineering Runtime and qualification gates remain authoritative.",
            ),
            evidence_contract=evidence,
            critic={
                "forge_plan_id": plan.id,
                "route": plan.route.value,
                "risk": self._risk_value(plan),
                "activation_authority": False,
            },
            readiness=ReadinessStatus.HOLD,
            status=WorkPlanStatus.DRAFT,
        )
        return ForgeWorkProjection(goal=goal, work_plan=work_plan, work_order=order)

    def persist(self, projection: ForgeWorkProjection) -> ForgeWorkProjection:
        if projection.work_plan.status is not WorkPlanStatus.DRAFT or projection.work_order.status is not WorkOrderStatus.DRAFT:
            raise PermissionError("Forge may only persist draft Canonical Work in this phase")
        self.work_store.upsert_goal(projection.goal)
        self.work_store.save_plan(projection.work_plan)
        if self.events is not None:
            self.events.emit(
                "capability_forge.work_projected",
                goal_id=projection.goal.id,
                work_plan_id=projection.work_plan.id,
                work_order_id=projection.work_order.id,
                status=projection.work_order.status.value,
            )
        return projection

    def prepare_draft_work(self, spec: CapabilitySpec, plan: CapabilityPlan, **kwargs) -> ForgeWorkProjection:
        """Create and persist draft work; deliberately does not claim or execute it."""
        return self.persist(self.project(spec, plan, **kwargs))
