"""License-aware registry for optional speech models.

The registry is intentionally conservative: model use is denied in commercial
mode unless the model entry explicitly records that commercial use is allowed.
No model is registered automatically by importing this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelCapability(str, Enum):
    TTS = "tts"
    STT = "stt"
    VOICE_CLONING = "voice_cloning"
    VOICE_DESIGN = "voice_design"
    STREAMING = "streaming"
    EMOTION_CONTROL = "emotion_control"


class ModelPolicyError(RuntimeError):
    """Raised when a model cannot be used under the active policy."""


@dataclass(frozen=True, slots=True)
class VoiceModelSpec:
    model_id: str
    provider_id: str
    version: str
    capabilities: frozenset[ModelCapability]
    code_license: str | None = None
    weights_license: str | None = None
    commercial_allowed: bool = False
    redistribution_allowed: bool = False
    attribution_required: bool = False
    supported_languages: tuple[str, ...] = ()
    hardware: tuple[str, ...] = ()
    memory_requirement_mb: int | None = None
    download_size_mb: int | None = None
    quality_score: float | None = None
    latency_score: float | None = None
    verified_hash: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        for name, value in (
            ("memory_requirement_mb", self.memory_requirement_mb),
            ("download_size_mb", self.download_size_mb),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name, value in (("quality_score", self.quality_score), ("latency_score", self.latency_score)):
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


class VoiceModelRegistry:
    """In-memory policy registry for model metadata and licensing."""

    def __init__(self) -> None:
        self._models: dict[str, VoiceModelSpec] = {}

    def register(self, spec: VoiceModelSpec, *, replace: bool = False) -> None:
        if spec.model_id in self._models and not replace:
            raise ValueError(f"voice model already registered: {spec.model_id}")
        self._models[spec.model_id] = spec

    def unregister(self, model_id: str) -> None:
        self._models.pop(model_id, None)

    def get(self, model_id: str) -> VoiceModelSpec:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown voice model: {model_id}") from exc

    def list(self) -> tuple[VoiceModelSpec, ...]:
        return tuple(sorted(self._models.values(), key=lambda item: item.model_id))

    def assert_usable(
        self,
        model_id: str,
        *,
        capability: ModelCapability,
        commercial_mode: bool = True,
        redistribution_required: bool = False,
    ) -> VoiceModelSpec:
        spec = self.get(model_id)
        if not spec.supports(capability):
            raise ModelPolicyError(f"model {model_id!r} does not support {capability.value}")
        if commercial_mode and not spec.commercial_allowed:
            raise ModelPolicyError(f"model {model_id!r} is not approved for commercial use")
        if redistribution_required and not spec.redistribution_allowed:
            raise ModelPolicyError(f"model {model_id!r} is not approved for redistribution")
        return spec
