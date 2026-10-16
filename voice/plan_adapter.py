"""Bridge existing Voice Intelligence plans into the provider runtime.

Voice Intelligence remains the authority for persona, style, language and
device-aware planning. This adapter only translates a VoicePlan into the
model-agnostic request consumed by VoiceRuntimeService.
"""

from __future__ import annotations

from voice.intelligence import VoicePlan
from voice.providers import SynthesisRequest
from voice.scheduler import VoicePriority


def synthesis_request_from_plan(*, text: str, model_id: str, plan: VoicePlan) -> SynthesisRequest:
    return SynthesisRequest(
        text=text,
        model_id=model_id,
        profile_id=plan.voice_profile_id,
        language=plan.language,
        intent={
            "persona_id": plan.persona_id,
            "style": plan.style,
            "style_source": plan.style_source,
            "speaking_rate": plan.speaking_rate,
            "pitch": plan.pitch,
            "energy": plan.energy,
            "formality": plan.formality,
            "avatar_expression": plan.avatar_expression,
            "character_id": plan.character_id,
            "offline_required": plan.route.offline_required,
            "private_required": plan.route.private_required,
            "streaming_preferred": plan.route.streaming_preferred,
            "voice_conversion_requested": plan.route.voice_conversion_requested,
        },
    )


def priority_from_plan(plan: VoicePlan) -> VoicePriority:
    """Map an existing intelligence plan to runtime scheduling priority."""

    if plan.style == "urgent":
        return VoicePriority.EMERGENCY
    if plan.route.streaming_preferred:
        return VoicePriority.LIVE_CONVERSATION
    return VoicePriority.AGENT_RESPONSE
