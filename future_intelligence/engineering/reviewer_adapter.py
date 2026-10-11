from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .contracts import EngineeringSpec, QualificationReport, SecurityClass
from .model_json import governed_engineering_json


@dataclass(frozen=True)
class EngineeringReviewDecision:
    decision: str
    reviewer: str
    summary: str
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"approved", "rejected"}:
            raise ValueError("engineering review must explicitly approve or reject")
        if not self.reviewer.strip():
            raise ValueError("reviewer identity is required")


class EngineeringReviewer(Protocol):
    def review(self, *, spec: EngineeringSpec, report: QualificationReport, diff: str, evidence: Mapping[str, Any]) -> EngineeringReviewDecision: ...


class ModelEngineeringReviewer:
    """Independent model review; has no mutation, owner approval, merge or deploy authority."""

    def __init__(self, models, *, reviewer_name: str = "independent-engineering-reviewer") -> None:
        self.models = models
        self.reviewer_name = reviewer_name

    def review(self, *, spec: EngineeringSpec, report: QualificationReport, diff: str, evidence: Mapping[str, Any]) -> EngineeringReviewDecision:
        system = (
            "You are an independent Vishnu software-engineering reviewer. Look actively for incompleteness, regression risk, "
            "security boundary violations, missing tests and unsupported completion claims. You cannot edit code, approve owner "
            "actions, merge, deploy or activate anything. Return JSON only with decision, summary and findings. decision must be "
            "approved or rejected; reject when required evidence is pending/failing or the diff exceeds the EngineeringSpec."
        )
        sensitivity = (
            "sensitive"
            if spec.security_class in {SecurityClass.SENSITIVE, SecurityClass.AUTHORITY}
            else "internal"
        )
        payload = governed_engineering_json(
            self.models,
            spec=spec,
            prompt=f"EngineeringSpec={spec.to_dict()}\nQualification={report.to_dict()}\nDiff={diff[:120000]}\nEvidence={dict(evidence)}",
            system=system,
            role=self.reviewer_name,
            sensitivity=sensitivity,
        )
        decision = str(payload.get("decision") or "rejected").lower()
        findings = payload.get("findings") or ()
        if not isinstance(findings, (list, tuple)):
            findings = (str(findings),)
        return EngineeringReviewDecision(
            decision=decision,
            reviewer=self.reviewer_name,
            summary=str(payload.get("summary") or "")[:4000],
            findings=tuple(str(item)[:2000] for item in findings),
        )
