from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from future_intelligence.engineering.accessibility import AccessibilityResult
from future_intelligence.engineering.contracts import (
    BrowserEngine,
    EngineeringBudget,
    EngineeringSpec,
    QualificationGateStatus,
)
from future_intelligence.engineering.impact import EngineeringImpactAnalyzer
from future_intelligence.engineering.policy import evaluate_engineering_path
from future_intelligence.engineering.qualification import EngineeringQualification, VerificationObservation
from future_intelligence.engineering.repair_loop import BoundedEngineeringRepairLoop
from future_intelligence.engineering.repository_editor import GovernedRepositoryEditor
from future_intelligence.engineering.repository_intelligence import RepositoryIntelligenceBuilder
from future_intelligence.engineering.ui_contracts import CANONICAL_DEVICES, breakpoint_neighbours
from future_intelligence.engineering.visual_qa import VisualRegressionAnalyzer
from future_intelligence.work_orchestration.repository import RepositoryWorkspaceSession


class FakeRepositoryProvider:
    repository = "owner/repo"

    def __init__(self, base_files=None):
        self.base_files = dict(base_files or {})

    def resolve_revision(self, revision: str) -> str:
        return "a" * 40 if revision in {"main", "a" * 40} else revision

    def read_text_at(self, revision: str, path: str) -> str:
        if path not in self.base_files:
            raise RuntimeError("missing")
        return self.base_files[path]


def make_spec(**overrides):
    values = dict(
        id="eng-1", work_order_id="work-1", attempt_id="attempt-1",
        repository="owner/repo", base_revision="a" * 40, objective="implement safely",
        allowed_paths=("app/", "tests/"), required_tests=("tests/test_app.py",),
        browsers=(BrowserEngine.CHROMIUM,), budget=EngineeringBudget(max_files=4, max_file_bytes=10_000, max_total_bytes=30_000),
    )
    values.update(overrides)
    return EngineeringSpec(**values)


def make_session(root: Path):
    return RepositoryWorkspaceSession("owner/repo", "work-1", "attempt-1", "a" * 40, "work/work-1", root)


def test_engineering_contract_round_trip():
    spec = make_spec(ui_required=True, accessibility_required=True, visual_review_required=True)
    restored = EngineeringSpec.from_dict(spec.to_dict())
    assert restored == spec
    assert CANONICAL_DEVICES[0].width == 320
    widths = breakpoint_neighbours((768, 1024))
    assert widths == (767, 768, 769, 1023, 1024, 1025)


def test_engineering_path_policy_fails_closed_for_secrets_and_authority():
    assert not evaluate_engineering_path(".env", allowed_paths=(".",)).allowed
    assert not evaluate_engineering_path("config/private-key.pem", allowed_paths=("config/",)).allowed
    authority = evaluate_engineering_path("security/policy.py", allowed_paths=("security/",))
    assert not authority.allowed and authority.authority_sensitive
    explicitly_scoped = evaluate_engineering_path("security/policy.py", allowed_paths=("security/",), allow_authority_paths=True)
    assert explicitly_scoped.allowed and explicitly_scoped.authority_sensitive
    assert not evaluate_engineering_path("other/file.py", allowed_paths=("app/",)).allowed


def test_repository_editor_is_workspace_bound_atomic_and_preconditioned(tmp_path: Path):
    root = tmp_path / "workspace"; root.mkdir()
    (root / "app").mkdir(); (root / "tests").mkdir()
    (root / "app" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = FakeRepositoryProvider({"app/main.py": "VALUE = 1\n"})
    editor = GovernedRepositoryEditor(provider=provider, session=make_session(root), spec=make_spec())
    text, digest = editor.read_text("app/main.py")
    assert text == "VALUE = 1\n"
    evidence = editor.replace_exact("app/main.py", "VALUE = 1", "VALUE = 2", expected_sha256=digest)
    assert evidence.before_sha256 == digest
    assert (root / "app" / "main.py").read_text() == "VALUE = 2\n"
    with pytest.raises(RuntimeError):
        editor.replace_text("app/main.py", "VALUE = 3\n", expected_sha256=digest)
    created = editor.create_text("tests/test_app.py", "def test_value():\n    assert 2 == 2\n")
    assert created.operation == "write"
    assert set(editor.mutated_paths) == {"app/main.py", "tests/test_app.py"}
    assert "-VALUE = 1" in editor.diff("app/main.py") and "+VALUE = 2" in editor.diff("app/main.py")
    with pytest.raises(PermissionError):
        editor.create_text("security/bypass.py", "bad = True\n")
    with pytest.raises(PermissionError):
        editor.create_text("../escape.py", "bad = True\n")


def test_repository_editor_restore_and_search(tmp_path: Path):
    root = tmp_path / "workspace"; root.mkdir(); (root / "app").mkdir()
    (root / "app" / "main.py").write_text("needle = 'changed'\n", encoding="utf-8")
    provider = FakeRepositoryProvider({"app/main.py": "needle = 'base'\n"})
    editor = GovernedRepositoryEditor(provider=provider, session=make_session(root), spec=make_spec())
    results = editor.search_text("changed")
    assert results and results[0]["path"] == "app/main.py"
    editor.restore_from_base("app/main.py")
    assert (root / "app" / "main.py").read_text() == "needle = 'base'\n"


def test_repository_intelligence_and_impact_are_reconstructable(tmp_path: Path):
    (tmp_path / "app").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "core.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "app" / "consumer.py").write_text("from app.core import value\n\ndef read():\n    return value()\n", encoding="utf-8")
    (tmp_path / "tests" / "test_core.py").write_text("from app.core import value\n\ndef test_value(): assert value() == 1\n", encoding="utf-8")
    graph = RepositoryIntelligenceBuilder().build(tmp_path, revision="deadbeef")
    assert graph.revision == "deadbeef"
    assert any(node.kind == "function" and node.name == "value" for node in graph.nodes)
    report = EngineeringImpactAnalyzer().analyze(graph, ("app/core.py",))
    assert "tests/test_core.py" in report.relevant_tests


def test_visual_regression_diff_is_deterministic(tmp_path: Path):
    baseline = tmp_path / "base.png"; candidate = tmp_path / "candidate.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(baseline)
    Image.new("RGB", (20, 20), (0, 0, 0)).save(candidate)
    analyzer = VisualRegressionAnalyzer()
    same = analyzer.compare(baseline, candidate)
    assert not same.changed and same.mismatch_ratio == 0
    image = Image.new("RGB", (20, 20), (0, 0, 0)); image.putpixel((5, 5), (255, 255, 255)); image.save(candidate)
    changed = analyzer.compare(baseline, candidate)
    assert changed.changed and 0 < changed.mismatch_ratio < 1


def test_accessibility_serious_violation_blocks():
    result = AccessibilityResult.from_axe({"violations": [{"id": "label", "impact": "serious", "description": "missing label", "nodes": [{"target": ["#field"]}]}], "passes": [], "incomplete": []})
    assert not result.passed
    assert result.violations[0].blocking


def test_qualification_stays_unqualified_until_independent_review_and_all_gates():
    spec = make_spec(ui_required=False)
    qualification = EngineeringQualification()
    observations = tuple(VerificationObservation(name, True, "ok") for name in qualification.required_gates(spec))
    pending = qualification.report(spec=spec, candidate_revision="b" * 40, observations=observations)
    assert not pending.qualified
    approved = qualification.report(spec=spec, candidate_revision="b" * 40, observations=observations, reviewer="reviewer", review_decision="approved")
    assert approved.qualified
    assert all(gate.status is QualificationGateStatus.PASS for gate in approved.gates)


class Detector:
    def __init__(self): self.calls = 0
    def detect(self, *, spec):
        self.calls += 1
        return ("defect",) if self.calls < 3 else ()


class Repairer:
    def repair(self, *, spec, defects, cycle): return {"cycle": cycle}


class Verifier:
    def verify(self, *, spec, cycle): return True


def test_repair_loop_is_bounded_and_stops_when_clean():
    outcome = BoundedEngineeringRepairLoop(detector=Detector(), repairer=Repairer(), verifier=Verifier()).run(make_spec())
    assert outcome.status == "repaired"
    assert len(outcome.cycles) == 2
    assert not outcome.needs_attention


def test_repair_loop_marks_attention_at_budget():
    class NeverClean:
        def detect(self, *, spec): return ("defect",)
    spec = make_spec(budget=EngineeringBudget(max_files=4, max_file_bytes=10_000, max_total_bytes=30_000, max_repair_cycles=1))
    outcome = BoundedEngineeringRepairLoop(detector=NeverClean(), repairer=Repairer(), verifier=Verifier()).run(spec)
    assert outcome.status == "needs_attention"
    assert len(outcome.cycles) == 1
