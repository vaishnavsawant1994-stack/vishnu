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
    """An immutable test definition for one exact voice route."""

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
        if len(set(self.required_gate_ids)) != len(self.required_gate_ids):
            raise ValueError("required qualification gate IDs must be unique")
        if any(not gate_id.strip() for gate_id in self.required_gate_ids):
            raise ValueError("required qualification gate IDs cannot be empty")
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
        digest = hashlib.sha256(_normalized_json(asdict(self)).encode("utf-8")).hexdigest()
        return f"voice-lab-{digest[:20]}"

    @property
    def baseline_key(self) -> str:
        """Stable comparison family across provider/model/config changes."""
        family = {
            "title": self.title,
            "device": self.device,
            "language": self.language,
            "route": self.route,
            "fixture_refs": self.fixture_refs,
            "required_gate_ids": self.required_gate_ids,
        }
        digest = hashlib.sha256(_normalized_json(family).encode("utf-8")).hexdigest()
        return f"voice-baseline-{digest[:20]}"
