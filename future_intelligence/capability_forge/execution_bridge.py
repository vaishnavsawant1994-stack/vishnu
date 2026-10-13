from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from future_intelligence.work_orchestration.models import WorkOrderStatus

from .models import CapabilityPlan, CapabilityRoute, CapabilitySpec


@dataclass(frozen=True)
class ForgeCandidateResult:
    work_order_id: str
    attempt_id: str
    candidate_revision: str
    changed_paths: tuple[str, ...]
    status: str
    qualified: bool
    qualification: Mapping[str, Any]
    review: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "candidate_revision": self.candidate_revision,
            "changed_paths": list(self.changed_paths),
            "status": self.status,
            "qualified": self.qualified,
            "qualification": dict(self.qualification),
            "review": dict(self.review),
        }


class CapabilityForgeExecutionBridge:
    """Run already-governed Forge Work through Vishnu's EngineeringWorkExecutor.

    This bridge cannot enqueue draft Work, broaden resource scope, approve owner
    actions, push, merge, deploy, or activate a capability. It only executes a
    WorkOrder that Canonical Work has already advanced to QUEUED/RETRYING.
    """

    ENGINEERING_ROUTES = frozenset({CapabilityRoute.GENERATED, CapabilityRoute.CORE_ENGINEERING})

    def __init__(self, work_store, engineering_executor, *, events=None, lifecycle=None):
        self.work_store = work_store
        self.engineering_executor = engineering_executor
        self.events = events
        self.lifecycle = lifecycle

    @staticmethod
    def _lineage(order) -> dict[str, Any]:
        return dict(getattr(order.resource_scope, "metadata", {}) or {})

    def _validate(self, spec: CapabilitySpec, plan: CapabilityPlan, work_order_id: str):
        if plan.spec_id != spec.id:
            raise ValueError("Forge plan does not belong to the supplied capability specification")
        if plan.route not in self.ENGINEERING_ROUTES:
            raise PermissionError("discovery/composition routes cannot execute engineering work")
        order = self.work_store.get_order(str(work_order_id))
        if order is None:
            raise KeyError(work_order_id)
        if order.worker_type != "engineering":
            raise PermissionError("Forge engineering work must use the engineering worker type")
        if order.status not in {WorkOrderStatus.QUEUED, WorkOrderStatus.RETRYING}:
            raise PermissionError("Forge WorkOrder must be advanced by Canonical Work before execution")
        lineage = self._lineage(order)
        if lineage.get("forge_spec_id") != spec.id or lineage.get("forge_plan_id") != plan.id:
            raise PermissionError("Forge WorkOrder lineage does not match the supplied specification and plan")
        if bool(lineage.get("forge_activation_authority", False)):
            raise PermissionError("Forge engineering work must not carry activation authority")
        if bool(dict(order.approval_policy or {}).get("activation_authority", False)):
            raise PermissionError("Canonical Work must not grant capability activation authority")
        if not tuple(order.resource_scope.allowed_repositories or ()):
            raise PermissionError("Forge engineering work requires an explicit repository scope")
        allowed_paths = tuple(str(item) for item in order.resource_scope.allowed_paths or ())
        if not allowed_paths or any(item in {".", "./", "*", "**", "**/*", "/"} for item in allowed_paths):
            raise PermissionError("Forge engineering work requires narrow explicit path scopes")
        return order

    def execute_candidate(
        self,
        spec: CapabilitySpec,
        plan: CapabilityPlan,
        *,
        work_order_id: str,
        runtime_epoch: int,
        worker_id: str = "vishnu-capability-forge",
        base_revision: str = "HEAD",
        lease_seconds: int = 3600,
        overrides: Mapping[str, object] | None = None,
    ) -> ForgeCandidateResult:
        order = self._validate(spec, plan, work_order_id)
        result = self.engineering_executor.execute(
            order.id,
            worker_id=str(worker_id),
            runtime_epoch=int(runtime_epoch),
            base_revision=str(base_revision),
            lease_seconds=int(lease_seconds),
            overrides=overrides,
        )
        qualification = dict(result.qualification or {})
        qualified = bool(qualification.get("qualified")) and str(result.status) == "qualified"
        candidate = ForgeCandidateResult(
            work_order_id=str(result.work_order_id),
            attempt_id=str(result.attempt_id),
            candidate_revision=str(result.candidate_revision),
            changed_paths=tuple(str(item) for item in result.changed_paths),
            status=str(result.status),
            qualified=qualified,
            qualification=qualification,
            review=dict(result.review or {}),
        )
        if self.lifecycle is not None:
            self.lifecycle.record_build(
                build_id=f"build:{candidate.attempt_id}",
                spec_id=spec.id,
                plan_id=plan.id,
                work_order_id=candidate.work_order_id,
                attempt_id=candidate.attempt_id,
                candidate_revision=candidate.candidate_revision,
                status="qualified" if candidate.qualified else candidate.status,
                payload=candidate.to_dict(),
            )
        if self.events is not None:
            self.events.emit(
                "capability_forge.candidate_built",
                spec_id=spec.id,
                plan_id=plan.id,
                work_order_id=candidate.work_order_id,
                attempt_id=candidate.attempt_id,
                candidate_revision=candidate.candidate_revision,
                qualified=candidate.qualified,
                status=candidate.status,
            )
        return candidate
