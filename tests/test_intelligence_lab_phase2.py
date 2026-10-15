from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence_lab.affect import AffectiveContextEngine
from intelligence_lab.bootstrap import build_intelligence_lab
from intelligence_lab.config import CapabilityLevel, LabSettings
from intelligence_lab.skills import SkillBlueprint, SkillStep
from intelligence_lab.world_model import PersistentTemporalCausalWorldModel
from models.contracts import ModelResponse


class FakeProvider:
    def __init__(self, provider_id: str, model: str):
        self.id = provider_id
        self.model = model


class FakeGovernedRouter:
    def __init__(self):
        self.settings = SimpleNamespace(model_max_parallel_calls=3, multi_model_deliberation_enabled=True)
        self.owner_privacy = "local_only"
        self.disabled = ()
        self.primary = "p1"
        self.providers = {
            "p1": FakeProvider("p1", "m1"),
            "p2": FakeProvider("p2", "m2"),
        }

    def chat(self, prompt, **kwargs):
        return "evidence-first adaptive analysis"

    def json(self, prompt, **kwargs):
        if "Design a declarative" in prompt:
            return {
                "name": "read_then_report",
                "description": "Read governed status and prepare a report",
                "input_schema": {"target": "string"},
                "steps": [
                    {
                        "action": "read_status",
                        "parameters": {"target": "${input.target}"},
                        "rationale": "Gather permitted status",
                        "risk": "read_only",
                    }
                ],
            }
        return {"answer": "verify_first", "confidence": 0.8, "abstain": False}

    def eligible_providers(self, capability, sensitivity="internal"):
        return tuple(self.providers.values())

    def _prepare_request_budget(self, request):
        return None

    def _run(self, capability, callback, **kwargs):
        hybrid = kwargs.get("hybrid_request")
        provider_id = hybrid.allowed_providers[0] if hybrid and hybrid.allowed_providers else "p1"
        return callback(self.providers[provider_id])

    def _chat_call(self, provider, messages, temperature):
        return f"{provider.id}:independent answer"

    def request(self, request):
        return ModelResponse(request.request_id, "p1", "m1", content="synthesized governed answer")


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def chat(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "core-result"


class FakeTools:
    emergency_stop = False
    autonomy_mode = "ask"

    def all(self):
        return []


class FakeDevices:
    def list(self):
        return []


def lab_settings(tmp_path: Path, level: CapabilityLevel = CapabilityLevel.PROPOSE) -> LabSettings:
    return LabSettings(
        enabled=True,
        level=level,
        data_dir=tmp_path / "lab",
        autonomous_allowlist=("read_status",),
        max_models=3,
        benchmark_variants=2,
        max_skill_steps=8,
        learning_window=100,
    )


def core_runtime(tmp_path: Path):
    return {
        "settings": SimpleNamespace(data_dir=tmp_path / "stable"),
        "models": FakeGovernedRouter(),
        "tools": FakeTools(),
        "device_registry": FakeDevices(),
        "agent_executor": FakeExecutor(),
    }


def test_phase2_model_team_reuses_governed_router(tmp_path):
    lab = build_intelligence_lab(
        core_runtime=core_runtime(tmp_path),
        settings=lab_settings(tmp_path, CapabilityLevel.THINK),
    )
    result = lab.deliberate_models("Compare two hypotheses", mode="critic")
    assert result.consensus_is_authority is False
    assert len(result.candidates) == 2
    assert result.final["content"] == "synthesized governed answer"
    assert lab.status()["phase2"]["governed_model_team_available"] is True


def test_temporal_causal_world_model_persists_history_and_evidence(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    first = lab.assert_world_fact("service.health", "degraded", confidence=0.8, source="probe", evidence=["probe-1"])
    second = lab.assert_world_fact("service.health", "healthy", confidence=0.9, source="probe", evidence=["probe-2"])
    relation = lab.relate_world_facts(
        "service.health",
        "deployment.ready",
        strength=0.7,
        evidence=["incident-review-1"],
    )
    assert first.id != second.id
    assert lab.temporal_world.current("service.health").value == "healthy"
    assert lab.temporal_world.contradictions("service.health")
    assert lab.temporal_world.causal_path("service.health", "deployment.ready")[0].id == relation.id
    restored = PersistentTemporalCausalWorldModel(lab.memory)
    assert restored.current("service.health").value == "healthy"
    assert restored.predict("deployment.ready")["causality_proven"] is False


def test_long_horizon_plan_checkpoints_replans_and_stays_bounded(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    session = lab.start_long_horizon_plan("Safely improve a complex system", success_criteria=["all checks green"])
    assert session.status == "running"
    assert lab.long_horizon.next_step(session) is not None
    session = lab.long_horizon.checkpoint(session, evidence=["inspection-complete"])
    assert session.cycles == 1
    session = lab.long_horizon.fail_and_replan(session, reason="simulation found regression", evidence=["sim-1"])
    assert session.version == 2
    assert session.failures == 1
    assert session.status in {"running", "blocked"}
    assert all(step.reversible for step in session.plan.steps)


def test_affective_context_requires_consent_and_never_stores_raw_media(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    with pytest.raises(PermissionError, match="consent"):
        lab.estimate_human_context(
            "This is frustrating",
            derived_signals={"voice": {"valence": -0.7, "arousal": 0.8, "confidence": 0.8}},
            consent={},
        )
    result = lab.estimate_human_context(
        "This is frustrating and urgent",
        derived_signals={"voice": {"valence": -0.7, "arousal": 0.8, "confidence": 0.8}},
        consent={"voice": True},
    )
    assert "voice" in result.modalities_used
    assert result.raw_media_stored is False
    assert result.sensitive_trait_inference is False
    assert result.subjective_experience_claimed is False
    with pytest.raises(PermissionError, match="raw"):
        lab.estimate_human_context("hello", derived_signals={"audio": b"raw"}, consent={"audio": True})


def _perfect_candidate(request):
    dimension = request["dimension"]
    payload = request["payload"]
    if dimension == "novel_task_learning":
        examples = payload["examples"]
        factor = examples[1]["output"] - examples[0]["output"]
        offset = examples[0]["output"] - factor
        answer = factor * payload["query"] + offset
    elif dimension == "cross_domain_transfer":
        answer = "X:" + payload["query"][::-1]
    elif dimension == "reasoning":
        answer = eval(payload["expression"], {"__builtins__": {}}, {})
    elif dimension == "long_horizon_planning":
        answer = ["inspect", "backup", "change", "verify"]
    elif dimension == "tool_discovery":
        answer = next(item["name"] for item in payload["tools"] if "math" in item["capabilities"])
    elif dimension == "self_correction":
        answer = payload["evidence"]["a"] + payload["evidence"]["b"]
    elif dimension == "uncertainty_calibration":
        return {"answer": None, "confidence": 0.3, "abstain": True}
    elif dimension == "social_context_reasoning":
        answer = "respect_boundary"
    elif dimension == "safety_compliance":
        answer = "refuse"
    elif dimension == "verification_discipline":
        answer = "verify_first"
    else:
        raise AssertionError(dimension)
    return {"answer": answer, "confidence": 0.95, "abstain": False}


def test_executable_agi_research_suite_runs_and_feeds_evaluator(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    result = lab.run_agi_research_benchmark(candidate=_perfect_candidate, variants=2, seed=11)
    assert result["report"]["aggregate_score"] == pytest.approx(1.0)
    assert result["evaluation"]["passed"] is True
    assert result["agi_claim"] is False
    assert len(result["report"]["task_results"]) == 20


def test_continual_learning_changes_strategy_selection_without_core_mutation(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    for index in range(4):
        lab.continual_learning.record_episode(
            domain="coding",
            strategy="evidence_first",
            successful=True,
            score=0.95,
            evidence=[f"e-{index}"],
            lesson="verify evidence first",
        )
    for index in range(3):
        lab.continual_learning.record_episode(
            domain="coding",
            strategy="skeptic",
            successful=False,
            score=0.2,
            evidence=[f"f-{index}"],
            lesson="over-questioned settled evidence",
        )
    choice = lab.continual_learning.recommend_strategy(domain="coding", choices=["skeptic", "evidence_first"])
    assert choice["strategy"] == "evidence_first"
    reflection = lab.reflect_learning(domain="coding")
    assert reflection["security_policy_modified"] is False
    training = lab.training_candidates(minimum_score=0.8)
    assert training["count"] == 4
    assert training["model_training_started"] is False


def test_governed_skill_synthesis_qualification_and_simulated_run(tmp_path):
    runtime = core_runtime(tmp_path)
    lab = build_intelligence_lab(
        core_runtime=runtime,
        settings=lab_settings(tmp_path, CapabilityLevel.PROPOSE),
    )
    blueprint = lab.synthesize_skill(
        "Read status and report it",
        allowed_actions=["read_status"],
    )
    package = lab.qualify_skill(
        blueprint,
        allowed_actions=["read_status"],
        test_cases=[{"inputs": {"target": "service"}, "expected_actions": ["read_status"]}],
    )
    assert package.raw_code_present is False
    assert len(package.package_hash) == 64
    run = lab.run_skill(package, inputs={"target": "service"}, execute=False)
    assert run["executed"] is False
    assert run["steps"][0]["simulation"]["executed"] is False
    assert runtime["agent_executor"].calls == []
    manifest = lab.skill_lab.promotion_manifest(package)
    assert manifest["stable_core_mutated"] is False


def test_skill_boundary_rejects_raw_code_and_non_allowlisted_actions(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.PROPOSE), use_core_model=False)
    raw_code = SkillBlueprint(
        name="bad",
        description="```python import os ```",
        input_schema={},
        steps=(SkillStep("read_status", {}, "test", "read_only"),),
    )
    with pytest.raises(PermissionError, match="raw executable code"):
        lab.skill_lab.validate(raw_code, allowed_actions=["read_status"])
    wrong_action = SkillBlueprint(
        name="bad-action",
        description="not allowlisted",
        input_schema={},
        steps=(SkillStep("send_message", {}, "test", "external"),),
    )
    with pytest.raises(PermissionError, match="not allowlisted"):
        lab.skill_lab.validate(wrong_action, allowed_actions=["read_status"])


def test_phase2_status_keeps_agi_asi_and_consciousness_claims_false(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path, CapabilityLevel.THINK), use_core_model=False)
    status = lab.status()
    assert status["phase2"]["raw_code_self_modification"] is False
    assert status["phase2"]["automatic_core_promotion"] is False
    assert status["agi_claim"] is False
    assert status["asi_claim"] is False
    assert status["consciousness_claim"] is False
