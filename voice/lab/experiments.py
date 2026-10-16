"""Deterministic, privacy-first Voice Lab experiment specifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .evaluation import BASELINE_REQUIRED_GATES


def _normalized_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class VoiceExperimentSpec:
    """An immutable test definition for one exact voice route.

    Fixture references are identifiers/paths, not embedded audio bytes. Raw voice
    persistence is disabled by default and cannot be silently enabled.
    """

    title: str
    provider: str
    model: str
    device: str
    language: str
    route: str = "canonical-stt-runtime-tts"
    style: str = "neutral"
    fixture_refs: tuple[str, ...] = ()
    required_gate_ids: tuple[str, ...] = BASELINE_REQUIRED_GATES
    retain_raw_audio: bool = False
    raw_audio_retention_seconds: int = 0
    contains_voice_biometrics: bool = False
    consent_reference: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("experiment title is required")
        for label, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("device", self.device),
            ("language", self.language),
            ("route", self.route),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        if len({key for key, _ in self.metadata}) != len(self.metadata):
            raise ValueError("metadata keys must be unique")
        if any(not key.strip() for key, _ in self.metadata):
            raise ValueError("metadata keys cannot be empty")
        if self.raw_audio_retention_seconds < 0:
            raise ValueError("raw audio retention cannot be negative")
        if not self.retain_raw_audio and self.raw_audio_retention_seconds != 0:
            raise ValueError("raw audio retention seconds must be zero when retention is disabled")
        if self.retain_raw_audio:
            if self.raw_audio_retention_seconds <= 0:
                raise ValueError("bounded retention seconds are required when raw audio retention is enabled")
            if self.raw_audio_retention_seconds > 3600:
                raise ValueError("Voice Lab raw audio retention is bounded to at most one hour")
            if not self.consent_reference:
                raise ValueError("explicit consent reference is required to retain raw voice audio")
        if self.contains_voice_biometrics and not self.consent_reference:
            raise ValueError("voice-biometric experiments require an explicit consent reference")

    @property
    def experiment_id(self) -> str:
        data = asdict(self)
        digest = hashlib.sha256(_normalized_json(data).encode("utf-8")).hexdigest()
        return f"voice-lab-{digest[:20]}"
