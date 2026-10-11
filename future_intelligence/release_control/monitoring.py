from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from future_intelligence.engineering.canary import CanaryThresholds

from .contracts import ReleaseEnvironment, ReleaseEvidence, ReleaseStatus
from .providers import ReleaseDeployment
from .runtime import ReleaseControlRuntime
from .telemetry import ProductionTelemetryObservation


@dataclass(frozen=True)
class ReleaseMonitorResult:
    release_id: str
    status: str
    outcome: str
    observation_count: int


class ProductionReleaseMonitor:
    """Read-only production observer for releases in MONITORING.

    The monitor never deploys, promotes, rolls back, or mutates source. It first
    proves the exact recorded deployment and configured production smoke checks.
    Provider-native telemetry is then sampled read-only when available. Only
    sanitized aggregate telemetry is persisted; raw logs are never retained.

    A sufficiently large provider sample with a server-error rate above the same
    conservative absolute threshold used by canary analysis becomes a production
    regression and is routed to Canonical Work. Telemetry transport/permission
    failures are recorded separately and never become rollback authority by
    themselves. Rollback still requires the separate owner-controlled authority.
    """

    _SUCCESS_KIND = "production_monitor_observation"
    _ERROR_KIND = "production_monitor_error"
    _TELEMETRY_KIND = "production_provider_telemetry"
    _TELEMETRY_ERROR_KIND = "production_provider_telemetry_error"

    def __init__(
        self,
        runtime: ReleaseControlRuntime,
        *,
        failure_threshold: int = 3,
        telemetry_window_seconds: int = 300,
    ) -> None:
        self.runtime = runtime
        self.failure_threshold = max(1, min(int(failure_threshold), 10))
        self.telemetry_window_seconds = max(30, min(int(telemetry_window_seconds), 3_600))

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

    def _append_success(
        self,
        plan,
        *,
        observed: ReleaseDeployment,
        smoke: Any | None,
        telemetry: ProductionTelemetryObservation | None,
        telemetry_available: bool,
    ):
        metadata: dict[str, Any] = {
            "deployment": observed.to_dict(),
            "smoke": smoke.to_dict() if smoke is not None else None,
            "provider_telemetry_available": telemetry_available,
            "provider_telemetry_observed": telemetry is not None,
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

    def _append_telemetry(self, plan, telemetry: ProductionTelemetryObservation):
        if telemetry.provider != plan.provider or telemetry.deployment_id != plan.production_deployment_id:
            raise RuntimeError("provider telemetry is not bound to the recorded production deployment")
        updated = plan.append_evidence(
            ReleaseEvidence(
                kind=self._TELEMETRY_KIND,
                summary=(
                    f"Provider telemetry sampled {telemetry.request_count} requests; "
                    f"server error rate {telemetry.error_rate:.4f}."
                ),
                reference=";".join(telemetry.references),
                revision=plan.candidate_revision,
                trusted=True,
                metadata=telemetry.to_safe_dict(),
            )
        )
        return self.runtime.controller.store.save(updated)

    def _append_telemetry_error(self, plan, exc: Exception):
        updated = plan.append_evidence(
            ReleaseEvidence(
                kind=self._TELEMETRY_ERROR_KIND,
                summary=f"Provider telemetry was unavailable: {type(exc).__name__}",
                revision=plan.candidate_revision,
                trusted=True,
                metadata={
                    "error_type": type(exc).__name__[:120],
                    "application_regression_proven": False,
                    "automatic_rollback_authority": False,
                },
            )
        )
        return self.runtime.controller.store.save(updated)

    def _telemetry_incident(self, telemetry: ProductionTelemetryObservation) -> bool:
        policy = self.runtime.policy()
        minimum = max(1, int(policy.canary_min_requests))
        absolute_error_threshold = CanaryThresholds().max_error_rate_absolute
        return telemetry.request_count >= minimum and telemetry.error_rate > absolute_error_threshold

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

            telemetry = None
            telemetry_available = callable(getattr(provider, "collect_production_telemetry", None))
            telemetry_failed = False
            if telemetry_available:
                try:
                    telemetry = provider.collect_production_telemetry(
                        observed,
                        window_seconds=self.telemetry_window_seconds,
                    )
                    plan = self._append_telemetry(plan, telemetry)
                except Exception as exc:
                    # Telemetry APIs can be permission/plan/transport limited.
                    # Record the missing observation, but never turn telemetry
                    # unavailability itself into an application rollback signal.
                    plan = self._append_telemetry_error(plan, exc)
                    telemetry_failed = True

            if telemetry is not None and self._telemetry_incident(telemetry):
                plan = self.runtime.controller.store.save(
                    plan.with_update(status=ReleaseStatus.ROLLBACK_RECOMMENDED)
                )
                self.runtime.controller.observe_regression(
                    plan.id,
                    signal=(
                        "provider telemetry detected elevated production server errors: "
                        f"{telemetry.server_error_count}/{telemetry.request_count} "
                        f"({telemetry.error_rate:.4f})"
                    ),
                    evidence=(f"provider-telemetry:{plan.provider}:{plan.production_deployment_id}",),
                    severity="high",
                )
                return ReleaseMonitorResult(
                    plan.id,
                    plan.status.value,
                    "rollback_recommended",
                    self._observation_count(plan),
                )

            plan = self._append_success(
                plan,
                observed=observed,
                smoke=smoke,
                telemetry=telemetry,
                telemetry_available=telemetry_available,
            )
            return ReleaseMonitorResult(
                plan.id,
                plan.status.value,
                "healthy_telemetry_unavailable" if telemetry_failed else "healthy",
                self._observation_count(plan),
            )
        except Exception as exc:
            # Provider deployment observation/smoke failures can be transient.
            # Record bounded evidence first and recommend rollback only after
            # repeated consecutive failures. Telemetry failures are handled above
            # and deliberately do not enter this path.
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
