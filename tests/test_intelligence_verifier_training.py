import pytest

from models.verifier import EvidenceVerifier, VerificationEvidence
from training.candidates import CandidateStatus, PrivacyLevel, TrainingCandidateFactory


def test_verifier_passes_well_grounded_result_without_granting_authority():
    result = EvidenceVerifier(pass_threshold=0.70).verify(
        VerificationEvidence(
            task_correctness=0.95,
            constraint_compliance=1.0,
            tool_agreement=0.9,
            evidence_support=0.9,
            factual_consistency=0.95,
            project_consistency=1.0,
        )
    )

    assert result.passed is True
    assert result.score >= 0.70
    assert 'verification_is_not_authorization' in result.reason_codes


def test_verifier_penalizes_unsupported_or_hallucinated_output():
    verifier = EvidenceVerifier(pass_threshold=0.70)
    clean = verifier.verify(
        VerificationEvidence(
            task_correctness=0.9,
            constraint_compliance=0.9,
            evidence_support=0.9,
        )
    )
    risky = verifier.verify(
        VerificationEvidence(
            task_correctness=0.9,
            constraint_compliance=0.9,
            evidence_support=0.9,
            unsupported_claims=2,
            contradictions=1,
            hallucination_signals=1,
        )
    )

    assert risky.score < clean.score
    assert risky.passed is False
    assert 'unsupported_claims' in risky.reason_codes
    assert 'contradictions' in risky.reason_codes
    assert 'hallucination_signals' in risky.reason_codes


def test_verifier_fails_closed_without_evidence():
    result = EvidenceVerifier().verify(VerificationEvidence())

    assert result.passed is False
    assert result.score == 0.0
    assert result.evaluated_dimensions == 0
    assert 'insufficient_evidence' in result.reason_codes


def test_verifier_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        VerificationEvidence(task_correctness=1.01)
    with pytest.raises(ValueError):
        VerificationEvidence(unsupported_claims=-1)
    with pytest.raises(ValueError):
        EvidenceVerifier(pass_threshold=1.1)


def test_training_candidate_is_sanitized_and_secret_bearing_data_is_ineligible():
    candidate = TrainingCandidateFactory().create(
        source_type='conversation',
        source_id='conv-123',
        prompt='Use api_key=super-secret-value to continue',
        response='Authorization: Bearer abcdefghijklmnop',
        provenance='conversation:conv-123',
        privacy_level=PrivacyLevel.INTERNAL,
    )

    assert candidate.contains_secret is True
    assert 'super-secret-value' not in candidate.prompt
    assert 'abcdefghijklmnop' not in candidate.response
    assert '[redacted]' in candidate.prompt
    assert '[redacted]' in candidate.response
    assert candidate.training_eligible is False
    assert 'secret_detected_and_redacted' in candidate.reason_codes
    with pytest.raises(ValueError, match='ineligible candidate'):
        candidate.approve()


def test_eligible_candidate_requires_governance_then_can_be_approved():
    candidate = TrainingCandidateFactory().create(
        source_type='conversation',
        source_id='conv-456',
        prompt='Explain the deployment plan.',
        response='Use the governed release workflow and verify health checks.',
        provenance='conversation:conv-456',
        consent_basis='owner-default-training-policy',
        privacy_level=PrivacyLevel.PRIVATE,
        verifier_score=0.94,
    )

    assert candidate.training_eligible is True
    assert candidate.status is CandidateStatus.PENDING
    approved = candidate.approve()
    assert approved.status is CandidateStatus.APPROVED


def test_private_candidate_without_consent_is_not_training_eligible():
    candidate = TrainingCandidateFactory().create(
        source_type='project',
        source_id='project-event-1',
        prompt='A',
        response='B',
        provenance='project:event-1',
        privacy_level=PrivacyLevel.PRIVATE,
    )

    assert candidate.training_eligible is False
    assert 'consent_basis_required' in candidate.reason_codes


def test_restricted_candidate_is_never_eligible_even_with_consent():
    candidate = TrainingCandidateFactory().create(
        source_type='conversation',
        source_id='restricted-1',
        prompt='A',
        response='B',
        provenance='conversation:restricted-1',
        consent_basis='explicit-owner-consent',
        privacy_level=PrivacyLevel.RESTRICTED,
    )

    assert candidate.training_eligible is False
    assert 'privacy_level_not_training_eligible' in candidate.reason_codes


def test_missing_provenance_fails_closed():
    candidate = TrainingCandidateFactory().create(
        source_type='conversation',
        source_id='conv-789',
        prompt='A',
        response='B',
    )

    assert candidate.training_eligible is False
    assert 'provenance_required' in candidate.reason_codes


def test_hidden_chain_of_thought_capture_is_rejected():
    with pytest.raises(ValueError, match='chain-of-thought'):
        TrainingCandidateFactory().create(
            source_type='conversation',
            source_id='conv-cot',
            prompt='A',
            response='B',
            provenance='conversation:conv-cot',
            content_kind='chain_of_thought',
        )


def test_tombstone_removes_content_and_prevents_future_approval():
    candidate = TrainingCandidateFactory().create(
        source_type='conversation',
        source_id='conv-delete',
        prompt='Prompt to remove',
        response='Response to remove',
        provenance='conversation:conv-delete',
    )
    tombstoned = candidate.tombstone()

    assert tombstoned.status is CandidateStatus.TOMBSTONED
    assert tombstoned.training_eligible is False
    assert tombstoned.prompt == ''
    assert tombstoned.response == ''
    with pytest.raises(ValueError, match='ineligible candidate'):
        tombstoned.approve()
