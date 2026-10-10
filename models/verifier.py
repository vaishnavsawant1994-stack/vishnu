from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationEvidence:
    """Observable evidence used to assess a model result.

    All dimensions are normalized to [0, 1]. Missing dimensions are ignored
    rather than guessed. Agreement between models is intentionally not a truth
    signal and is therefore not represented here.
    """

    task_correctness: float | None = None
    constraint_compliance: float | None = None
    tool_agreement: float | None = None
    evidence_support: float | None = None
    factual_consistency: float | None = None
    project_consistency: float | None = None
    unsupported_claims: int = 0
    contradictions: int = 0
    hallucination_signals: int = 0

    def __post_init__(self) -> None:
        for name in (
            'task_correctness',
            'constraint_compliance',
            'tool_agreement',
            'evidence_support',
            'factual_consistency',
            'project_consistency',
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f'{name} must be between 0 and 1')
        for name in ('unsupported_claims', 'contradictions', 'hallucination_signals'):
            if int(getattr(self, name)) < 0:
                raise ValueError(f'{name} cannot be negative')


@dataclass(frozen=True)
class VerificationResult:
    score: float
    passed: bool
    evaluated_dimensions: int
    reason_codes: tuple[str, ...]


class EvidenceVerifier:
    """Deterministic verifier for observable correctness signals.

    Verification is advisory. A passing score never grants tool access,
    permission, approval, or execution authority.
    """

    _WEIGHTS = {
        'task_correctness': 0.25,
        'constraint_compliance': 0.20,
        'tool_agreement': 0.20,
        'evidence_support': 0.15,
        'factual_consistency': 0.10,
        'project_consistency': 0.10,
    }

    def __init__(self, *, pass_threshold: float = 0.70) -> None:
        if not 0.0 <= float(pass_threshold) <= 1.0:
            raise ValueError('pass_threshold must be between 0 and 1')
        self.pass_threshold = float(pass_threshold)

    def verify(self, evidence: VerificationEvidence) -> VerificationResult:
        weighted = 0.0
        total_weight = 0.0
        evaluated = 0
        reasons: list[str] = []

        for name, weight in self._WEIGHTS.items():
            value = getattr(evidence, name)
            if value is None:
                continue
            weighted += float(value) * weight
            total_weight += weight
            evaluated += 1

        base_score = weighted / total_weight if total_weight else 0.0
        penalty = min(
            0.85,
            (0.08 * evidence.unsupported_claims)
            + (0.15 * evidence.contradictions)
            + (0.20 * evidence.hallucination_signals),
        )
        score = max(0.0, min(1.0, base_score - penalty))

        if evaluated == 0:
            reasons.append('insufficient_evidence')
        if evidence.unsupported_claims:
            reasons.append('unsupported_claims')
        if evidence.contradictions:
            reasons.append('contradictions')
        if evidence.hallucination_signals:
            reasons.append('hallucination_signals')

        passed = bool(evaluated and score >= self.pass_threshold)
        reasons.append('verification_passed' if passed else 'verification_failed')
        reasons.append('verification_is_not_authorization')
        return VerificationResult(
            score=score,
            passed=passed,
            evaluated_dimensions=evaluated,
            reason_codes=tuple(reasons),
        )
