from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from future_intelligence.work_orchestration.attempts import WorkAttemptStatus
from future_intelligence.work_orchestration.failure_policy import FailureClass, WorkFailure
from future_intelligence.work_orchestration.recovery import RecoveryReason
from security.projection_redaction import sanitize_sensitive_text

from .change_planner import EngineeringEditPlan, ModelEngineeringChangePlanner
from .reviewer_adapter import EngineeringReviewDecision, ModelEngineeringReviewer
from .verification import observations_from_verification_report


@dataclass(frozen=True)
class EngineeringExecutionResult:
    work_order_id: str
    attempt_id: str
    spec_id: str
    candidate_revision: str
    changed_paths: tuple[str, ...]
    verification_passed: bool | None
    repair_cycles: int
    qualification: Mapping[str, Any]
    review: Mapping[str, Any]
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "spec_id": self.spec_id,
            "candidate_revision": self.candidate_revision,
            "changed_paths": list(self.changed_paths),
            "verification_passed": self.verification_passed,
            "repair_cycles": self.repair_cycles,
            "qualification": dict(self.qualification),
            "review": dict(self.review),
            "status": self.status,
            "push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "activation_authority": False,
        }


class EngineeringWorkExecutor:
    """Bounded model -> governed edits -> local verify -> candidate review executor.

    This class deliberately stops at a local candidate in canonical VERIFYING
    state. It cannot approve owner actions, push, merge, deploy, publish, or
    activate a Body revision. Browser/device/visual evidence may be added by the
    external qualification lanes before the WorkOrder can progress further.
    """

    def __init__(
        self,
        *,
        runtime,
        models,
        verification_provider=None,
        planner: ModelEngineeringChangePlanner | None = None,
        reviewer=None,
    ) -> None:
        self.runtime = runtime
        self.models = models
        self.verification_provider = verification_provider
        self.planner = planner or ModelEngineeringChangePlanner(models)
        self.reviewer = reviewer or ModelEngineeringReviewer(models)

    @staticmethod
    def _review_payload(decision: EngineeringReviewDecision) -> dict[str, object]:
        return {
            "decision": decision.decision,
            "reviewer": decision.reviewer,
            "summary": decision.summary,
            "findings": list(decision.findings),
        }

    @staticmethod
    def _verification_defects(report) -> tuple[str, ...]:
        defects = []
        for check in report.checks:
            if check.passed:
                continue
            excerpt = sanitize_sensitive_text(str(check.output_excerpt or ""))[:4000]
            defects.append(f"{check.name}: returncode={check.returncode}; output={excerpt}")
        return tuple(defects)

    def _apply_plan(self, coordinator, plan: EngineeringEditPlan) -> tuple[str, ...]:
        if not plan.operations:
            raise ValueError("engineering model returned no safe source edits")
        work_order_id = coordinator.spec.work_order_id
        attempt_id = coordinator.spec.attempt_id
        mutated = []
        for edit in plan.operations:
            if edit.operation == "create":
                result = self.runtime.execute(
                    work_order_id, attempt_id, "create", {"path": edit.path, "content": edit.content}
                )
            else:
                current = self.runtime.execute(work_order_id, attempt_id, "read", {"path": edit.path})
                digest = str(current["sha256"])
                if edit.operation == "replace_exact":
                    result = self.runtime.execute(
                        work_order_id,
                        attempt_id,
                        "replace_exact",
                        {"path": edit.path, "old": edit.old, "new": edit.new, "expected_sha256": digest},
                    )
                elif edit.operation == "delete":
                    result = self.runtime.execute(
                        work_order_id, attempt_id, "delete", {"path": edit.path, "expected_sha256": digest}
                    )
                elif edit.operation == "rename":
                    result = self.runtime.execute(
                        work_order_id,
                        attempt_id,
                        "rename",
                        {"source": edit.path, "destination": edit.destination, "expected_sha256": digest},
                    )
                else:  # pragma: no cover - validated by EngineeringEditOperation
                    raise ValueError(edit.operation)
            mutated.extend(str(item) for item in result.get("mutated_paths", ()))
        return tuple(dict.fromkeys(mutated))

    def _commit_and_verify(self, coordinator, *, message: str):
        commit = self.runtime.commit(
            coordinator.spec.work_order_id,
            coordinator.spec.attempt_id,
            message=message,
        )
        revision = str(commit["revision"])
        if self.verification_provider is None:
            return revision, None, ()
        report = self.verification_provider.verify(coordinator.session, revision=revision)
        observations = observations_from_verification_report(report)
        coordinator.evidence.append(
            "engineering.local_verification",
            {
                "revision": report.revision,
                "passed": report.passed,
                "checks": [
                    {
                        "name": item.name,
                        "passed": item.passed,
                        "returncode": item.returncode,
                        "duration_ms": item.duration_ms,
                        "output_hash": item.output_hash,
                    }
                    for item in report.checks
                ],
            },
        )
        return revision, report, observations

    def _finish_attempt(self, coordinator, *, succeeded: bool, metadata: Mapping[str, Any]) -> None:
        lease = self.runtime.work_store.get_lease(coordinator.spec.work_order_id)
        if lease is None or lease.attempt_id != coordinator.spec.attempt_id:
            raise RuntimeError("engineering execution lost its canonical Work lease")
        order = self.runtime.work_store.get_order(coordinator.spec.work_order_id)
        retry_policy = {} if order is None else dict(order.retry_policy or {})
        max_attempts = max(1, int(retry_policy.get("max_attempts", 1)))
        if succeeded:
            self.runtime.work_store.finish_attempt(
                coordinator.spec.attempt_id,
                lease_token=lease.lease_token,
                status=WorkAttemptStatus.SUCCEEDED,
                metadata=dict(metadata),
                max_attempts=max_attempts,
            )
        else:
            self.runtime.work_store.finish_attempt(
                coordinator.spec.attempt_id,
                lease_token=lease.lease_token,
                status=WorkAttemptStatus.FAILED,
                failure=WorkFailure(
                    failure_class=FailureClass.VALIDATION,
                    code="engineering_local_verification_failed",
                    message="bounded engineering verification did not pass",
                    metadata=dict(metadata),
                ),
                max_attempts=max_attempts,
            )

    def execute(
        self,
        work_order_id: str,
        *,
        worker_id: str = "vishnu-software-engineer",
        runtime_epoch: int,
        base_revision: str = "HEAD",
        lease_seconds: int = 3600,
        overrides: Mapping[str, object] | None = None,
    ) -> EngineeringExecutionResult:
        coordinator = self.runtime.prepare(
            work_order_id,
            worker_id=worker_id,
            runtime_epoch=runtime_epoch,
            base_revision=base_revision,
            lease_seconds=lease_seconds,
            overrides=overrides,
        )
        spec = coordinator.spec
        try:
            context = coordinator.inspect(changed_paths=())
            plan = self.planner.plan(spec=spec, graph=context.graph, editor=coordinator.editor)
            coordinator.evidence.append("engineering.edit_plan", plan.to_dict())
            self._apply_plan(coordinator, plan)
            revision, verification, observations = self._commit_and_verify(
                coordinator, message=f"Vishnu engineering candidate: {spec.objective[:120]}"
            )
            repairs = 0
            while verification is not None and not verification.passed and repairs < spec.budget.max_repair_cycles:
                repairs += 1
                current_context = coordinator.inspect()
                defects = self._verification_defects(verification)
                repair_plan = self.planner.plan(
                    spec=spec,
                    graph=current_context.graph,
                    editor=coordinator.editor,
                    defects=defects,
                    cycle=repairs,
                )
                coordinator.evidence.append(
                    "engineering.repair_plan", {"cycle": repairs, **repair_plan.to_dict()}
                )
                self._apply_plan(coordinator, repair_plan)
                revision, verification, observations = self._commit_and_verify(
                    coordinator, message=f"Vishnu engineering repair {repairs}: {spec.objective[:100]}"
                )

            if verification is not None and not verification.passed:
                failed_context = coordinator.inspect()
                preliminary = coordinator.finalize(
                    candidate_revision=revision,
                    observations=observations,
                    review_decision="pending",
                    limitations=("local verification failed",),
                )
                coordinator.evidence.append(
                    "engineering.execution_failed",
                    {"revision": revision, "repair_cycles": repairs, "reason": "local_verification_failed"},
                )
                self._finish_attempt(
                    coordinator,
                    succeeded=False,
                    metadata={"candidate_revision": revision, "repair_cycles": repairs},
                )
                return EngineeringExecutionResult(
                    work_order_id=work_order_id,
                    attempt_id=spec.attempt_id,
                    spec_id=spec.id,
                    candidate_revision=revision,
                    changed_paths=failed_context.changed_paths,
                    verification_passed=False,
                    repair_cycles=repairs,
                    qualification=preliminary.to_dict(),
                    review={"decision": "not_run", "findings": ["local verification failed"]},
                    status="failed",
                )

            current = coordinator.inspect()
            diff = "\n".join(coordinator.editor.diff(path) for path in current.changed_paths)
            limitations = []
            if verification is None:
                limitations.append("local verification provider unavailable; external qualification required")
            preliminary = coordinator.qualification.report(
                spec=spec,
                candidate_revision=revision,
                observations=observations,
                review_decision="pending",
                limitations=limitations,
            )
            review = self.reviewer.review(
                spec=spec,
                report=preliminary,
                diff=diff,
                evidence={
                    "changed_paths": list(current.changed_paths),
                    "repair_cycles": repairs,
                    "local_verification_passed": None if verification is None else verification.passed,
                },
            )
            final_report = coordinator.finalize(
                candidate_revision=revision,
                observations=observations,
                reviewer=review.reviewer,
                review_decision=review.decision,
                limitations=limitations,
                review_evidence=self._review_payload(review),
            )
            self._finish_attempt(
                coordinator,
                succeeded=True,
                metadata={
                    "candidate_revision": revision,
                    "qualification_status": "qualified" if final_report.qualified else "pending_external_qualification",
                    "review_decision": review.decision,
                    "repair_cycles": repairs,
                },
            )
            return EngineeringExecutionResult(
                work_order_id=work_order_id,
                attempt_id=spec.attempt_id,
                spec_id=spec.id,
                candidate_revision=revision,
                changed_paths=current.changed_paths,
                verification_passed=None if verification is None else verification.passed,
                repair_cycles=repairs,
                qualification=final_report.to_dict(),
                review=self._review_payload(review),
                status="qualified" if final_report.qualified else "verifying",
            )
        except Exception as exc:
            lease = self.runtime.work_store.get_lease(spec.work_order_id)
            if lease is not None and lease.attempt_id == spec.attempt_id:
                try:
                    order = self.runtime.work_store.get_order(spec.work_order_id)
                    max_attempts = max(1, int(dict(order.retry_policy or {}).get("max_attempts", 1))) if order is not None else 1
                    self.runtime.work_store.finish_attempt(
                        spec.attempt_id,
                        lease_token=lease.lease_token,
                        status=WorkAttemptStatus.FAILED,
                        failure=WorkFailure(
                            failure_class=FailureClass.VALIDATION,
                            code="engineering_execution_failed",
                            message=type(exc).__name__,
                        ),
                        max_attempts=max_attempts,
                    )
                except Exception:
                    self.runtime.work_store.mark_recovery_required(
                        spec.work_order_id,
                        attempt_id=spec.attempt_id,
                        reason=RecoveryReason.UNKNOWN_EFFECT,
                    )
            raise