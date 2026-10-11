from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.performance import PerformanceBudget, evaluate_performance
from future_intelligence.engineering.policy import evaluate_engineering_path
from future_intelligence.engineering.qualification import EngineeringQualification, VerificationObservation
from future_intelligence.engineering.repository_intelligence import RepositoryIntelligenceBuilder
from future_intelligence.engineering.visual_baselines import ApprovedVisualBaselineStore, VisualBaselineError, VisualBaselineKey


def make_spec(**kwargs):
    values = dict(
        id="eng", work_order_id="work", attempt_id="attempt", repository="owner/repo",
        base_revision="a" * 40, objective="qualify", allowed_paths=(".",),
        metadata={"performance_required": True},
    )
    values.update(kwargs)
    return EngineeringSpec(**values)


def write_baseline(root: Path, *, tamper: bool = False):
    root.mkdir()
    image = root / "home.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = {
        "version": 1,
        "entries": [{
            "key": {"screen": "home", "browser": "chromium", "device": "iphone-standard", "state": "normal", "theme": "dark", "reference_version": "v1"},
            "relative_path": "home.png", "sha256": ("0" * 64 if tamper else digest),
            "approved_by": "owner", "approved_at": "2026-10-11T00:00:00Z",
        }],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return image


def test_allowed_directory_scope_includes_scope_root():
    assert evaluate_engineering_path("app", allowed_paths=("app/",)).allowed
    assert evaluate_engineering_path("app/main.py", allowed_paths=("app/",)).allowed


def test_root_repository_graph_scope_includes_files(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def main(): return 1\n", encoding="utf-8")
    graph = RepositoryIntelligenceBuilder().build(tmp_path, revision="abc", include_paths=(".",))
    assert any(node.path == "app/main.py" for node in graph.nodes)


def test_visual_baseline_requires_explicit_approved_manifest(tmp_path: Path):
    store = ApprovedVisualBaselineStore(tmp_path)
    key = VisualBaselineKey("home", "chromium", "iphone-standard", theme="dark")
    with pytest.raises(VisualBaselineError):
        store.resolve(key)


def test_visual_baseline_verifies_checksum_and_compares(tmp_path: Path):
    baseline = write_baseline(tmp_path)
    store = ApprovedVisualBaselineStore(tmp_path)
    key = VisualBaselineKey("home", "chromium", "iphone-standard", theme="dark")
    assert store.resolve(key) == baseline
    result = store.compare(key, baseline)
    assert not result.changed


def test_visual_baseline_checksum_mismatch_fails_closed(tmp_path: Path):
    write_baseline(tmp_path, tamper=True)
    store = ApprovedVisualBaselineStore(tmp_path)
    key = VisualBaselineKey("home", "chromium", "iphone-standard", theme="dark")
    with pytest.raises(VisualBaselineError):
        store.resolve(key)


def test_performance_budget_and_required_gate_are_blocking():
    performance = evaluate_performance({"first_usable_ms": 900}, PerformanceBudget(max_first_usable_ms=800))
    assert not performance.passed
    spec = make_spec()
    qualification = EngineeringQualification()
    required = qualification.required_gates(spec)
    assert "performance" in required
    observations = tuple(VerificationObservation(gate, True, "ok") for gate in required if gate != "performance")
    report = qualification.report(spec=spec, candidate_revision="b" * 40, observations=observations, reviewer="reviewer", review_decision="approved")
    assert not report.qualified
    assert next(gate for gate in report.gates if gate.gate == "performance").blocking
