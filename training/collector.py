from __future__ import annotations

from models.contracts import ModelRequest, ModelResponse
from models.adaptive_strategy import StrategyDecision
from models.verifier import VerificationResult
from training.candidates import PrivacyLevel, TrainingCandidate, TrainingCandidateFactory
from training.store import TrainingCandidateStore


class TrainingCollector:
    """Capture model exchanges only when the request carries explicit policy metadata."""

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
        return PrivacyLevel.INTERNAL

    def capture(
        self,
        request: ModelRequest,
        response: ModelResponse,
        verification: VerificationResult | None,
        strategy: StrategyDecision,
    ) -> TrainingCandidate | None:
        metadata = request.metadata if isinstance(request.metadata, dict) else {}

        # No silent conversation-to-training pipeline. The caller/source must
        # explicitly identify itself and assert training permission.
        source_id = str(metadata.get('training_source_id') or '').strip()
        provenance = str(metadata.get('training_provenance') or '').strip()
        consent_basis = str(metadata.get('training_consent_basis') or '').strip()
        source_allowed = metadata.get('training_source_allowed') is True
        if not source_id or not provenance or not source_allowed:
            return None

        source_type = str(metadata.get('training_source_type') or 'model_exchange').strip().lower()
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
            verifier_score=(verification.score if verification is not None and verification.evaluated_dimensions else None),
            content_kind=str(metadata.get('training_content_kind') or 'instruction_response'),
            source_training_allowed=source_allowed,
        )
        self.store.save(candidate)
        return candidate
