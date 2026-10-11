from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ReleaseEnvironment, ReleaseEvidence, ReleaseStatus
from .providers import ReleaseDeployment
from .runtime import ReleaseControlRuntime


@dataclass(frozen=True)
class ReleaseMonitorResult:
    release_id: str
    status: str
    outcome: str
    observation_count: int


class ProductionReleaseMonitor:
    """Read-only production observer for releases in MONITORING.

    The monitor never deploys, promotes, rolls back, or mutates source. It may
    observe the exact recorded deployment and run the configured safe production
    smoke provider. Repeated inability to prove deployment health is treated as
    a production regression and routed back into Canonical Work; rollback still
    requires the separate owner-controlled rollback authority.
    """

    _SUCCESS_KIND = "production_monitor_observation"
    _ERROR_KIND = "production_monitor_error"

    def __init__(self, runtime: ReleaseControlRuntime, *, failure_threshold: int = 3) -> None:
        self.runtime = runtime
        self.failure_threshold = max(1, min(int(failure_threshold), 10))

    @classmethod
    def _observation_count(cls, plan) -> int:
        return sum(
            1
            for item in plan.evidence
            if item.kind in {cls._SUCCESS_KIND, cls._ERROR_KIND}
        )

    @classmethod
    def _consecutive_errors(cls, plan) -> int:
        count = 0
        for item in reversed(plan.evidence):
            if item.kind == cls._ERROR_KIND:
                count += 1
                continue
            if item.kind == cls._SUCCESS_KIND:
                break
        return count

    @staticmethod
    def _deployment(plan) -> ReleaseDeployment:
        if not plan.production_deployment_id or not plan.production_url:
            raise RuntimeError("production deployment evidence is missing")
        return ReleaseDeployment(
            id=plan.production_deployment_id,
            provider=plan.provider,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PRODUCTION,
            url=plan.production_url,
            state="ready",
        )

    def _append_success(self, plan, *, observed: ReleaseDeployment, smoke: Any | None):
        metadata: dict[str, Any] = {
            "deployment": observed.to_dict(),
            "smoke": smoke.to_dict() if smoke is not None else None,
        }
        updated = plan.append_evidence(
            ReleaseEvidence(
                kind=self._SUCCESS_KIND,
                summary="Production monitor proved the exact deployment healthy.",
                reference=observed.id,
                revision=plan.candidate_revision,
                trusted=True,
                metadata=metadata,
            )
        )
        return self.runtime.controller.store.save(updated)

    def _append_error(self, plan, *, error_type: str, summary: str):
        updated = plan.append_evidence(
            ReleaseEvidence(
                kind=self._ERROR_KIND,
                summary=summary[:1000],
                revision=plan.candidate_revision,
                trusted=True,
                metadata={"error_type": error_type[:120]},
            )
        )
        return self.runtime.controller.store.save(updated)

    def check_once(self, release_id: str) -> ReleaseMonitorResult:
        plan = self.runtime.controller.require(release_id)
        if plan.status is not ReleaseStatus.MONITORING:
            return ReleaseMonitorResult(plan.id, plan.status.value, "not_monitoring", self._observation_count(plan))

        limit = self.runtime.policy().max_monitoring_observations
        current_count = self._observation_count(plan)
        if current_count >= limit:
            return ReleaseMonitorResult(plan.id, plan.status.value, "observation_limit_reached", current_count)

        try:
            provider = self.runtime.provider(plan.provider)
            observed = provider.observe(self._deployment(plan))
            self.runtime.controller._validate_deployment(plan, observed, ReleaseEnvironment.PRODUCTION)

            smoke = None
            if self.runtime.policy().require_production_smoke:
                smoke_provider = self.runtime.controller.production_smoke
                if smoke_provider is None:
                    raise RuntimeError("production smoke provider is unavailable")
                smoke = smoke_provider.smoke_production(
                    target=plan.production_url,
                    release_revision=plan.candidate_revision,
                )
                if not smoke.passed:
                    raise RuntimeError("production smoke check failed")

            plan = self._append_success(plan, observed=observed, smoke=smoke)
            return ReleaseMonitorResult(
                plan.id,
                plan.status.value,
                "healthy",
                self._observation_count(plan),
            )
        except Exception as exc:
            # Provider/network failures can be transient. Record bounded evidence
            # first and recommend rollback only after repeated consecutive
            # failures, while preserving the separate rollback authority.
            plan = self._append_error(
                plan,
                error_type=type(exc).__name__,
                summary=f"Production monitor could not prove release health: {type(exc).__name__}",
            )
            failures = self._consecutive_errors(plan)
            if failures >= self.failure_threshold:
                plan = self.runtime.controller.store.save(
                    plan.with_update(status=ReleaseStatus.ROLLBACK_RECOMMENDED)
                )
                self.runtime.controller.observe_regression(
                    plan.id,
                    signal=f"production monitor failed {failures} consecutive observations",
                    evidence=(f"release-monitor:{plan.id}",),
                    severity="high",
                )
                return ReleaseMonitorResult(
                    plan.id,
                    plan.status.value,
                    "rollback_recommended",
                    self._observation_count(plan),
                )
            return ReleaseMonitorResult(
                plan.id,
                plan.status.value,
                "transient_failure",
                self._observation_count(plan),
            )

    def poll_all(self) -> tuple[ReleaseMonitorResult, ...]:
        results: list[ReleaseMonitorResult] = []
        for plan in self.runtime.controller.store.list():
            if plan.status is ReleaseStatus.MONITORING:
                results.append(self.check_once(plan.id))
        return tuple(results)
