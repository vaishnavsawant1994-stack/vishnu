from __future__ import annotations

from pathlib import Path

from future_intelligence.engineering.contracts import EngineeringBudget, EngineeringSpec, QualificationGateStatus, VisualDefect
from future_intelligence.engineering.qualification import VerificationObservation
from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult, ProductionRegression
from future_intelligence.engineering.repository_intelligence import RepositoryIntelligenceBuilder
from future_intelligence.engineering.service import EngineeringCandidateCoordinator
from future_intelligence.engineering.source_correlation import VisualSourceCorrelator
from future_intelligence.work_orchestration.repository import RepositoryWorkspaceSession


class Provider:
    repository = "owner/repo"

    def __init__(self, root: Path): self.root = root
    def resolve_revision(self, revision): return "a" * 40
    def read_text_at(self, revision, path): return (self.root / path).read_text(encoding="utf-8")
    def changed_paths(self, session): return ("app/ui.css",)


def spec():
    return EngineeringSpec(
        id="eng-x", work_order_id="work-x", attempt_id="attempt-x", repository="owner/repo",
        base_revision="a" * 40, objective="fix UI", allowed_paths=("app/",),
        ui_required=False, budget=EngineeringBudget(max_files=4, max_file_bytes=20_000, max_total_bytes=40_000),
    )


def session(root: Path):
    return RepositoryWorkspaceSession("owner/repo", "work-x", "attempt-x", "a" * 40, "work/work-x", root)


def test_candidate_coordinator_reports_no_release_authority(tmp_path: Path):
    workspace = tmp_path / "workspace"; (workspace / "app").mkdir(parents=True)
    (workspace / "app" / "ui.css").write_text(".composer { bottom: 0; }\n", encoding="utf-8")
    coordinator = EngineeringCandidateCoordinator(
        repository_provider=Provider(workspace), session=session(workspace), spec=spec(), evidence_root=tmp_path / "evidence",
    )
    context = coordinator.inspect()
    assert context.changed_paths == ("app/ui.css",)
    status = coordinator.status()
    assert status["push_authority"] is False
    assert status["merge_authority"] is False
    assert status["deploy_authority"] is False
    assert status["activation_authority"] is False
    required = coordinator.qualification.required_gates(spec())
    observations = tuple(VerificationObservation(gate, True, "ok") for gate in required)
    report = coordinator.finalize(candidate_revision="b" * 40, observations=observations, reviewer="independent", review_decision="approved")
    assert report.qualified
    assert coordinator.evidence.read()


def test_pending_gate_is_blocking_even_when_review_approved():
    from future_intelligence.engineering.contracts import QualificationGateResult, QualificationReport
    report = QualificationReport(
        "eng", "a" * 40, "b" * 40,
        (QualificationGateResult("security", QualificationGateStatus.PENDING, "missing"),),
        reviewer="reviewer", review_decision="approved",
    )
    assert not report.qualified


def test_visual_source_correlation_prefers_matching_ui_surface(tmp_path: Path):
    (tmp_path / "pwa").mkdir(); (tmp_path / "server").mkdir()
    (tmp_path / "pwa" / "projects.css").write_text(".projects-composer { bottom: 0; }\n", encoding="utf-8")
    (tmp_path / "pwa" / "projects.js").write_text("const route = '/projects';\n", encoding="utf-8")
    (tmp_path / "server" / "projects.py").write_text("def projects(): return {}\n", encoding="utf-8")
    graph = RepositoryIntelligenceBuilder().build(tmp_path, revision="abc")
    defect = VisualDefect(
        screen="projects", route="/projects", viewport="390x844", browser="webkit", state="normal",
        severity="review", expected="composer visible", actual="composer layout is too low",
        suspected_element="#projects-composer", suspected_component="projects", confidence=0.8,
    )
    candidates = VisualSourceCorrelator().correlate(graph, defect)
    assert candidates
    assert candidates[0].path.startswith("pwa/")


def test_environment_qualification_requires_health_and_all_checks():
    good = EnvironmentQualificationResult("preview", "https://example.test", True, {"health": True, "routes": True})
    bad = EnvironmentQualificationResult("production", "https://example.test", True, {"health": True, "auth": False})
    assert good.passed
    assert not bad.passed


def test_production_regression_only_proposes_canonical_work():
    proposal = ProductionRegression("a" * 40, "https://example.test", "chat route returns 500").to_work_proposal()
    assert proposal["created_from"] == "production_regression_observation"
    assert proposal["metadata"]["automatic_mutation_authority"] is False
    assert proposal["metadata"]["automatic_deploy_authority"] is False
