from __future__ import annotations

from models.contracts import ModelRequest, ModelResponse
from models.adaptive_strategy import StrategyDecision
from models.verifier import VerificationResult
from training.candidates import PrivacyLevel, TrainingCandidate, TrainingCandidateFactory
from training.store import TrainingCandidateStore


class TrainingCollector:
    """Capture sanitized candidates while keeping eligibility fail-closed.

    Training Capture being ON means ordinary Vishnu model exchanges may create
    governed candidate records without requiring every caller to manually add
    training metadata. That default capture never bypasses secret filtering,
    privacy/consent rules, provenance, quality verification, source policy,
    deduplication or owner review. A caller may explicitly mark a source as not
    training-allowed, and turning Training Capture OFF prevents this hook from
    being invoked at all.
    """

    def __init__(self, store: TrainingCandidateStore, *, factory: TrainingCandidateFactory | None = None) -> None:
        self.store = store
        self.factory = factory or TrainingCandidateFactory()

    @staticmethod
    def _privacy(request: ModelRequest, metadata: dict) -> PrivacyLevel:
        explicit = metadata.get('training_privacy_level')
        if explicit:
            return PrivacyLevel(str(explicit).strip().lower())
        if request.sensitivity == 'secret':
            return PrivacyLevel.RESTRICTED
        if request.sensitivity == 'sensitive':
            return PrivacyLevel.SENSITIVE
        if request.sensitivity == 'private':
            return PrivacyLevel.PRIVATE
        return PrivacyLevel.INTERNAL

    def capture(
        self,
        request: ModelRequest,
        response: ModelResponse,
        verification: VerificationResult | None,
        strategy: StrategyDecision,
    ) -> TrainingCandidate | None:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}

        # Runtime-authored provenance is safe to provide by default for an
        # ordinary in-product model exchange. Connected-service and credential
        # source types are still rejected by TrainingCandidateFactory.
        source_id = str(metadata.get('training_source_id') or request.request_id or '').strip()
        if not source_id:
            return None
        source_type = str(metadata.get('training_source_type') or 'model_exchange').strip().lower()
        provenance = str(metadata.get('training_provenance') or 'vishnu_runtime:model_exchange').strip()
        consent_basis = str(metadata.get('training_consent_basis') or '').strip()
        source_allowed = metadata.get('training_source_allowed') is not False

        quality_score = None
        if verification is not None and verification.evaluated_dimensions:
            quality_score = verification.score
        elif metadata.get('training_quality_score') is not None:
            quality_score = metadata.get('training_quality_score')

        candidate = self.factory.create(
            source_type=source_type,
            source_id=source_id,
            prompt=request.prompt,
            response=response.content,
            privacy_level=self._privacy(request, metadata),
            provider_id=response.provider_id,
            model_id=response.model_id,
            provenance=provenance,
            consent_basis=consent_basis or None,
            verifier_score=quality_score,
            content_kind=str(metadata.get('training_content_kind') or 'instruction_response'),
            source_training_allowed=source_allowed,
        )
        return self.store.save(candidate)
