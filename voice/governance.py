"""Consent and provenance primitives for voice cloning and reference samples.

These records are intentionally persistence-agnostic. Vishnu's existing
storage and audit authorities decide where they are stored. Raw biometric-like
voice material defaults to device-only handling and cloning requires an
explicit affirmative consent record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class VoiceStoragePolicy(str, Enum):
    DEVICE_ONLY = "device_only"
    PROGRESS_ONLY = "progress_only"
    SYNC_EVERYWHERE = "sync_everywhere"
    ON_DEMAND = "on_demand"


class VoiceSourceKind(str, Enum):
    OWNER_RECORDING = "owner_recording"
    PERMITTED_RECORDING = "permitted_recording"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"


class VoiceConsentError(PermissionError):
    """Raised when cloning is requested without valid recorded consent."""


@dataclass(frozen=True, slots=True)
class VoiceConsentRecord:
    consent_id: str
    subject_id: str
    granted_by_owner: bool
    allows_voice_cloning: bool
    allows_commercial_use: bool = False
    granted_at: str = ""
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        if not self.consent_id.strip() or not self.subject_id.strip():
            raise ValueError("consent_id and subject_id must not be empty")
        if not self.granted_at:
            object.__setattr__(self, "granted_at", datetime.now(timezone.utc).isoformat())

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.granted_by_owner and self.allows_voice_cloning

    def assert_allows_clone(self, *, commercial_use: bool = False) -> None:
        if not self.active:
            raise VoiceConsentError("active explicit voice-cloning consent is required")
        if commercial_use and not self.allows_commercial_use:
            raise VoiceConsentError("consent does not allow commercial voice use")


@dataclass(frozen=True, slots=True)
class VoiceSampleProvenance:
    sample_id: str
    subject_id: str
    source_kind: VoiceSourceKind
    consent_id: str
    content_hash: str
    storage_policy: VoiceStoragePolicy = VoiceStoragePolicy.DEVICE_ONLY
    source_description: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("sample_id", self.sample_id),
            ("subject_id", self.subject_id),
            ("consent_id", self.consent_id),
            ("content_hash", self.content_hash),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


def assert_sample_usable_for_clone(
    sample: VoiceSampleProvenance,
    consent: VoiceConsentRecord,
    *,
    commercial_use: bool = False,
) -> None:
    """Fail closed if sample provenance and consent do not match."""

    if sample.consent_id != consent.consent_id or sample.subject_id != consent.subject_id:
        raise VoiceConsentError("voice sample provenance does not match its consent record")
    consent.assert_allows_clone(commercial_use=commercial_use)
