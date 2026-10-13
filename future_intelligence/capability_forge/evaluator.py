from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from future_intelligence.engineering.canary import (
    CanaryMetrics,
    CanaryThresholds,
    compare_canary,
)


@dataclass(frozen=True)
class GeneratedCapabilityHealth:
    capability_id: str
    active_version: str | None
    baseline_version: str | None
    active: CanaryMetrics | None
    baseline: CanaryMetrics | None
    state: str
    rollback_recommended: bool
    reasons: tuple[str, ...]
    sufficient_evidence: bool
    automatic_rollback_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        def metrics(value):
            return None if value is None else {
                "sample_count": value.sample_count,
                "error_rate": value.error_rate,
                "p95_latency_ms": value.p95_latency_ms,
            }
        return {
            "capability_id": self.capability_id,
            "active_version": self.active_version,
            "baseline_version": self.baseline_version,
            "active": metrics(self.active),
            "baseline": metrics(self.baseline),
            "state": self.state,
            "rollback_recommended": self.rollback_recommended,
            "reasons": list(self.reasons),
            "sufficient_evidence": self.sufficient_evidence,
            "automatic_rollback_authority": False,
        }


class GeneratedCapabilityEvaluator:
    """Read-only health/canary evaluator over Forge invocation evidence.

    It can recommend rollback but intentionally has no rollback or activation
    authority. Owner approval remains required by CapabilityActivationService.
    """

    def __init__(self, lifecycle, *, events=None, thresholds: CanaryThresholds | None = None):
        self.lifecycle = lifecycle
        self.events = events
        self.thresholds = thresholds or CanaryThresholds()

    def _metrics(self, capability_id: str, version: str, *, limit: int = 500) -> CanaryMetrics:
        limit = max(1, min(int(limit), 5000))
        with self.lifecycle._con() as con:
            rows = con.execute(
                """
                SELECT ok,duration_ms FROM forge_invocations
                WHERE capability_id=? AND version=?
                ORDER BY id DESC LIMIT ?
                """,
                (str(capability_id), str(version), limit),
            ).fetchall()
        count = len(rows)
        failures = sum(1 for row in rows if not int(row["ok"]))
        latencies = sorted(float(row["duration_ms"]) for row in rows)
        if latencies:
            index = max(0, min(len(latencies) - 1, ceil(0.95 * len(latencies)) - 1))
            p95 = latencies[index]
        else:
            p95 = 0.0
        return CanaryMetrics(
            sample_count=count,
            error_rate=(failures / count) if count else 0.0,
            p95_latency_ms=p95,
        )

    def evaluate(self, capability_id: str) -> GeneratedCapabilityHealth:
        active = self.lifecycle.active_activation(str(capability_id))
        if not active:
            return GeneratedCapabilityHealth(
                capability_id=str(capability_id),
                active_version=None,
                baseline_version=None,
                active=None,
                baseline=None,
                state="inactive",
                rollback_recommended=False,
                reasons=("no active generated capability version",),
                sufficient_evidence=False,
            )
        active_version = str(active["version"])
        active_metrics = self._metrics(str(capability_id), active_version)
        previous = self.lifecycle.previous_activation(str(capability_id))
        if previous is None:
            sufficient = active_metrics.sample_count >= self.thresholds.min_sample_count
            reasons: list[str] = []
            if sufficient and active_metrics.error_rate > self.thresholds.max_error_rate_absolute:
                reasons.append("active generated capability error rate exceeds absolute threshold")
            state = "degraded" if reasons else ("healthy" if sufficient else "observing")
            result = GeneratedCapabilityHealth(
                capability_id=str(capability_id),
                active_version=active_version,
                baseline_version=None,
                active=active_metrics,
                baseline=None,
                state=state,
                rollback_recommended=False,
                reasons=tuple(reasons) if reasons else (("insufficient canary sample size",) if not sufficient else ()),
                sufficient_evidence=sufficient,
            )
        else:
            baseline_version = str(previous["version"])
            baseline_metrics = self._metrics(str(capability_id), baseline_version)
            recommendation = compare_canary(
                baseline_metrics,
                active_metrics,
                thresholds=self.thresholds,
            )
            result = GeneratedCapabilityHealth(
                capability_id=str(capability_id),
                active_version=active_version,
                baseline_version=baseline_version,
                active=active_metrics,
                baseline=baseline_metrics,
                state=(
                    "rollback_recommended" if recommendation.recommended
                    else ("healthy" if recommendation.sufficient_evidence else "observing")
                ),
                rollback_recommended=recommendation.recommended,
                reasons=recommendation.reasons,
                sufficient_evidence=recommendation.sufficient_evidence,
            )
        if self.events is not None:
            self.events.emit(
                "capability_forge.health_evaluated",
                capability_id=result.capability_id,
                active_version=result.active_version,
                baseline_version=result.baseline_version,
                state=result.state,
                rollback_recommended=result.rollback_recommended,
                automatic_rollback_authority=False,
            )
        return result
