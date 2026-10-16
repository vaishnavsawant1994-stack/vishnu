"""Fail-closed qualification evidence for Vishnu Voice Lab experiments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"
    BLOCKED = "blocked"


class ReportStatus(str, Enum):
    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"


@dataclass(frozen=True, slots=True)
class QualificationGate:
    """One objective or governance gate from a Voice Lab run."""

    gate_id: str
    status: GateStatus
    observed: Any = None
    threshold: str = ""
    notes: str = ""


BASELINE_REQUIRED_GATES: tuple[str, ...] = (
    "stt-wer",
    "stt-cer",
    "endpoint-latency",
    "first-audio-latency",
    "real-time-factor",
    "barge-in-cancellation-latency",
    "dropped-audio-blocks",
    "stale-output-rejection",
    "code-switch-retention",
    "pronunciation-accuracy",
    "canonical-authority-preserved",
    "no-raw-audio-retention",
    "consent-revocation-integrity",
    "model-license-provenance-integrity",
    "provider-failure-fallback",
    "device-route-correctness",
    "mcp-risk-floor",
)


@dataclass(frozen=True, slots=True)
class VoiceLabReport:
    """Evidence for one exact provider/model/device experiment.

    A report is deliberately fail-closed: every required gate must exist exactly
    once and pass. Unknown, missing, not-run, blocked, failed or duplicate gates
    prevent qualification.
    """

    experiment_id: str
    provider: str
    model: str
    device: str
    language: str
    gates: tuple[QualificationGate, ...]
    required_gate_ids: tuple[str, ...] = BASELINE_REQUIRED_GATES

    def gate(self, gate_id: str) -> QualificationGate | None:
        matches = tuple(item for item in self.gates if item.gate_id == gate_id)
        return matches[0] if len(matches) == 1 else None

    @property
    def missing_gate_ids(self) -> tuple[str, ...]:
        present_once = {
            gate_id
            for gate_id in self.required_gate_ids
            if sum(item.gate_id == gate_id for item in self.gates) == 1
        }
        return tuple(gate_id for gate_id in self.required_gate_ids if gate_id not in present_once)

    @property
    def non_passing_gate_ids(self) -> tuple[str, ...]:
        result: list[str] = []
        for gate_id in self.required_gate_ids:
            gate = self.gate(gate_id)
            if gate is None or gate.status is not GateStatus.PASS:
                result.append(gate_id)
        return tuple(result)

    @property
    def status(self) -> ReportStatus:
        return ReportStatus.QUALIFIED if not self.non_passing_gate_ids else ReportStatus.NOT_QUALIFIED

    @property
    def is_qualified(self) -> bool:
        return self.status is ReportStatus.QUALIFIED


def passed_gate(gate_id: str, observed: Any = None, threshold: str = "", notes: str = "") -> QualificationGate:
    """Convenience constructor used by qualification harnesses and tests."""

    return QualificationGate(
        gate_id=gate_id,
        status=GateStatus.PASS,
        observed=observed,
        threshold=threshold,
        notes=notes,
    )
