from __future__ import annotations

from typing import Any, Mapping

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
from .memory import LabMemory
from .models import ActionProposal, EvaluationResult, Experiment, Plan, PromotionRecord, Thought
from .safety import SimulationEngine


class IntelligenceLabRuntime:
    """Top-level experimental cognition runtime.

    No method silently promotes itself to a higher capability level. Every public
    operation checks the configured ceiling before performing work.
    """

    def __init__(
        self,
        settings: LabSettings,
        memory: LabMemory,
        bridge: VishnuCoreBridge,
        *,
        model_callback=None,
        owner_promotion_verifier=None,
    ):
        self.settings = settings
        self.memory = memory
        self.bridge = bridge
        self.world = WorldModel(memory)
        self.self_model = SelfModel(
            capabilities={
                "evidence_labelled_world_model",
                "advanced_reasoning",
                "hierarchical_planning",
                "simulation",
                "multi_agent_research",
                "affective_context_estimation",
                "lab_local_skill_learning",
                "agi_research_evaluation",
            }
        )
        self.reasoner = AdvancedReasoner(model_callback=model_callback)
        self.planner = HierarchicalPlanner(max_steps=settings.max_plan_steps)
        self.emotional = EmotionalUnderstanding()
        self.research = MultiAgentResearch()
        self.skills = SkillLearner(memory)
        self.learning = LearningEngine(memory, self.skills)
        self.simulator = SimulationEngine()
        self.experiments = ExperimentManager(memory)
        self.evaluator = AGIResearchEvaluator(memory, settings)
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
            "stable_runtime_mutated_by_status": False,
            "agi_claim": False,
            "asi_claim": False,
            "consciousness_claim": False,
        }

    def observe(self):
        observation = self.bridge.observe()
        self.world.ingest(observation)
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

    def plan(self, goal: str, *, thought: Thought | None = None) -> Plan:
        self.settings.require(CapabilityLevel.THINK)
        thought = thought or self.think(goal)
        plan = self.planner.plan(goal, thought)
        self.memory.put(plan.id, "plan", plan.public_dict())
        self.memory.audit("planning", "plan_created", {"id": plan.id, "steps": len(plan.steps)})
        return plan

    def estimate_affect(self, text: str, *, signals: Mapping[str, Any] | None = None):
        self.settings.require(CapabilityLevel.THINK)
        estimate = self.emotional.estimate(text, signals=signals)
        self.memory.audit(
            "human_context",
            "affect_estimated",
            {"confidence": estimate.confidence, "subjective_experience_claimed": False},
        )
        return estimate

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
        result = self.simulator.simulate(proposal, world=self.world.snapshot())
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
        thought = self.think(goal)
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
        return completed

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
