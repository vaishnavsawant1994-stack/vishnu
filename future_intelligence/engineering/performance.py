from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class PerformanceBudget:
    max_first_usable_ms: float | None = None
    max_api_p95_ms: float | None = None
    max_bundle_bytes: int | None = None
    max_request_count: int | None = None
    max_layout_shift: float | None = None


@dataclass(frozen=True)
class PerformanceResult:
    metrics: Mapping[str, float] = field(default_factory=dict)
    violations: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations


def evaluate_performance(metrics: Mapping[str, float], budget: PerformanceBudget) -> PerformanceResult:
    checks = (
        ("first_usable_ms", budget.max_first_usable_ms),
        ("api_p95_ms", budget.max_api_p95_ms),
        ("bundle_bytes", float(budget.max_bundle_bytes) if budget.max_bundle_bytes is not None else None),
        ("request_count", float(budget.max_request_count) if budget.max_request_count is not None else None),
        ("layout_shift", budget.max_layout_shift),
    )
    violations: list[str] = []
    for name, maximum in checks:
        if maximum is None or name not in metrics:
            continue
        actual = float(metrics[name])
        if actual > maximum:
            violations.append(f"{name}={actual:g} exceeds budget {maximum:g}")
    return PerformanceResult(dict(metrics), tuple(violations))
