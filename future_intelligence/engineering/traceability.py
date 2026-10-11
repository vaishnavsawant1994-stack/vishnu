from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import EngineeringSpec, QualificationReport


@dataclass(frozen=True)
class RequirementTrace:
    requirement: str
    evidence_refs: tuple[str, ...] = ()
    passed: bool = False


@dataclass(frozen=True)
class UserFlowExpectation:
    name: str
    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.steps:
            raise ValueError("user flow name and steps are required")
        if any(not str(step).strip() for step in self.steps):
            raise ValueError("user flow steps must be non-empty")


@dataclass(frozen=True)
class UserFlowObservation:
    name: str
    observed_steps: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()


class EngineeringTraceability:
    """Evidence-first requirement and user-flow coverage without subjective scoring."""

    @staticmethod
    def requirements(
        spec: EngineeringSpec,
        *,
        evidence: Mapping[str, Iterable[str]],
        passed_requirements: Iterable[str] = (),
    ) -> tuple[RequirementTrace, ...]:
        passed = {str(item) for item in passed_requirements}
        result = []
        for requirement in (*spec.requirements, *spec.success_criteria):
            refs = tuple(dict.fromkeys(str(item) for item in evidence.get(str(requirement), ()) if str(item)))
            result.append(RequirementTrace(str(requirement), refs, str(requirement) in passed and bool(refs)))
        return tuple(result)

    @staticmethod
    def user_flows(
        expectations: Iterable[UserFlowExpectation],
        observations: Iterable[UserFlowObservation],
    ) -> dict[str, object]:
        observed = {item.name: item for item in observations}
        rows = []
        for expected in expectations:
            actual = observed.get(expected.name)
            passed = bool(actual and actual.observed_steps == expected.steps and actual.evidence_refs)
            rows.append({
                "name": expected.name,
                "expected_steps": list(expected.steps),
                "observed_steps": list(actual.observed_steps) if actual else [],
                "evidence": list(actual.evidence_refs) if actual else [],
                "passed": passed,
            })
        return {"passed": bool(rows) and all(row["passed"] for row in rows), "flows": rows}

    @staticmethod
    def completion_matrix(
        spec: EngineeringSpec,
        report: QualificationReport,
        traces: Iterable[RequirementTrace],
    ) -> dict[str, object]:
        trace_rows = tuple(traces)
        gate_rows = {gate.gate: gate.status.value for gate in report.gates}
        requirements_passed = bool(trace_rows) and all(item.passed for item in trace_rows)
        return {
            "spec_id": spec.id,
            "candidate_revision": report.candidate_revision,
            "requirements_passed": requirements_passed,
            "requirements": [
                {"requirement": item.requirement, "passed": item.passed, "evidence": list(item.evidence_refs)}
                for item in trace_rows
            ],
            "gates": gate_rows,
            "review_decision": report.review_decision,
            "qualified": bool(report.qualified and requirements_passed),
        }
