from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CanaryThresholds:
    max_error_rate_absolute: float = 0.05
    max_error_rate_increase: float = 0.02
    max_p95_latency_ratio: float = 1.5
    min_sample_count: int = 20

    def __post_init__(self) -> None:
        if not 0 <= self.max_error_rate_absolute <= 1:
            raise ValueError("max_error_rate_absolute must be between 0 and 1")
        if not 0 <= self.max_error_rate_increase <= 1:
            raise ValueError("max_error_rate_increase must be between 0 and 1")
        if self.max_p95_latency_ratio < 1:
            raise ValueError("max_p95_latency_ratio must be at least 1")
        if self.min_sample_count < 1:
            raise ValueError("min_sample_count must be positive")


@dataclass(frozen=True)
class CanaryMetrics:
    sample_count: int
    error_rate: float
    p95_latency_ms: float

    def __post_init__(self) -> None:
        if self.sample_count < 0 or not 0 <= self.error_rate <= 1 or self.p95_latency_ms < 0:
            raise ValueError("invalid canary metrics")


@dataclass(frozen=True)
class RollbackRecommendation:
    recommended: bool
    reasons: tuple[str, ...]
    sufficient_evidence: bool
    automatic_rollback_authority: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "recommended": self.recommended,
            "reasons": list(self.reasons),
            "sufficient_evidence": self.sufficient_evidence,
            "automatic_rollback_authority": False,
        }


def compare_canary(
    baseline: CanaryMetrics,
    candidate: CanaryMetrics,
    *,
    thresholds: CanaryThresholds = CanaryThresholds(),
    additional_checks: Mapping[str, bool] | None = None,
) -> RollbackRecommendation:
    if baseline.sample_count < thresholds.min_sample_count or candidate.sample_count < thresholds.min_sample_count:
        return RollbackRecommendation(False, ("insufficient canary sample size",), False)
    reasons: list[str] = []
    if candidate.error_rate > thresholds.max_error_rate_absolute:
        reasons.append("candidate error rate exceeds absolute threshold")
    if candidate.error_rate - baseline.error_rate > thresholds.max_error_rate_increase:
        reasons.append("candidate error rate regressed relative to baseline")
    if baseline.p95_latency_ms > 0 and candidate.p95_latency_ms / baseline.p95_latency_ms > thresholds.max_p95_latency_ratio:
        reasons.append("candidate p95 latency regressed relative to baseline")
    for name, passed in dict(additional_checks or {}).items():
        if not bool(passed):
            reasons.append(f"canary check failed: {name}")
    return RollbackRecommendation(bool(reasons), tuple(reasons), True)
