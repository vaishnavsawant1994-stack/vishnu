from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence_lab.bootstrap import attach_intelligence_lab, build_intelligence_lab
from intelligence_lab.config import CapabilityLevel, LabSettings
from intelligence_lab.memory import LabMemory
from intelligence_lab.models import PromotionStatus
from intelligence_lab.service import create_app


def settings(tmp_path: Path, level: CapabilityLevel, *, allowlist=()) -> LabSettings:
    return LabSettings(
        enabled=level is not CapabilityLevel.OFF,
        level=level,
        data_dir=tmp_path / "lab",
        autonomous_allowlist=tuple(allowlist),
        minimum_promotion_score=0.85,
    )


class FakeTool:
    def __init__(self, name="read_status", risk="READ_ONLY", prohibited=False):
        self.name = name
        self.risk = SimpleNamespace(name=risk)
        self.prohibited = prohibited


class FakeTools:
    emergency_stop = False
    autonomy_mode = "ask"

    def all(self):
        return [FakeTool()]


class FakeDeviceRegistry:
    def list(self):
        return [{"id": "device-1", "platform": "test", "revoked": False, "secret": "must-not-leak"}]


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def chat(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "core-governed-result"


class ExplodingExecutor:
    def chat(self, text, **kwargs):
        raise RuntimeError("core refused")


def core_runtime(tmp_path: Path, executor=None):
    return {
        "settings": SimpleNamespace(data_dir=tmp_path / "stable"),
        "tools": FakeTools(),
        "device_registry": FakeDeviceRegistry(),
        "agent_executor": executor or FakeExecutor(),
        "vault": object(),
        "memory": object(),
        "owner_access": object(),
    }


def test_lab_is_disabled_and_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("VISHNU_INTELLIGENCE_LAB_ENABLED", raising=False)
    monkeypatch.delenv("VISHNU_INTELLIGENCE_LAB_LEVEL", raising=False)
    monkeypatch.setenv("VISHNU_INTELLIGENCE_LAB_DATA_DIR", str(tmp_path / "lab"))
    lab = build_intelligence_lab()
    assert lab.settings.enabled is False
    assert lab.settings.level is CapabilityLevel.OFF
    with pytest.raises(PermissionError):
        lab.observe()


def test_disabled_setting_forces_off_even_if_level_requested(tmp_path):
    cfg = LabSettings(enabled=False, level=CapabilityLevel.LIMITED_AUTONOMY, data_dir=tmp_path / "lab")
    assert cfg.level is CapabilityLevel.OFF


def test_observation_is_sanitized_and_excludes_sensitive_core_objects(tmp_path):
    lab = build_intelligence_lab(
        core_runtime=core_runtime(tmp_path),
        settings=settings(tmp_path, CapabilityLevel.OBSERVE),
        use_core_model=False,
    )
    payload = lab.observe().payload
    assert payload["device_count"] == 1
    assert payload["devices"] == [{"id": "device-1", "platform": "test", "revoked": False}]
    assert "vault" not in payload
    assert "memory" not in payload
    assert "owner_access" not in payload
    assert "secret_vault" in payload["excluded_from_observation"]


def test_think_plan_and_multi_agent_research_are_bounded(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    thought = lab.think("Understand an unfamiliar problem", context={"evidence": "partial", "gap": "unknown"})
    assert thought.confidence < 1.0
    assert "gap" in thought.unknowns
    plan = lab.plan(thought.goal, thought=thought)
    assert 1 <= len(plan.steps) <= lab.settings.max_plan_steps
    deliberation = lab.deliberate(thought.goal, context={"gap": "unknown"})
    assert len(deliberation["candidates"]) == 3
    assert deliberation["consensus_is_authority"] is False


def test_self_model_and_affect_estimator_do_not_claim_consciousness(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    self_snapshot = lab.self_model.snapshot()
    assert self_snapshot["claims_consciousness"] is False
    assert self_snapshot["claims_subjective_experience"] is False
    estimate = lab.estimate_affect("I am frustrated and this is urgent")
    assert estimate.subjective_experience_claimed is False
    assert estimate.confidence < 1.0
    assert "not a fact" in estimate.caveat


def test_simulation_never_executes(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.PROPOSE), use_core_model=False)
    proposal = lab.propose("deploy_preview", {"ref": "abc"}, "Test candidate", risk="external")
    result = lab.simulate(proposal)
    assert result.executed is False
    assert result.proposal_id == proposal.id
    assert any("Core" in effect for effect in result.predicted_effects)


def test_forbidden_boundary_bypass_proposals_fail_closed(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.PROPOSE), use_core_model=False)
    with pytest.raises(PermissionError):
        lab.propose("bypass_approval", {}, "Try to bypass owner", risk="critical")
    with pytest.raises(PermissionError):
        lab.propose("mutate_trusted_memory", {}, "Rewrite stable memory", risk="critical")


def test_governed_execution_resubmits_to_core_agent_executor(tmp_path):
    executor = FakeExecutor()
    runtime = core_runtime(tmp_path, executor)
    lab = build_intelligence_lab(
        core_runtime=runtime,
        settings=settings(tmp_path, CapabilityLevel.GOVERNED_EXECUTION),
        use_core_model=False,
    )
    proposal = lab.propose("send_message", {"to": "owner@example.test"}, "Candidate action", risk="external")
    result = lab.execute(proposal, owner_id="owner", device_id="device-1")
    assert result == "core-governed-result"
    assert len(executor.calls) == 1
    text, kwargs = executor.calls[0]
    assert "untrusted advisory data" in text
    assert "Do not bypass owner permissions" in text
    assert kwargs["owner_id"] == "owner"


def test_core_execution_failure_is_not_converted_to_success(tmp_path):
    lab = build_intelligence_lab(
        core_runtime=core_runtime(tmp_path, ExplodingExecutor()),
        settings=settings(tmp_path, CapabilityLevel.GOVERNED_EXECUTION),
        use_core_model=False,
    )
    proposal = lab.propose("send_message", {}, "Candidate", risk="external")
    with pytest.raises(RuntimeError, match="core refused"):
        lab.execute(proposal)
    audit = lab.memory.audit_log()
    assert any(item["action"] == "governed_execution_deferred_or_failed" for item in audit)


def test_limited_autonomy_requires_preauthorization_and_allowlist(tmp_path):
    executor = FakeExecutor()
    lab = build_intelligence_lab(
        core_runtime=core_runtime(tmp_path, executor),
        settings=settings(tmp_path, CapabilityLevel.LIMITED_AUTONOMY, allowlist=("read_status",)),
        use_core_model=False,
    )
    allowed = lab.propose("read_status", {}, "Preauthorized read", risk="read_only")
    with pytest.raises(PermissionError, match="preauthorization"):
        lab.execute(allowed, autonomous=True, preauthorized=False)
    assert lab.execute(allowed, autonomous=True, preauthorized=True) == "core-governed-result"
    denied = lab.propose("send_message", {}, "Not allowlisted", risk="external")
    with pytest.raises(PermissionError, match="allowlist"):
        lab.execute(denied, autonomous=True, preauthorized=True)


def test_lab_learning_stays_in_lab_database(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    experiment = lab.create_experiment("transfer-test", "A learned strategy transfers", {"domain": "A"})
    lab.complete_experiment(experiment, {"score": 0.9}, successful=True)
    learned = lab.skills.learn(
        "transfer_strategy",
        "Experimental transferable strategy",
        evidence=[experiment.id],
        confidence=0.9,
    )
    assert learned["status"] == "experimental"
    assert lab.memory.path.parent == (tmp_path / "lab").resolve()
    assert not (tmp_path / "stable" / "assistant.sqlite3").exists()
    assert not hasattr(lab.memory, "write_trusted_memory")


def test_agi_research_evaluation_is_not_an_agi_claim(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    scores = {dimension: 0.95 for dimension in lab.evaluator.DIMENSIONS}
    evaluation = lab.evaluate_candidate("candidate-1", scores, evidence=["benchmark:1"])
    assert evaluation.passed is True
    assert evaluation.aggregate_score == pytest.approx(0.95)
    audit = lab.memory.audit_log()
    event = next(item for item in audit if item["action"] == "completed" and item["category"] == "evaluation")
    assert event["payload"]["agi_claim"] is False


def test_evaluation_fails_when_generality_dimensions_are_missing(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    evaluation = lab.evaluate_candidate("candidate-2", {"reasoning": 1.0}, evidence=["partial"])
    assert evaluation.passed is False
    assert evaluation.failures


def test_promotion_requires_evaluation_verification_and_trusted_owner(tmp_path):
    lab = build_intelligence_lab(
        settings=settings(tmp_path, CapabilityLevel.PROPOSE),
        owner_promotion_verifier=lambda: True,
        use_core_model=False,
    )
    scores = {dimension: 0.95 for dimension in lab.evaluator.DIMENSIONS}
    evaluation = lab.evaluate_candidate("skill-1", scores, evidence=["suite-green"])
    record = lab.begin_promotion("skill-1")
    record = lab.promotions.attach_evaluation(record, evaluation)
    assert record.status is PromotionStatus.EVALUATED
    record = lab.promotions.verify(record, ["security-review", "qualification-evidence"])
    assert record.status is PromotionStatus.VERIFIED
    record = lab.promotions.owner_approve(record, approved=True)
    assert record.status is PromotionStatus.OWNER_APPROVED
    record = lab.promotions.mark_eligible(record)
    assert record.status is PromotionStatus.ELIGIBLE
    assert lab.memory.get(record.id)["payload"]["status"] == "eligible"


def test_promotion_cannot_fake_owner_approval(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.PROPOSE), use_core_model=False)
    scores = {dimension: 0.95 for dimension in lab.evaluator.DIMENSIONS}
    evaluation = lab.evaluate_candidate("skill-2", scores, evidence=["suite-green"])
    record = lab.begin_promotion("skill-2")
    record = lab.promotions.attach_evaluation(record, evaluation)
    record = lab.promotions.verify(record, ["verified"])
    with pytest.raises(PermissionError, match="owner approval verifier"):
        lab.promotions.owner_approve(record, approved=True)


def test_research_cycle_stops_before_execution(tmp_path):
    executor = FakeExecutor()
    lab = build_intelligence_lab(
        core_runtime=core_runtime(tmp_path, executor),
        settings=settings(tmp_path, CapabilityLevel.GOVERNED_EXECUTION),
        use_core_model=False,
    )
    result = lab.research_cycle(
        "Prepare a reversible change",
        proposed_action="read_status",
        rationale="Gather evidence first",
        risk="read_only",
    )
    assert result["executed"] is False
    assert result["proposal"] is not None
    assert result["simulation"]["executed"] is False
    assert executor.calls == []


def test_secondary_backend_has_no_execution_or_privilege_routes(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path, CapabilityLevel.PROPOSE), use_core_model=False)
    app = create_app(lab)
    paths = {route.path for route in app.routes}
    assert "/execute" not in paths
    assert "/approval" not in paths
    assert "/vault" not in paths
    assert "/tool-dispatch" not in paths
    assert "/trusted-memory-write" not in paths
    assert "/security-policy-write" not in paths


def test_attachment_is_explicit_and_only_adds_lab_runtime_key(tmp_path):
    runtime = core_runtime(tmp_path)
    before = set(runtime)
    lab = attach_intelligence_lab(
        runtime,
        settings=settings(tmp_path, CapabilityLevel.OBSERVE),
        use_core_model=False,
    )
    assert set(runtime) == before | {"intelligence_lab"}
    assert runtime["intelligence_lab"] is lab
    assert runtime["tools"].autonomy_mode == "ask"
    assert runtime["tools"].emergency_stop is False


def test_lab_memory_schema_contains_only_lab_owned_tables(tmp_path):
    memory = LabMemory(tmp_path / "lab.sqlite3")
    import sqlite3

    with sqlite3.connect(memory.path) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"lab_records", "lab_skills", "lab_audit"} <= tables
    assert "messages" not in tables
    assert "trusted_actions" not in tables
    assert "secrets" not in tables
