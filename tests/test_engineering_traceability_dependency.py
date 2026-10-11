from __future__ import annotations

import json
from pathlib import Path

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.dependency_qualification import DependencyQualifier
from future_intelligence.engineering.qualification import EngineeringQualification, VerificationObservation
from future_intelligence.engineering.traceability import (
    EngineeringTraceability,
    RequirementTrace,
    UserFlowExpectation,
    UserFlowObservation,
)


def test_dependency_qualification_flags_direct_vcs_and_records_range_review(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text(
        "safe==1.2.3\nrange>=2,<3\ngit+https://example.test/repo.git\n",
        encoding="utf-8",
    )
    result = DependencyQualifier().qualify(tmp_path)
    assert not result.passed
    assert "requirements.txt" in result.files_checked
    reasons = [item.reason for item in result.findings]
    assert any("VCS" in reason for reason in reasons)
    assert any("version range" in reason for reason in reasons)


def test_package_lock_integrity_policy_flags_remote_package_without_hash(tmp_path: Path):
    payload = {
        "packages": {
            "node_modules/example": {"resolved": "https://registry.example.test/example.tgz"},
            "node_modules/safe": {"resolved": "https://registry.example.test/safe.tgz", "integrity": "sha512-example"},
        }
    }
    (tmp_path / "package-lock.json").write_text(json.dumps(payload), encoding="utf-8")
    result = DependencyQualifier().qualify(tmp_path)
    assert result.passed
    assert any(item.severity == "medium" and "integrity" in item.reason for item in result.findings)


def test_requirement_traceability_requires_evidence_and_pass_state():
    spec = EngineeringSpec(
        id="eng-trace",
        work_order_id="work-trace",
        attempt_id="attempt-trace",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="trace requirements",
        requirements=("save profile",),
        success_criteria=("cancel restores values",),
        allowed_paths=("app/",),
    )
    traces = EngineeringTraceability.requirements(
        spec,
        evidence={"save profile": ("test:profile-save",), "cancel restores values": ("test:profile-cancel",)},
        passed_requirements=("save profile", "cancel restores values"),
    )
    assert all(item.passed for item in traces)
    incomplete = EngineeringTraceability.requirements(
        spec,
        evidence={"save profile": ()},
        passed_requirements=("save profile",),
    )
    assert not all(item.passed for item in incomplete)


def test_user_flow_coverage_is_exact_and_evidence_bound():
    expected = (
        UserFlowExpectation("project create", ("open-projects", "new-project", "save", "project-visible")),
    )
    good = (
        UserFlowObservation("project create", ("open-projects", "new-project", "save", "project-visible"), ("browser:project-create",)),
    )
    bad = (
        UserFlowObservation("project create", ("open-projects", "save"), ("browser:partial",)),
    )
    assert EngineeringTraceability.user_flows(expected, good)["passed"] is True
    assert EngineeringTraceability.user_flows(expected, bad)["passed"] is False


def test_completion_matrix_cannot_be_qualified_when_requirement_trace_is_missing():
    spec = EngineeringSpec(
        id="eng-matrix",
        work_order_id="work-matrix",
        attempt_id="attempt-matrix",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="trace completion",
        requirements=("required behavior",),
        allowed_paths=("app/",),
    )
    qualification = EngineeringQualification()
    observations = tuple(VerificationObservation(gate, True, "ok", (f"evidence:{gate}",)) for gate in qualification.required_gates(spec))
    report = qualification.report(
        spec=spec,
        candidate_revision="b" * 40,
        observations=observations,
        reviewer="reviewer",
        review_decision="approved",
    )
    assert report.qualified
    matrix = EngineeringTraceability.completion_matrix(
        spec,
        report,
        (RequirementTrace("required behavior", (), False),),
    )
    assert matrix["qualified"] is False
