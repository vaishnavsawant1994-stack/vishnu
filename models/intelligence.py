from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from models.adaptive_strategy import AdaptiveStrategy, ExecutionPattern, StrategyDecision, StrategyRequest, TaskComplexity
from models.contracts import ModelRequest, ModelResponse
from models.deliberation import DeliberationEngine
from models.intelligence_modes import IntelligenceMode, intelligence_profile
from models.performance import ModelPerformanceTracker, PerformanceObservation
from models.verifier import EvidenceVerifier, VerificationEvidence, VerificationResult


@dataclass(frozen=True)
class IntelligenceOutcome:
    response: ModelResponse
    strategy: StrategyDecision
    verification: VerificationResult | None = None
    deliberation_mode: str | None = None
    failures: tuple[str, ...] = ()


class IntelligenceEngine:
    """Adaptive intelligence layer over the canonical governed model router.

    The engine may choose bounded reasoning, deliberation and verification, but
    all model calls still flow through the existing governed router. It cannot
    execute tools, approve effects, change privacy policy, or grant authority.
    """

    def __init__(
        self,
        router,
        *,
        default_mode: IntelligenceMode | str = IntelligenceMode.STANDARD,
        performance: ModelPerformanceTracker | None = None,
        verifier: EvidenceVerifier | None = None,
        capture_hook: Callable[[ModelRequest, ModelResponse, VerificationResult | None, StrategyDecision], None] | None = None,
    ) -> None:
        self.router = router
        self.default_mode = self._mode(default_mode)
        self.performance = performance or ModelPerformanceTracker()
        self.verifier = verifier or EvidenceVerifier()
        self.capture_hook = capture_hook
        self.strategy = AdaptiveStrategy()
        self.last_outcome: IntelligenceOutcome | None = None

    @staticmethod
    def _mode(value: IntelligenceMode | str) -> IntelligenceMode:
        if isinstance(value, IntelligenceMode):
            return value
        normalized = str(value or '').strip().lower()
        if normalized == 'focused':
            normalized = IntelligenceMode.SMART.value
        return IntelligenceMode(normalized)

    def mode_for(self, request: ModelRequest) -> IntelligenceMode:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        raw = metadata.get('intelligence_mode', self.default_mode.value)
        try:
            return self._mode(raw)
        except ValueError:
            return self.default_mode

    def should_handle(self, request: ModelRequest) -> bool:
        return self.mode_for(request) is not IntelligenceMode.STANDARD

    @staticmethod
    def _complexity(request: ModelRequest) -> TaskComplexity:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        raw = str(metadata.get('task_complexity', metadata.get('complexity', 'medium'))).strip().lower()
        try:
            return TaskComplexity(raw)
        except ValueError:
            return TaskComplexity.MEDIUM

    @staticmethod
    def _verification_evidence(request: ModelRequest) -> VerificationEvidence:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        raw = metadata.get('verification_evidence')
        if not isinstance(raw, dict):
            return VerificationEvidence()
        allowed = {
            'task_correctness', 'constraint_compliance', 'tool_agreement',
            'evidence_support', 'factual_consistency', 'project_consistency',
            'unsupported_claims', 'contradictions', 'hallucination_signals',
        }
        return VerificationEvidence(**{key: raw[key] for key in allowed if key in raw})

    def _decision(self, request: ModelRequest) -> StrategyDecision:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        mode = self.mode_for(request)
        capture_override = metadata.get('training_capture')
        profile = intelligence_profile(mode, training_capture=None if capture_override is None else bool(capture_override))
        return self.strategy.decide(
            StrategyRequest(
                profile=profile,
                task_domain=str(metadata.get('task_domain', request.routing_policy or 'general')),
                complexity=self._complexity(request),
                sensitivity=request.sensitivity,
                required_capabilities=tuple(request.required_capabilities),
                evidence_required=bool(metadata.get('evidence_required', False)),
            )
        )

    def request(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError('request must be ModelRequest')
        decision = self._decision(request)
        failures: tuple[str, ...] = ()
        deliberation_mode: str | None = None

        if decision.pattern is ExecutionPattern.SPECIALIST_RACE:
            deliberation_mode = 'synthesize'
            result = DeliberationEngine(self.router, max_models=decision.max_models).run(request, mode=deliberation_mode)
            response = result.final
            failures = result.failures
        elif decision.pattern is ExecutionPattern.DEEP_CONSENSUS:
            deliberation_mode = 'consensus'
            result = DeliberationEngine(self.router, max_models=decision.max_models).run(request, mode=deliberation_mode)
            response = result.final
            failures = result.failures
        else:
            response = self.router.request(request)

        verification: VerificationResult | None = None
        if decision.verifier_required:
            verification = self.verifier.verify(self._verification_evidence(request))

        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        self.performance.record(
            PerformanceObservation(
                task_domain=str(metadata.get('task_domain', request.routing_policy or 'general')),
                provider_id=response.provider_id,
                model_id=response.model_id,
                success=True,
                verifier_score=(verification.score if verification is not None and verification.evaluated_dimensions else None),
                latency_ms=response.usage.latency_ms,
                estimated_cost=response.usage.estimated_cost,
                accepted=metadata.get('accepted') if isinstance(metadata.get('accepted'), bool) else None,
                corrected=bool(metadata.get('corrected', False)),
                regenerated=bool(metadata.get('regenerated', False)),
                fallback=bool(response.retry_count),
            )
        )

        if decision.training_capture and self.capture_hook is not None:
            self.capture_hook(request, response, verification, decision)

        self.last_outcome = IntelligenceOutcome(
            response=response,
            strategy=decision,
            verification=verification,
            deliberation_mode=deliberation_mode,
            failures=failures,
        )
        return response
