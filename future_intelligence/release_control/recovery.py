from __future__ import annotations

from dataclasses import dataclass

from .contracts import ReleaseEnvironment, ReleaseEvidence, ReleaseStatus
from .providers import ReleaseDeployment
from .runtime import ReleaseControlRuntime


@dataclass(frozen=True)
class ReleaseRecoveryResult:
    release_id: str
    action: str
    status: str


class ReleaseRecoveryService:
    """Reconcile persisted releases after a process restart without replaying writes.

    The critical invariant is that a crash around an authority-bearing provider
    call must never cause a second deploy or rollback merely because Vishnu lost
    its in-memory thread. If a deployment ID was durably recorded, recovery may
    observe and re-run read-only qualification. If it was not recorded, the
    release moves to RECOVERY_REQUIRED for owner/provider reconciliation.
    """

    def __init__(self, runtime: ReleaseControlRuntime) -> None:
        self.runtime = runtime

    def _recovery_required(self, plan, reason: str) -> ReleaseRecoveryResult:
        updated = plan.with_update(status=ReleaseStatus.RECOVERY_REQUIRED).append_evidence(
            ReleaseEvidence(
                kind="release_recovery_required",
                summary=reason,
                revision=plan.candidate_revision,
                trusted=True,
                metadata={"previous_status": plan.status.value},
            )
        )
        self.runtime.controller.store.save(updated)
        return ReleaseRecoveryResult(plan.id, "owner_reconciliation_required", updated.status.value)

    def _resume_preview_qualification(self, plan) -> ReleaseRecoveryResult:
        if not plan.preview_deployment_id or not plan.preview_url:
            return self._recovery_required(
                plan,
                "Preview provider action may have occurred before durable deployment evidence was recorded.",
            )
        provider = self.runtime.provider(plan.provider)
        deployment = ReleaseDeployment(
            id=plan.preview_deployment_id,
            provider=plan.provider,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PREVIEW,
            url=plan.preview_url,
            state="ready",
        )
        observed = provider.observe(deployment)
        self.runtime.controller._validate_deployment(plan, observed, ReleaseEnvironment.PREVIEW)
        qualifier = self.runtime.controller.preview_qualifier
        if qualifier is None:
            return self._recovery_required(plan, "Preview qualification provider is unavailable after restart.")
        result = qualifier.qualify_preview(
            target=plan.preview_url,
            spec_id=plan.engineering_spec_id,
            candidate_revision=plan.candidate_revision,
        )
        updated = plan.append_evidence(
            ReleaseEvidence(
                kind="preview_qualification_recovered",
                summary=result.summary or ("Recovered preview qualification passed." if result.passed else "Recovered preview qualification failed."),
                reference=";".join(result.evidence),
                revision=plan.candidate_revision,
                trusted=True,
                metadata=result.to_dict(),
            )
        ).with_update(status=ReleaseStatus.PREVIEW_QUALIFIED if result.passed else ReleaseStatus.FAILED)
        self.runtime.controller.store.save(updated)
        return ReleaseRecoveryResult(plan.id, "preview_requalified", updated.status.value)

    def _resume_production_qualification(self, plan) -> ReleaseRecoveryResult:
        if not plan.production_deployment_id or not plan.production_url:
            return self._recovery_required(
                plan,
                "Production provider action may have occurred before durable deployment evidence was recorded.",
            )
        provider = self.runtime.provider(plan.provider)
        deployment = ReleaseDeployment(
            id=plan.production_deployment_id,
            provider=plan.provider,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PRODUCTION,
            url=plan.production_url,
            state="ready",
        )
        observed = provider.observe(deployment)
        self.runtime.controller._validate_deployment(plan, observed, ReleaseEnvironment.PRODUCTION)
        smoke = self.runtime.controller.production_smoke
        if self.runtime.policy().require_production_smoke and smoke is None:
            return self._recovery_required(plan, "Production smoke provider is unavailable after restart.")
        updated = plan
        if self.runtime.policy().require_production_smoke:
            result = smoke.smoke_production(
                target=plan.production_url,
                release_revision=plan.candidate_revision,
            )
            updated = updated.append_evidence(
                ReleaseEvidence(
                    kind="production_smoke_recovered",
                    summary=result.summary or ("Recovered production smoke passed." if result.passed else "Recovered production smoke failed."),
                    reference=";".join(result.evidence),
                    revision=plan.candidate_revision,
                    trusted=True,
                    metadata=result.to_dict(),
                )
            )
            if not result.passed:
                updated = updated.with_update(status=ReleaseStatus.ROLLBACK_RECOMMENDED)
                self.runtime.controller.store.save(updated)
                self.runtime.controller.observe_regression(
                    plan.id,
                    signal="production smoke failed during restart reconciliation",
                    evidence=("release-recovery:production-smoke",),
                    severity="high",
                )
                return ReleaseRecoveryResult(plan.id, "production_smoke_failed", ReleaseStatus.ROLLBACK_RECOMMENDED.value)
        updated = updated.with_update(
            status=ReleaseStatus.MONITORING if self.runtime.policy().require_canary else ReleaseStatus.SUCCEEDED
        )
        self.runtime.controller.store.save(updated)
        return ReleaseRecoveryResult(plan.id, "production_requalified", updated.status.value)

    def reconcile(self) -> tuple[ReleaseRecoveryResult, ...]:
        results: list[ReleaseRecoveryResult] = []
        for plan in self.runtime.controller.store.list():
            if plan.status.terminal or plan.status in {
                ReleaseStatus.MONITORING,
                ReleaseStatus.ROLLBACK_RECOMMENDED,
                ReleaseStatus.RECOVERY_REQUIRED,
                ReleaseStatus.AWAITING_APPROVAL,
            }:
                continue
            try:
                if plan.status is ReleaseStatus.PREVIEW_QUALIFYING:
                    results.append(self._resume_preview_qualification(plan))
                elif plan.status is ReleaseStatus.PRODUCTION_QUALIFYING:
                    results.append(self._resume_production_qualification(plan))
                elif plan.status in {
                    ReleaseStatus.PREVIEWING,
                    ReleaseStatus.PROMOTING,
                    ReleaseStatus.ROLLING_BACK,
                }:
                    results.append(self._recovery_required(
                        plan,
                        "An authority-bearing provider action was interrupted before its outcome was durably known; automatic replay is prohibited.",
                    ))
                else:
                    results.append(ReleaseRecoveryResult(plan.id, "safe_to_resume", plan.status.value))
            except Exception as exc:
                results.append(self._recovery_required(
                    plan,
                    f"Restart reconciliation could not prove provider state ({type(exc).__name__}); automatic replay is prohibited.",
                ))
        return tuple(results)
