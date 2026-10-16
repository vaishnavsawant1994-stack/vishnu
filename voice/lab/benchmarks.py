"""Dependency-light objective metrics for Voice Lab qualification."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .evaluation import GateStatus, QualificationGate


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = _tokens(reference)
    hyp = _tokens(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = list(reference.casefold())
    hyp = list(hypothesis.casefold())
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def retention_score(expected: Iterable[str], observed: str) -> float:
    wanted = [item.casefold().strip() for item in expected if item.strip()]
    if not wanted:
        return 1.0
    body = observed.casefold()
    return sum(item in body for item in wanted) / len(wanted)


@dataclass(frozen=True, slots=True)
class MetricThreshold:
    gate_id: str
    metric: str
    limit: float
    lower_is_better: bool = True

    def evaluate(self, metrics: dict[str, float]) -> QualificationGate:
        if self.metric not in metrics:
            return QualificationGate(self.gate_id, GateStatus.BLOCKED, notes=f"missing metric: {self.metric}")
        value = float(metrics[self.metric])
        passed = value <= self.limit if self.lower_is_better else value >= self.limit
        operator = "<=" if self.lower_is_better else ">="
        return QualificationGate(
            self.gate_id,
            GateStatus.PASS if passed else GateStatus.FAIL,
            observed=value,
            threshold=f"{operator} {self.limit}",
        )


DEFAULT_THRESHOLDS = (
    MetricThreshold("stt-wer", "wer", 0.15),
    MetricThreshold("stt-cer", "cer", 0.10),
    MetricThreshold("endpoint-latency", "endpoint_latency_ms", 650.0),
    MetricThreshold("first-audio-latency", "first_audio_latency_ms", 1200.0),
    MetricThreshold("real-time-factor", "real_time_factor", 1.0),
    MetricThreshold("barge-in-cancellation-latency", "barge_in_latency_ms", 300.0),
    MetricThreshold("dropped-audio-blocks", "dropped_audio_blocks", 0.0),
    MetricThreshold("code-switch-retention", "code_switch_retention", 0.90, False),
    MetricThreshold("pronunciation-accuracy", "pronunciation_accuracy", 0.90, False),
)


class BenchmarkEngine:
    def __init__(self, thresholds: tuple[MetricThreshold, ...] = DEFAULT_THRESHOLDS):
        self.thresholds = thresholds

    def speech_recognition_metrics(self, reference: str, hypothesis: str) -> dict[str, float]:
        return {"wer": word_error_rate(reference, hypothesis), "cer": character_error_rate(reference, hypothesis)}

    def numeric_gates(self, metrics: dict[str, float]) -> tuple[QualificationGate, ...]:
        return tuple(item.evaluate(metrics) for item in self.thresholds)
