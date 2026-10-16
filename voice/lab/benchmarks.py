"""Dependency-light objective metrics for Voice Lab qualification."""
from __future__ import annotations

from dataclasses import dataclass
import math
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


def _bounded_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, float(numerator) / float(denominator)))


def _finite_non_negative(name: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return result


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


def acoustic_quality_score(*, snr_db: float, clipping_ratio: float, dropped_ratio: float = 0.0) -> float:
    """Return a bounded 0..1 objective signal-quality score.

    SNR contributes 60%, low clipping 25%, and low dropped-audio ratio 15%.
    This is a qualification signal, not a claim of human-perceived naturalness or MOS.
    """

    snr = max(0.0, min(1.0, float(snr_db) / 30.0))
    clipping = 1.0 - max(0.0, min(1.0, float(clipping_ratio) / 0.05))
    dropped = 1.0 - max(0.0, min(1.0, float(dropped_ratio) / 0.05))
    return round((snr * 0.60) + (clipping * 0.25) + (dropped * 0.15), 6)


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
    MetricThreshold("failure-recovery-rate", "failure_recovery_rate", 0.95, False),
    MetricThreshold("acoustic-quality-score", "acoustic_quality_score", 0.80, False),
    MetricThreshold("telephony-connect-latency", "telephony_connect_latency_ms", 3000.0),
    MetricThreshold("telephony-jitter", "telephony_jitter_ms", 30.0),
    MetricThreshold("telephony-packet-loss", "telephony_packet_loss_rate", 0.02),
    MetricThreshold("telephony-call-completion", "telephony_call_completion_rate", 0.99, False),
)


class BenchmarkEngine:
    def __init__(self, thresholds: tuple[MetricThreshold, ...] = DEFAULT_THRESHOLDS):
        self.thresholds = thresholds

    def speech_recognition_metrics(self, reference: str, hypothesis: str) -> dict[str, float]:
        return {"wer": word_error_rate(reference, hypothesis), "cer": character_error_rate(reference, hypothesis)}

    def reliability_metrics(
        self,
        *,
        successful_runs: int,
        total_runs: int,
        recovered_failures: int = 0,
        provider_failures: int = 0,
    ) -> dict[str, float]:
        if min(successful_runs, total_runs, recovered_failures, provider_failures) < 0:
            raise ValueError("reliability counters cannot be negative")
        if successful_runs > total_runs:
            raise ValueError("successful_runs cannot exceed total_runs")
        success_rate = _bounded_ratio(successful_runs, total_runs)
        recovery_rate = 1.0 if provider_failures == 0 else _bounded_ratio(recovered_failures, provider_failures)
        return {
            "success_rate": success_rate,
            "failure_recovery_rate": recovery_rate,
            "provider_failures": float(provider_failures),
        }

    def resource_metrics(
        self,
        *,
        cpu_percent: float,
        memory_mb: float,
        peak_memory_mb: float | None = None,
    ) -> dict[str, float]:
        metrics = {
            "cpu_percent": _finite_non_negative("cpu_percent", cpu_percent),
            "memory_mb": _finite_non_negative("memory_mb", memory_mb),
        }
        if peak_memory_mb is not None:
            metrics["peak_memory_mb"] = _finite_non_negative("peak_memory_mb", peak_memory_mb)
        return metrics

    def acoustic_metrics(
        self,
        *,
        snr_db: float,
        clipping_ratio: float,
        dropped_ratio: float = 0.0,
    ) -> dict[str, float]:
        return {
            "snr_db": float(snr_db),
            "clipping_ratio": float(clipping_ratio),
            "dropped_ratio": float(dropped_ratio),
            "acoustic_quality_score": acoustic_quality_score(
                snr_db=snr_db,
                clipping_ratio=clipping_ratio,
                dropped_ratio=dropped_ratio,
            ),
        }

    def telephony_metrics(
        self,
        *,
        connect_latency_ms: float,
        connected: bool,
        jitter_ms: float | None = None,
        packet_loss_rate: float | None = None,
    ) -> dict[str, float]:
        metrics = {
            "telephony_connect_latency_ms": _finite_non_negative("connect_latency_ms", connect_latency_ms),
            "telephony_call_completion_rate": 1.0 if connected else 0.0,
        }
        if jitter_ms is not None:
            metrics["telephony_jitter_ms"] = _finite_non_negative("jitter_ms", jitter_ms)
        if packet_loss_rate is not None:
            loss = float(packet_loss_rate)
            if not math.isfinite(loss) or not 0.0 <= loss <= 1.0:
                raise ValueError("packet_loss_rate must be between 0 and 1")
            metrics["telephony_packet_loss_rate"] = loss
        return metrics

    def numeric_gates(self, metrics: dict[str, float]) -> tuple[QualificationGate, ...]:
        return tuple(item.evaluate(metrics) for item in self.thresholds)
