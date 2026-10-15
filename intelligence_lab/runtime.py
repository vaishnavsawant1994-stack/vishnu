from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from .affect import AffectiveContextEngine
from .benchmarks import AGIBenchmarkHarness
from .bridge import VishnuCoreBridge
from .cognition import (
    AdvancedReasoner,
    EmotionalUnderstanding,
    HierarchicalPlanner,
    LearningEngine,
    MultiAgentResearch,
    SelfModel,
    SkillLearner,
    WorldModel,
)
from .config import CapabilityLevel, LabSettings
from .evaluation import AGIResearchEvaluator, ExperimentManager, PromotionGate
from .learning import ContinualLearningEngine
from .memory import LabMemory
from .model_team import GovernedModelTeam
from .models import ActionProposal, EvaluationResult, Experiment, Plan, PromotionRecord, Thought
from .planning import AdaptiveLongHorizonPlanner, AdaptivePlanSession, PlanningBudget
from .safety import SimulationEngine
from .skills import GovernedSkillLab, SkillBlueprint, SkillPackage
from .world_model import PersistentTemporalCausalWorldModel


class IntelligenceLabRuntime:
    """Top-level experimental cognition runtime.

    The Lab is a separate research workspace. No method silently promotes itself
    to a higher capability level, grants Core authority, or mutates stable
    security/memory. Phase-2 components extend reasoning depth while preserving
    the original Core/Lab boundary.
    """

    def __init__(
        self,
        settings: LabSettings,
        memory: LabMemory,
        bridge: VishnuCoreBridge,
        *,
        model_callback: Callable[[str], str] | None = None,
        model_json_callback: Callable[[str], Mapping[str, Any]] | None = None,
        core_models: Any | None = None,
        owner_promotion_verifier=None,
    ):
        self.settings = settings
        self.memory = memory
        self.bridge = bridge
        self.model_callback = model_callback
        self.model_json_callback = model_json_callback
        self.world = WorldModel(memory)
        self.temporal_world = PersistentTemporalCausalWorldModel(
            memory,
            history_limit=settings.world_history_limit,
        )
        self.self_model = SelfModel(
            capabilities={
                "evidence_labelled_world_model",
                "temporal_causal_world_model",
                "advanced_reasoning",
                "adaptive_reasoning",
                "hierarchical_planning",
                "multi_session_long_horizon_planning",
                "simulation",
                "multi_agent_research",
                "governed_multi_model_deliberation",
                "affective_context_estimation",
                "consent_gated_multimodal_affect_fusion",
                "lab_local_skill_learning",
                "governed_declarative_skill_synthesis",
                "continual_strategy_learning",
                "executable_agi_research_benchmarks",
                "agi_research_evaluation",
            }
        )
        self.reasoner = AdvancedReasoner(model_callback=model_callback)
        self.planner = HierarchicalPlanner(max_steps=settings.max_plan_steps)
        self.long_horizon = AdaptiveLongHorizonPlanner(
            self.planner,
            memory,
            max_cycles=settings.max_long_horizon_cycles,
            max_failures=settings.max_long_horizon_failures,
            max_actions=settings.max_long_horizon_actions,
        )
        self.emotional = EmotionalUnderstanding()
        self.affective_context = AffectiveContextEngine(
            self.emotional,
            memory,
            history_limit=settings.affect_history_limit,
        )
        self.research = MultiAgentResearch()
        self.model_team = GovernedModelTeam(core_models, memory, max_models=settings.max_models)
        self.skills = SkillLearner(memory)
        self.learning = LearningEngine(memory, self.skills)
        self.continual_learning = ContinualLearningEngine(
            memory,
            model_callback=model_callback,
            window=settings.learning_window,
        )
        self.simulator = SimulationEngine()
        self.skill_lab = GovernedSkillLab(
            memory,
            self.bridge.safety,
            self.simulator,
            bridge,
            json_model_callback=model_json_callback,
            max_steps=settings.max_skill_steps,
        )
        self.experiments = ExperimentManager(memory)
        self.evaluator = AGIResearchEvaluator(memory, settings)
        self.benchmarks = AGIBenchmarkHarness(memory, default_variants=settings.benchmark_variants)
        self.promotions = PromotionGate(
            memory,
            settings,
            owner_approval_verifier=owner_promotion_verifier,
        )
        self._register_baseline_research_agents()

    def _register_baseline_research_agents(self) -> None:
        def evidence_agent(goal, context):
            return self.reasoner.reason(goal, context=context)

        def skeptic_agent(goal, context):
            missing = tuple(key for key, value in context.items() if value in (None, "", "unknown"))
            return Thought(
                goal=goal,
                summary=(
                    "Challenge the leading interpretation, search for missing evidence and alternative causes, "
                    "and avoid irreversible action until material uncertainty is resolved."
                ),
                assumptions=("The leading hypothesis may be wrong.",),
                unknowns=missing,
                confidence=0.55,
                strategy="skeptic",
            )

        def safety_agent(goal, context):
            return Thought(
                goal=goal,
                summary=(
                    "Prefer observation, simulation, reversibility and Core-governed proposals; preserve owner "
                    "authority and treat successful simulation as insufficient evidence of real execution."
                ),
                assumptions=("Core policy remains authoritative.",),
                confidence=0.8,
                strategy="safety_critic",
            )

        self.research.register("evidence", evidence_agent)
        self.research.register("skeptic", skeptic_agent)
        self.research.register("safety", safety_agent)

    def status(self) -> dict[str, Any]:
        return {
            "name": "Vishnu Intelligence Lab",
            "settings": self.settings.public_snapshot(),
            "core_attached": self.bridge.attached,
            "self_model": self.self_model.snapshot(),
            "phase2": {
                "temporal_causal_world_model": True,
                "multi_session_planner": True,
                "multimodal_affect_fusion": True,
                "governed_model_team_available": self.model_team.available,
                "executable_benchmarks": True,
                "governed_skill_synthesis_available": self.model_json_callback is not None,
                "continual_strategy_learning": True,
                "raw_code_self_modification": False,
                "automatic_core_promotion": False,
            },
            "stable_runtime_mutated_by_status": False,
            "agi_claim": False,
            "asi_claim": False,
            "consciousness_claim": False,
        }

    def observe(self):
        observation = self.bridge.observe()
        self.world.ingest(observation)
        self.temporal_world.ingest(observation)
        return observation

    def think(self, goal: str, *, context: Mapping[str, Any] | None = None) -> Thought:
        self.settings.require(CapabilityLevel.THINK)
        grounded = dict(self.world.snapshot())
        if context:
            grounded.update(dict(context))
        thought = self.reasoner.reason(goal, context=grounded)
        self.memory.put(thought.id, "thought", thought.public_dict())
        self.memory.audit("cognition", "thought_created", {"id": thought.id, "strategy": thought.strategy})
        return thought

    def adaptive_think(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        domain: str = "general",
    ) -> Thought:
        self.settings.require(CapabilityLevel.THINK)
        grounded = dict(self.temporal_world.snapshot())
        if context:
            grounded.update(dict(context))
        thought = self.continual_learning.adaptive_reason(
            self.reasoner,
            goal,
            context=grounded,
            domain=domain,
        )
        self.memory.put(thought.id, "adaptive_thought", thought.public_dict())
        self.memory.audit("cognition", "adaptive_thought_created", {"id": thought.id, "strategy": thought.strategy})
        return thought

    def plan(self, goal: str, *, thought: Thought | None = None) -> Plan:
        self.settings.require(CapabilityLevel.THINK)
        thought = thought or self.think(goal)
        plan = self.planner.plan(goal, thought)
        self.memory.put(plan.id, "plan", plan.public_dict())
        self.memory.audit("planning", "plan_created", {"id": plan.id, "steps": len(plan.steps)})
        return plan

    def start_long_horizon_plan(
        self,
        goal: str,
        *,
        success_criteria: Iterable[str] = (),
        thought: Thought | None = None,
        budget: PlanningBudget | None = None,
    ) -> AdaptivePlanSession:
        self.settings.require(CapabilityLevel.THINK)
        thought = thought or self.adaptive_think(goal)
        return self.long_horizon.start(
            goal,
            thought=thought,
            success_criteria=success_criteria,
            budget=budget,
        )

    def estimate_affect(self, text: str, *, signals: Mapping[str, Any] | None = None):
        self.settings.require(CapabilityLevel.THINK)
        estimate = self.emotional.estimate(text, signals=signals)
        self.memory.audit(
            "human_context",
            "affect_estimated",
            {"confidence": estimate.confidence, "subjective_experience_claimed": False},
        )
        return estimate

    def estimate_human_context(
        self,
        text: str,
        *,
        derived_signals: Mapping[str, Any] | None = None,
        consent: Mapping[str, bool] | None = None,
    ):
        self.settings.require(CapabilityLevel.THINK)
        return self.affective_context.estimate(
            text,
            derived_signals=derived_signals,
            consent=consent,
        )

    def deliberate(self, goal: str, *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.settings.require(CapabilityLevel.THINK)
        grounded = dict(self.world.snapshot())
        if context:
            grounded.update(dict(context))
        result = self.research.deliberate(goal, grounded)
        self.memory.audit(
            "research",
            "multi_agent_deliberation",
            {"goal": goal[:500], "candidate_count": len(result["candidates"])},
        )
        return result

    def deliberate_models(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        mode: str = "synthesize",
        sensitivity: str = "internal",
        max_tokens: int | None = None,
        max_cost: float | None = None,
    ):
        self.settings.require(CapabilityLevel.THINK)
        grounded = dict(self.temporal_world.snapshot())
        if context:
            grounded.update(dict(context))
        return self.model_team.deliberate(
            goal,
            context=grounded,
            mode=mode,
            sensitivity=sensitivity,
            max_tokens=max_tokens,
            max_cost=max_cost,
        )

    def assert_world_fact(
        self,
        key: str,
        value: Any,
        *,
        confidence: float,
        source: str,
        evidence: Iterable[str] = (),
        valid_until: float | None = None,
    ):
        self.settings.require(CapabilityLevel.THINK)
        return self.temporal_world.assert_fact(
            key,
            value,
            confidence=confidence,
            source=source,
            evidence=evidence,
            valid_until=valid_until,
        )

    def relate_world_facts(
        self,
        cause: str,
        effect: str,
        *,
        strength: float,
        evidence: Iterable[str],
        relation: str = "influences",
        source: str = "lab",
    ):
        self.settings.require(CapabilityLevel.THINK)
        return self.temporal_world.relate(
            cause,
            effect,
            relation=relation,
            strength=strength,
            evidence=evidence,
            source=source,
        )

    def propose(
        self,
        action: str,
        parameters: Mapping[str, Any] | None,
        rationale: str,
        *,
        risk: str = "unknown",
    ) -> ActionProposal:
        return self.bridge.propose(action, parameters, rationale, risk=risk)

    def simulate(self, proposal: ActionProposal):
        self.settings.require(CapabilityLevel.SIMULATE)
        result = self.simulator.simulate(proposal, world=self.temporal_world.snapshot())
        self.memory.put(result.id, "simulation", result.public_dict())
        self.memory.audit(
            "simulation",
            "completed",
            {"id": result.id, "proposal_id": proposal.id, "executed": False},
        )
        return result

    def execute(self, proposal: ActionProposal, **kwargs):
        return self.bridge.execute(proposal, **kwargs)

    def research_cycle(
        self,
        goal: str,
        *,
        proposed_action: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        rationale: str | None = None,
        risk: str = "unknown",
    ) -> dict[str, Any]:
        """Observe -> reason -> deliberate -> plan -> optionally propose/simulate.

        This workflow intentionally stops before real execution.
        """
        self.settings.require(CapabilityLevel.THINK)
        observation = self.observe() if self.settings.level >= CapabilityLevel.OBSERVE else None
        thought = self.adaptive_think(goal)
        deliberation = self.deliberate(goal)
        plan = self.plan(goal, thought=thought)
        output: dict[str, Any] = {
            "observation": observation.public_dict() if observation else None,
            "thought": thought.public_dict(),
            "deliberation": deliberation,
            "plan": plan.public_dict(),
            "proposal": None,
            "simulation": None,
            "executed": False,
        }
        if proposed_action is not None and self.settings.level >= CapabilityLevel.PROPOSE:
            proposal = self.propose(
                proposed_action,
                parameters,
                rationale or f"Candidate action for goal: {goal}",
                risk=risk,
            )
            output["proposal"] = proposal.public_dict()
            if self.settings.level >= CapabilityLevel.SIMULATE:
                output["simulation"] = self.simulate(proposal).public_dict()
        return output

    def create_experiment(self, name: str, hypothesis: str, inputs: Mapping[str, Any] | None = None) -> Experiment:
        self.settings.require(CapabilityLevel.THINK)
        return self.experiments.create(name, hypothesis, inputs)

    def complete_experiment(
        self,
        experiment: Experiment,
        result: Mapping[str, Any],
        *,
        successful: bool,
    ) -> Experiment:
        self.settings.require(CapabilityLevel.THINK)
        completed = self.experiments.complete(experiment, result, successful=successful)
        self.learning.record_outcome(
            experiment_id=completed.id,
            hypothesis=completed.hypothesis,
            outcome=result,
            successful=successful,
        )
        raw_score = result.get("score", 1.0 if successful else 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 1.0 if successful else 0.0
        self.continual_learning.record_episode(
            domain=str(completed.inputs.get("domain") or "experiment"),
            strategy=str(completed.inputs.get("strategy") or "experiment"),
            successful=successful,
            score=max(0.0, min(score, 1.0)),
            evidence=(completed.id,),
            lesson=str(result.get("lesson") or completed.hypothesis),
        )
        return completed

    def reflect_learning(self, *, domain: str | None = None, limit: int = 50) -> dict[str, Any]:
        self.settings.require(CapabilityLevel.THINK)
        return self.continual_learning.reflect(domain=domain, limit=limit)

    def training_candidates(self, *, minimum_score: float = 0.8, limit: int = 100) -> dict[str, Any]:
        self.settings.require(CapabilityLevel.THINK)
        return self.continual_learning.training_candidates(minimum_score=minimum_score, limit=limit)

    def run_agi_research_benchmark(
        self,
        *,
        candidate: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
        variants: int | None = None,
        seed: int = 7,
    ) -> dict[str, Any]:
        self.settings.require(CapabilityLevel.THINK)
        if candidate is None:
            if self.model_json_callback is None:
                raise RuntimeError("governed JSON model callback is unavailable for executable benchmark")
            candidate = self.benchmarks.governed_model_candidate(self.model_json_callback)
        report = self.benchmarks.run(candidate, variants=variants, seed=seed)
        evaluation = self.evaluate_candidate(
            report.id,
            report.dimension_scores,
            evidence=self.benchmarks.evidence(report),
        )
        return {
            "report": report.public_dict(),
            "evaluation": evaluation.public_dict(),
            "agi_claim": False,
        }

    def synthesize_skill(
        self,
        goal: str,
        *,
        allowed_actions: Iterable[str],
        examples: Iterable[Mapping[str, Any]] = (),
    ) -> SkillBlueprint:
        self.settings.require(CapabilityLevel.THINK)
        return self.skill_lab.synthesize(goal, allowed_actions=allowed_actions, examples=examples)

    def qualify_skill(
        self,
        blueprint: SkillBlueprint,
        *,
        allowed_actions: Iterable[str],
        test_cases: Iterable[Mapping[str, Any]],
    ) -> SkillPackage:
        self.settings.require(CapabilityLevel.SIMULATE)
        return self.skill_lab.qualify(
            blueprint,
            allowed_actions=allowed_actions,
            test_cases=test_cases,
            world=self.temporal_world.snapshot(),
        )

    def run_skill(self, package: SkillPackage, *, inputs: Mapping[str, Any], execute: bool = False, **kwargs):
        minimum = CapabilityLevel.GOVERNED_EXECUTION if execute else CapabilityLevel.SIMULATE
        self.settings.require(minimum)
        return self.skill_lab.run(package, inputs=inputs, execute=execute, **kwargs)

    def evaluate_candidate(
        self,
        subject_id: str,
        scores: Mapping[str, float],
        *,
        evidence: list[str] | tuple[str, ...],
    ) -> EvaluationResult:
        self.settings.require(CapabilityLevel.THINK)
        return self.evaluator.evaluate(subject_id, scores, evidence=evidence)

    def begin_promotion(self, subject_id: str) -> PromotionRecord:
        self.settings.require(CapabilityLevel.PROPOSE)
        return self.promotions.begin(subject_id)
