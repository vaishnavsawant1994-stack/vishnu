from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from models.intelligence_modes import IntelligenceMode, IntelligenceProfile


class TaskComplexity(str, Enum):
    TRIVIAL = 'trivial'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class ExecutionPattern(str, Enum):
    SINGLE = 'single'
    PRIMARY_PLUS_VERIFIER = 'primary_plus_verifier'
    SPECIALIST_RACE = 'specialist_race'
    DEEP_CONSENSUS = 'deep_consensus'


@dataclass(frozen=True)
class StrategyRequest:
    profile: IntelligenceProfile
    task_domain: str = 'general'
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    sensitivity: str = 'internal'
    required_capabilities: tuple[str, ...] = ()
    evidence_required: bool = False


@dataclass(frozen=True)
class StrategyDecision:
    mode: IntelligenceMode
    pattern: ExecutionPattern
    max_models: int
    verifier_required: bool
    training_capture: bool
    reason_codes: tuple[str, ...]

    @property
    def deliberation_enabled(self) -> bool:
        return self.pattern in {ExecutionPattern.SPECIALIST_RACE, ExecutionPattern.DEEP_CONSENSUS}


class AdaptiveStrategy:
    """Pure strategy recommendation layer.

    This class chooses a bounded reasoning pattern only. It does not select an
    unauthorized provider, execute a tool, change policy, or grant approval.
    Those responsibilities stay with Vishnu's existing governed router and
    execution/security layers.
    """

    def decide(self, request: StrategyRequest) -> StrategyDecision:
        profile = request.profile
        reasons: list[str] = [f'mode:{profile.mode.value}', f'complexity:{request.complexity.value}']

        if profile.mode is IntelligenceMode.STANDARD:
            return StrategyDecision(
                mode=profile.mode,
                pattern=ExecutionPattern.SINGLE,
                max_models=1,
                verifier_required=False,
                training_capture=profile.training_capture,
                reason_codes=tuple(reasons + ['standard_preserves_existing_routing']),
            )

        # Higher modes are permission ceilings, not instructions to spend more.
        if request.complexity in {TaskComplexity.TRIVIAL, TaskComplexity.LOW} and not request.evidence_required:
            return StrategyDecision(
                mode=profile.mode,
                pattern=ExecutionPattern.SINGLE,
                max_models=1,
                verifier_required=False,
                training_capture=profile.training_capture,
                reason_codes=tuple(reasons + ['simple_task_single_model']),
            )

        if profile.mode is IntelligenceMode.SMART:
            needs_verifier = bool(profile.verification and (request.evidence_required or request.complexity in {TaskComplexity.HIGH, TaskComplexity.CRITICAL}))
            return StrategyDecision(
                mode=profile.mode,
                pattern=ExecutionPattern.PRIMARY_PLUS_VERIFIER if needs_verifier else ExecutionPattern.SINGLE,
                max_models=min(profile.max_models, 2 if needs_verifier else 1),
                verifier_required=needs_verifier,
                training_capture=profile.training_capture,
                reason_codes=tuple(reasons + (['evidence_or_high_risk_verification'] if needs_verifier else ['adaptive_single_model'])),
            )

        if profile.mode is IntelligenceMode.DEEP:
            if request.complexity in {TaskComplexity.HIGH, TaskComplexity.CRITICAL}:
                return StrategyDecision(
                    mode=profile.mode,
                    pattern=ExecutionPattern.SPECIALIST_RACE,
                    max_models=min(profile.max_models, 4),
                    verifier_required=True,
                    training_capture=profile.training_capture,
                    reason_codes=tuple(reasons + ['bounded_specialist_deliberation']),
                )
            return StrategyDecision(
                mode=profile.mode,
                pattern=ExecutionPattern.PRIMARY_PLUS_VERIFIER,
                max_models=min(profile.max_models, 2),
                verifier_required=True,
                training_capture=profile.training_capture,
                reason_codes=tuple(reasons + ['deep_mode_verification']),
            )

        # RESEARCH uses the deepest bounded pattern only for genuinely hard work.
        if request.complexity in {TaskComplexity.HIGH, TaskComplexity.CRITICAL}:
            return StrategyDecision(
                mode=profile.mode,
                pattern=ExecutionPattern.DEEP_CONSENSUS,
                max_models=min(profile.max_models, 5),
                verifier_required=True,
                training_capture=profile.training_capture,
                reason_codes=tuple(reasons + ['research_deep_consensus', 'agreement_is_not_proof']),
            )
        return StrategyDecision(
            mode=profile.mode,
            pattern=ExecutionPattern.PRIMARY_PLUS_VERIFIER,
            max_models=min(profile.max_models, 2),
            verifier_required=True,
            training_capture=profile.training_capture,
            reason_codes=tuple(reasons + ['research_verification']),
        )
