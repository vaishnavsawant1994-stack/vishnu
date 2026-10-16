"""Authoritative inventory for the isolated Vishnu Voice Lab.

This module is deliberately side-effect free. Importing it never starts audio
devices, providers, model downloads, or network activity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapabilityState(str, Enum):
    """Readiness of a voice capability in the Voice Lab."""

    IMPLEMENTED = "implemented"
    EXPERIMENTAL = "experimental"
    QUALIFICATION_REQUIRED = "qualification_required"
    GAP = "gap"


@dataclass(frozen=True, slots=True)
class VoiceCapability:
    """One independently trackable voice workstream."""

    capability_id: str
    category: str
    title: str
    state: CapabilityState
    evidence_paths: tuple[str, ...] = ()
    qualification_notes: tuple[str, ...] = ()
    production_authority: bool = False


_CAPABILITIES: tuple[VoiceCapability, ...] = (
    VoiceCapability(
        "microphone-capture",
        "conversation",
        "Microphone capture and audio device selection",
        CapabilityState.IMPLEMENTED,
        ("voice/full_duplex.py", "voice/realtime.py"),
    ),
    VoiceCapability(
        "adaptive-vad",
        "conversation",
        "Adaptive voice activity detection",
        CapabilityState.IMPLEMENTED,
        ("voice/full_duplex.py",),
    ),
    VoiceCapability(
        "semantic-endpointing",
        "conversation",
        "Semantic utterance endpointing",
        CapabilityState.IMPLEMENTED,
        ("voice/full_duplex.py",),
    ),
    VoiceCapability(
        "local-stt",
        "speech-recognition",
        "Local/offline speech recognition",
        CapabilityState.IMPLEMENTED,
        ("ingestion/", "voice/providers.py"),
        ("Exact local model, language, hardware, WER and CER still require qualification.",),
    ),
    VoiceCapability(
        "provider-stt",
        "speech-recognition",
        "Pluggable provider speech recognition",
        CapabilityState.IMPLEMENTED,
        ("voice/providers.py", "voice/voicestudio.py"),
        ("Each provider/model/language combination requires exact qualification.",),
    ),
    VoiceCapability(
        "canonical-runtime-bridge",
        "authority",
        "STT to CanonicalTurnRuntime to TTS authority bridge",
        CapabilityState.IMPLEMENTED,
        ("voice/realtime.py", "voice/full_duplex.py"),
        production_authority=True,
    ),
    VoiceCapability(
        "tts",
        "speech-synthesis",
        "Pluggable text-to-speech synthesis",
        CapabilityState.IMPLEMENTED,
        ("voice/providers.py", "voice/platform.py"),
        ("Acoustic quality depends on the exact provider, model, language and device.",),
    ),
    VoiceCapability(
        "streaming-synthesis",
        "speech-synthesis",
        "Application-level chunked/streaming synthesis",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py", "voice/platform.py"),
        ("Native provider incremental streaming is not implied.",),
    ),
    VoiceCapability(
        "barge-in",
        "conversation",
        "User interruption and barge-in cancellation",
        CapabilityState.IMPLEMENTED,
        ("voice/full_duplex.py", "voice/openai_realtime.py"),
    ),
    VoiceCapability(
        "stale-output-rejection",
        "conversation",
        "Stale reply and stale audio rejection after cancellation",
        CapabilityState.IMPLEMENTED,
        ("voice/full_duplex.py",),
    ),
    VoiceCapability(
        "personas-and-styles",
        "intelligence",
        "Voice personas, packs and bounded speaking styles",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py", "voice/preferences.py"),
    ),
    VoiceCapability(
        "bounded-affect-signals",
        "intelligence",
        "Bounded emotion/context signals for delivery style",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py",),
        ("Signals guide delivery only and do not claim feelings or consciousness.",),
    ),
    VoiceCapability(
        "multilingual-planning",
        "language",
        "Multilingual speech planning",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py",),
        ("Language quality requires exact provider/model qualification.",),
    ),
    VoiceCapability(
        "code-switch-planning",
        "language",
        "Script-aware code-switch planning",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py",),
        ("Code-switch retention and pronunciation require measured qualification.",),
    ),
    VoiceCapability(
        "pronunciation-lexicon",
        "language",
        "Owner-local pronunciation lexicon",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py",),
    ),
    VoiceCapability(
        "long-form-speech",
        "speech-synthesis",
        "Bounded long-form speech synthesis",
        CapabilityState.IMPLEMENTED,
        ("voice/platform.py",),
        ("Long-form coherence, latency and cancellation require provider qualification.",),
    ),
    VoiceCapability(
        "voice-profile-governance",
        "identity",
        "Voice profile enrollment, consent, provenance, revocation and deletion",
        CapabilityState.IMPLEMENTED,
        ("voice/platform.py", "voice/profile_archive.py"),
    ),
    VoiceCapability(
        "openvoice-conversion",
        "voice-conversion",
        "Governed OpenVoice tone-color/timbre conversion",
        CapabilityState.QUALIFICATION_REQUIRED,
        ("voice/conversion.py", "voice/platform.py"),
        ("Exact OpenVoice revision, checkpoints, source embedding and hardware require live qualification.",),
    ),
    VoiceCapability(
        "encrypted-profile-portability",
        "identity",
        "Encrypted voice-profile import/export",
        CapabilityState.IMPLEMENTED,
        ("voice/profile_archive.py",),
    ),
    VoiceCapability(
        "audio-quality-evaluator",
        "qualification",
        "Dependency-light WAV quality evaluation",
        CapabilityState.IMPLEMENTED,
        ("voice/intelligence.py",),
    ),
    VoiceCapability(
        "avatar-viseme-cues",
        "avatar",
        "Avatar expression and estimated viseme cues",
        CapabilityState.QUALIFICATION_REQUIRED,
        ("voice/intelligence.py",),
        ("Timing is estimated unless the selected provider supplies trustworthy timestamps.",),
    ),
    VoiceCapability(
        "trusted-device-output",
        "devices",
        "Trusted multi-device synthesized-audio routing",
        CapabilityState.IMPLEMENTED,
        ("voice/device_output.py", "voice/platform.py"),
    ),
    VoiceCapability(
        "openai-realtime-compatibility",
        "providers",
        "OpenAI Realtime speech-to-speech compatibility path",
        CapabilityState.EXPERIMENTAL,
        ("voice/openai_realtime.py", "voice/realtime_tools.py"),
        ("Compatibility/qualification only; it is not the canonical production voice authority.",),
    ),
    VoiceCapability(
        "voicestudio-http",
        "providers",
        "VoiceStudio HTTP STT/TTS/translation/discovery provider",
        CapabilityState.QUALIFICATION_REQUIRED,
        ("voice/voicestudio.py",),
        ("External service, exact model, GPU, acoustic quality and deployment licensing require qualification.",),
    ),
    VoiceCapability(
        "voicestudio-mcp-governance",
        "providers",
        "Governed VoiceStudio MCP capability discovery and execution",
        CapabilityState.IMPLEMENTED,
        ("voice/voicestudio.py", "capabilities/"),
    ),
    VoiceCapability(
        "media-transcription-intelligence",
        "content",
        "Local audio/video transcription and timestamp intelligence",
        CapabilityState.IMPLEMENTED,
        ("ingestion/",),
        ("Exact offline model quality remains model/language dependent.",),
    ),
    VoiceCapability(
        "sensorium-vision-voice",
        "sensorium",
        "Privacy-governed Vision plus Voice coordination",
        CapabilityState.IMPLEMENTED,
        ("sensorium/",),
    ),
    VoiceCapability(
        "environmental-audio",
        "sensorium",
        "Local-first bounded environmental audio awareness",
        CapabilityState.IMPLEMENTED,
        ("sensorium/",),
    ),
    VoiceCapability(
        "model-license-provenance",
        "governance",
        "Voice model license, provenance, integrity and local readiness governance",
        CapabilityState.IMPLEMENTED,
        ("voice/model_manager.py", "voice/platform.py"),
    ),
    VoiceCapability(
        "raw-audio-privacy",
        "governance",
        "Raw-audio retention and privacy controls",
        CapabilityState.IMPLEMENTED,
        ("voice/platform.py", "sensorium/"),
        ("Voice Lab experiments default to no raw-audio retention.",),
    ),
    VoiceCapability(
        "provider-failure-isolation",
        "reliability",
        "Provider failure isolation, fallback and clean runtime teardown",
        CapabilityState.IMPLEMENTED,
        ("voice/platform.py", "voice/voicestudio.py"),
    ),
    VoiceCapability(
        "telephony",
        "communications",
        "PSTN/SIP/telephony calling stack",
        CapabilityState.GAP,
        (),
        ("No confirmed PSTN, SIP or Twilio-style calling stack exists in the inspected voice architecture.",),
    ),
    VoiceCapability(
        "physical-device-acoustics",
        "qualification",
        "Real physical-device microphone, speaker and acoustic qualification",
        CapabilityState.QUALIFICATION_REQUIRED,
        (),
        ("Emulator/simulator evidence must not be treated as physical-device acoustic qualification.",),
    ),
    VoiceCapability(
        "provider-model-device-parity",
        "qualification",
        "Cross-provider/model/device acoustic and latency parity",
        CapabilityState.QUALIFICATION_REQUIRED,
        (),
        ("Requires evidence for each exact provider, model, language, device and route tuple.",),
    ),
)


def all_capabilities() -> tuple[VoiceCapability, ...]:
    """Return the complete immutable Voice Lab capability inventory."""

    return _CAPABILITIES


def find_capability(capability_id: str) -> VoiceCapability | None:
    """Return a capability by stable ID."""

    return next((item for item in _CAPABILITIES if item.capability_id == capability_id), None)


def gaps() -> tuple[VoiceCapability, ...]:
    """Return workstreams that are not implemented yet."""

    return tuple(item for item in _CAPABILITIES if item.state is CapabilityState.GAP)


def qualification_required() -> tuple[VoiceCapability, ...]:
    """Return capabilities that require real-world qualification before promotion."""

    return tuple(item for item in _CAPABILITIES if item.state is CapabilityState.QUALIFICATION_REQUIRED)
