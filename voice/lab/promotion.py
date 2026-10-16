"""Voice Lab release-readiness policy.

This module only evaluates evidence. It never changes production state.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CapabilityState, find_capability
from .evaluation import GateStatus, VoiceLabReport


@dataclass(frozen=True, slots=True)
class PromotionRequest:
    target_capability_ids: tuple[str, ...]
    manual_owner_approval: bool = False
    changes_canonical_authority: bool = False
    architecture_review_approved: bool = False
    targets_physical_device: bool = False
    uses_voice_profile_conversion: bool = False


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def _gate_passed(report: VoiceLabReport, gate_id: str) -> bool:
    gate = report.gate(gate_id)
    return gate is not None and gate.status is GateStatus.PASS


def evaluate_promotion(request: PromotionRequest, report: VoiceLabReport) -> PromotionDecision:
    """Fail closed unless required evidence and review are complete."""

    reasons: list[str] = []
    if not request.target_capability_ids:
        reasons.append("at least one target capability is required")

    for capability_id in request.target_capability_ids:
        capability = find_capability(capability_id)
        if capability is None:
            reasons.append(f"unknown capability: {capability_id}")
            continue
        if capability.state is CapabilityState.GAP:
            reasons.append(f"capability is still a gap: {capability_id}")

    if not report.is_qualified:
        if report.missing_gate_ids:
            reasons.append("required qualification evidence is missing")
        if report.non_passing_gate_ids:
            reasons.append("one or more required qualification gates did not pass")

    if not _gate_passed(report, "canonical-authority-preserved"):
        reasons.append("canonical STT -> CanonicalTurnRuntime -> TTS authority was not proven")
    if not _gate_passed(report, "model-license-provenance-integrity"):
        reasons.append("model license/provenance/integrity was not proven")
    if not _gate_passed(report, "no-raw-audio-retention"):
        reasons.append("privacy/no-raw-audio-retention was not proven")

    if request.uses_voice_profile_conversion and not _gate_passed(report, "consent-revocation-integrity"):
        reasons.append("voice profile conversion requires consent, revocation and integrity evidence")

    if request.targets_physical_device:
        if "physical-device-acoustics" not in request.target_capability_ids:
            reasons.append("physical-device promotion must target physical-device-acoustics qualification")
        if not _gate_passed(report, "physical-device-acoustics"):
            reasons.append("real physical-device acoustic evidence did not pass")

    if request.changes_canonical_authority and not request.architecture_review_approved:
        reasons.append("canonical authority changes require an explicit architecture/security review")
    if not request.manual_owner_approval:
        reasons.append("manual owner approval is required; Voice Lab never auto-promotes")

    return PromotionDecision(allowed=not reasons, reasons=tuple(dict.fromkeys(reasons)))
