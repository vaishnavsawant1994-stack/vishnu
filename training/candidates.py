from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from uuid import uuid4

from security.projection_redaction import sanitize_sensitive_text


class PrivacyLevel(str, Enum):
    PUBLIC = 'public'
    INTERNAL = 'internal'
    PRIVATE = 'private'
    SENSITIVE = 'sensitive'
    RESTRICTED = 'restricted'


class CandidateStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    TOMBSTONED = 'tombstoned'


@dataclass(frozen=True)
class TrainingCandidate:
    candidate_id: str
    created_at: str
    source_type: str
    source_fingerprint: str
    prompt: str
    response: str
    provider_id: str | None
    model_id: str | None
    privacy_level: PrivacyLevel
    provenance: str | None
    consent_basis: str | None
    verifier_score: float | None
    contains_secret: bool
    training_eligible: bool
    status: CandidateStatus
    reason_codes: tuple[str, ...]

    def approve(self) -> 'TrainingCandidate':
        if not self.training_eligible:
            raise ValueError('ineligible candidate cannot be approved')
        if self.status is CandidateStatus.TOMBSTONED:
            raise ValueError('tombstoned candidate cannot be approved')
        return replace(self, status=CandidateStatus.APPROVED)

    def reject(self, reason: str = 'owner_or_policy_rejected') -> 'TrainingCandidate':
        if self.status is CandidateStatus.TOMBSTONED:
            return self
        return replace(
            self,
            status=CandidateStatus.REJECTED,
            training_eligible=False,
            reason_codes=tuple(dict.fromkeys((*self.reason_codes, str(reason)))),
        )

    def tombstone(self, reason: str = 'source_deleted_or_consent_revoked') -> 'TrainingCandidate':
        return replace(
            self,
            prompt='',
            response='',
            status=CandidateStatus.TOMBSTONED,
            training_eligible=False,
            reason_codes=tuple(dict.fromkeys((*self.reason_codes, str(reason)))),
        )


class TrainingCandidateFactory:
    """Create sanitized, governed candidates without retaining raw secrets.

    Capture being enabled means a candidate may be proposed. It does not mean
    the candidate is eligible or approved. Secret-bearing, connected-service
    and restricted data fail closed, and hidden chain-of-thought is never
    accepted as a data type.
    """

    _DISALLOWED_CONTENT_KINDS = {
        'chain_of_thought',
        'hidden_chain_of_thought',
        'private_reasoning',
        'reasoning_trace',
        'scratchpad',
    }
    _DISALLOWED_SOURCE_TYPES = {
        'credential',
        'secret',
        'password',
        'authentication_secret',
        'gmail',
        'google_drive',
        'google-drive',
        'slack',
        'connected_service',
        'connector',
    }

    def create(
        self,
        *,
        source_type: str,
        source_id: str,
        prompt: str,
        response: str,
        privacy_level: PrivacyLevel | str = PrivacyLevel.INTERNAL,
        provider_id: str | None = None,
        model_id: str | None = None,
        provenance: str | None = None,
        consent_basis: str | None = None,
        verifier_score: float | None = None,
        content_kind: str = 'instruction_response',
        source_training_allowed: bool = True,
    ) -> TrainingCandidate:
        kind = str(content_kind).strip().lower()
        if kind in self._DISALLOWED_CONTENT_KINDS:
            raise ValueError('hidden chain-of-thought cannot be captured for training')

        source = str(source_type).strip().lower() or 'unknown'
        if source in self._DISALLOWED_SOURCE_TYPES:
            source_training_allowed = False

        try:
            privacy = privacy_level if isinstance(privacy_level, PrivacyLevel) else PrivacyLevel(str(privacy_level).strip().lower())
        except ValueError as exc:
            raise ValueError('unsupported privacy level') from exc

        if verifier_score is not None and not 0.0 <= float(verifier_score) <= 1.0:
            raise ValueError('verifier_score must be between 0 and 1')

        raw_prompt = str(prompt)
        raw_response = str(response)
        clean_prompt = sanitize_sensitive_text(raw_prompt)
        clean_response = sanitize_sensitive_text(raw_response)
        contains_secret = clean_prompt != raw_prompt or clean_response != raw_response

        reasons: list[str] = []
        eligible = bool(source_training_allowed)
        if not source_training_allowed:
            reasons.append('source_training_not_allowed')
        if contains_secret:
            eligible = False
            reasons.append('secret_detected_and_redacted')
        if privacy in {PrivacyLevel.SENSITIVE, PrivacyLevel.RESTRICTED}:
            eligible = False
            reasons.append('privacy_level_not_training_eligible')
        if not str(provenance or '').strip():
            eligible = False
            reasons.append('provenance_required')
        if privacy in {PrivacyLevel.PRIVATE, PrivacyLevel.SENSITIVE, PrivacyLevel.RESTRICTED} and not str(consent_basis or '').strip():
            eligible = False
            reasons.append('consent_basis_required')

        fingerprint_input = f'{source}\0{source_id}'.encode('utf-8', errors='replace')
        source_fingerprint = sha256(fingerprint_input).hexdigest()
        return TrainingCandidate(
            candidate_id=str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            source_type=source,
            source_fingerprint=source_fingerprint,
            prompt=clean_prompt,
            response=clean_response,
            provider_id=str(provider_id).strip() if provider_id else None,
            model_id=str(model_id).strip() if model_id else None,
            privacy_level=privacy,
            provenance=str(provenance).strip() if provenance else None,
            consent_basis=str(consent_basis).strip() if consent_basis else None,
            verifier_score=float(verifier_score) if verifier_score is not None else None,
            contains_secret=contains_secret,
            training_eligible=eligible,
            status=CandidateStatus.PENDING,
            reason_codes=tuple(reasons or ['candidate_eligible_for_review']),
        )
