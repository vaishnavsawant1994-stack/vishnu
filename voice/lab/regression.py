"""Fail-closed baseline regression detection for Voice Lab."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evaluation import GateStatus, QualificationGate


class MetricDirection(str, Enum):
    LOWER = "lower"
    HIGHER = "higher"


@dataclass(frozen=True, slots=True)
class RegressionRule:
    metric: str
    direction: MetricDirection
    max_relative_degradation: float = 0.05
    max_absolute_degradation: float = 0.0

    def __post_init__(self) -> None:
        if self.max_relative_degradation < 0 or self.max_absolute_degradation < 0:
            raise ValueError("regression tolerances cannot be negative")


@dataclass(frozen=True, slots=True)
class RegressionFinding:
    metric: str
    status: str
    baseline: float | None
    current: float | None
    allowed: float | None
    reason: str = ""


DEFAULT_REGRESSION_RULES = (
    RegressionRule("wer", MetricDirection.LOWER, 0.10, 0.01),
    RegressionRule("cer", MetricDirection.LOWER, 0.10, 0.01),
    RegressionRule("endpoint_latency_ms", MetricDirection.LOWER, 0.10, 25.0),
    RegressionRule("first_audio_latency_ms", MetricDirection.LOWER, 0.10, 50.0),
    RegressionRule("real_time_factor", MetricDirection.LOWER, 0.10, 0.05),
    RegressionRule("barge_in_latency_ms", MetricDirection.LOWER, 0.10, 25.0),
    RegressionRule("dropped_audio_blocks", MetricDirection.LOWER, 0.0, 0.0),
    RegressionRule("code_switch_retention", MetricDirection.HIGHER, 0.05, 0.02),
    RegressionRule("pronunciation_accuracy", MetricDirection.HIGHER, 0.05, 0.02),
)

EXTENDED_REGRESSION_RULES = (
    RegressionRule("failure_recovery_rate", MetricDirection.HIGHER, 0.02, 0.01),
    RegressionRule("acoustic_quality_score", MetricDirection.HIGHER, 0.05, 0.02),
    RegressionRule("cpu_percent", MetricDirection.LOWER, 0.10, 5.0),
    RegressionRule("memory_mb", MetricDirection.LOWER, 0.10, 32.0),
    RegressionRule("peak_memory_mb", MetricDirection.LOWER, 0.10, 32.0),
    RegressionRule("telephony_connect_latency_ms", MetricDirection.LOWER, 0.10, 100.0),
    RegressionRule("telephony_jitter_ms", MetricDirection.LOWER, 0.10, 3.0),
    RegressionRule("telephony_packet_loss_rate", MetricDirection.LOWER, 0.10, 0.005),
    RegressionRule("telephony_call_completion_rate", MetricDirection.HIGHER, 0.02, 0.01),
    RegressionRule("estimated_cost_per_minute", MetricDirection.LOWER, 0.10, 0.01),
    RegressionRule("failure_rate", MetricDirection.LOWER, 0.05, 0.01),
)


class RegressionEngine:
    @staticmethod
    def _select_rules(
        baseline: dict[str, float] | None,
        current: dict[str, float],
        rules: tuple[RegressionRule, ...] | None,
    ) -> tuple[RegressionRule, ...]:
        if rules is not None:
            return rules
        known = set(current)
        if baseline:
            known.update(baseline)
        extended = tuple(rule for rule in EXTENDED_REGRESSION_RULES if rule.metric in known)
        return (*DEFAULT_REGRESSION_RULES, *extended)

    def compare(
        self,
        baseline: dict[str, float] | None,
        current: dict[str, float],
        rules: tuple[RegressionRule, ...] | None = None,
    ) -> tuple[RegressionFinding, ...]:
        selected = self._select_rules(baseline, current, rules)
        if baseline is None:
            return tuple(
                RegressionFinding(rule.metric, "blocked", None, current.get(rule.metric), None, "baseline unavailable")
                for rule in selected
            )
        findings = []
        for rule in selected:
            if rule.metric not in baseline or rule.metric not in current:
                findings.append(
                    RegressionFinding(
                        rule.metric,
                        "blocked",
                        baseline.get(rule.metric),
                        current.get(rule.metric),
                        None,
                        "metric missing",
                    )
                )
                continue
            old = float(baseline[rule.metric])
            new = float(current[rule.metric])
            allowance = max(rule.max_absolute_degradation, abs(old) * rule.max_relative_degradation)
            degradation = new - old if rule.direction is MetricDirection.LOWER else old - new
            findings.append(
                RegressionFinding(
                    rule.metric,
                    "pass" if degradation <= allowance else "fail",
                    old,
                    new,
                    allowance,
                )
            )
        return tuple(findings)

    def qualification_gate(
        self,
        baseline: dict[str, float] | None,
        current: dict[str, float],
        rules: tuple[RegressionRule, ...] | None = None,
    ) -> tuple[QualificationGate, tuple[RegressionFinding, ...]]:
        findings = self.compare(baseline, current, rules)
        statuses = {item.status for item in findings}
        if "fail" in statuses:
            status = GateStatus.FAIL
        elif "blocked" in statuses:
            status = GateStatus.BLOCKED
        else:
            status = GateStatus.PASS
        summary = ", ".join(f"{item.metric}:{item.status}" for item in findings)
        return QualificationGate("baseline-regression", status, notes=summary), findings
