from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import EngineeringSpec, QualificationGateResult, QualificationGateStatus, QualificationReport


@dataclass(frozen=True)
class VerificationObservation:
    gate: str
    passed: bool
    summary: str = ""
    evidence: tuple[str, ...] = ()
    warning: bool = False
    metadata: Mapping[str, object] | None = None

    def to_gate(self) -> QualificationGateResult:
        if self.passed and not self.evidence:
            return QualificationGateResult(
                self.gate,
                QualificationGateStatus.PENDING,
                self.summary or "passing qualification observation has no evidence",
                (),
                dict(self.metadata or {}),
            )
        status = QualificationGateStatus.WARN if self.warning and self.passed else (QualificationGateStatus.PASS if self.passed else QualificationGateStatus.FAIL)
        return QualificationGateResult(self.gate, status, self.summary, self.evidence, dict(self.metadata or {}))


class EngineeringQualification:
    BASE_GATES = ("requirements", "build", "unit", "integration", "security")
    UI_GATES = ("responsive", "chromium", "runtime")

    def required_gates(self, spec: EngineeringSpec) -> tuple[str, ...]:
        gates = list(self.BASE_GATES)
        if spec.ui_required:
            gates.extend(self.UI_GATES)
            browser_values = {item.value for item in spec.browsers}
            if "webkit" in browser_values:
                gates.append("webkit")
            if "firefox" in browser_values:
                gates.append("firefox")
        if spec.visual_review_required:
            gates.append("visual")
        if spec.accessibility_required:
            gates.append("accessibility")
        metadata = dict(spec.metadata)
        if bool(metadata.get("performance_required", False)):
            gates.append("performance")
        if spec.ui_required and bool(metadata.get("localization_required", False)):
            gates.append("localization")
        if spec.ui_required and bool(metadata.get("three_d_required", False)):
            gates.append("three_d")
        if spec.ui_required and bool(metadata.get("physical_device_required", False)):
            gates.append("physical_device")
        if bool(metadata.get("preview_enabled", False)):
            gates.append("preview")
        if bool(metadata.get("regression_test_required", False)) or str(metadata.get("failure_fingerprint") or "").strip():
            gates.append("regression_test")
        return tuple(dict.fromkeys(gates))

    def report(
        self,
        *,
        spec: EngineeringSpec,
        candidate_revision: str,
        observations: Iterable[VerificationObservation],
        reviewer: str = "",
        review_decision: str = "pending",
        limitations: Iterable[str] = (),
    ) -> QualificationReport:
        supplied = {item.gate: item.to_gate() for item in observations}
        gates: list[QualificationGateResult] = []
        for gate in self.required_gates(spec):
            gates.append(supplied.pop(gate, QualificationGateResult(gate, QualificationGateStatus.PENDING, "required qualification evidence is missing")))
        gates.extend(supplied.values())
        if spec.review_required and review_decision not in {"approved", "rejected", "pending"}:
            raise ValueError("review_decision must be approved, rejected, or pending")
        if not spec.review_required and review_decision == "pending":
            review_decision = "approved"
        return QualificationReport(
            spec_id=spec.id,
            base_revision=spec.base_revision,
            candidate_revision=str(candidate_revision),
            gates=tuple(gates),
            reviewer=str(reviewer),
            review_decision=str(review_decision),
            limitations=tuple(str(item) for item in limitations),
        )
