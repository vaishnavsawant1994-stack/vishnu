"""Isolated lifecycle and routing layer for optional Vishnu voice inference.

VoiceRuntimeService is intentionally disabled by default and contains no heavy
model imports. It consumes providers registered by composition code and does
not replace Vishnu's existing approval, device, secret, intelligence, or audit
authorities.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from voice.chunking import chunk_speech_text
from voice.model_registry import ModelCapability, VoiceModelRegistry
from voice.providers import STTProvider, TTSProvider, SynthesisRequest, SynthesisResult, TranscriptionRequest, TranscriptionResult
from voice.scheduler import VoiceInferenceScheduler, VoicePriority


VOICE_RUNTIME_ENABLED_ENV = "VISHNU_VOICE_RUNTIME_ENABLED"
VOICE_COMMERCIAL_MODE_ENV = "VISHNU_VOICE_COMMERCIAL_MODE"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class VoiceRuntimeDisabledError(RuntimeError):
    """Raised when optional voice inference is requested while disabled."""


class VoiceProviderNotFoundError(LookupError):
    """Raised when a registered model has no matching runtime provider."""


AuditHook = Callable[[str, Mapping[str, Any]], None]


def _read_bool(env: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"{key} must be one of: 1/0, true/false, yes/no, on/off")


def voice_runtime_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return the explicit opt-in state. The safe default is disabled."""

    return _read_bool(os.environ if env is None else env, VOICE_RUNTIME_ENABLED_ENV, default=False)


class VoiceRuntimeService:
    """Optional, failure-isolated provider router for TTS and STT."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        commercial_mode: bool = True,
        registry: VoiceModelRegistry | None = None,
        scheduler: VoiceInferenceScheduler | None = None,
        audit_hook: AuditHook | None = None,
    ) -> None:
        self.enabled = enabled
        self.commercial_mode = commercial_mode
        self.registry = registry or VoiceModelRegistry()
        self.scheduler = scheduler or VoiceInferenceScheduler()
        self._audit_hook = audit_hook
        self._tts_providers: dict[str, TTSProvider] = {}
        self._stt_providers: dict[str, STTProvider] = {}
        self._started = False
        self._closed = False

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        registry: VoiceModelRegistry | None = None,
        scheduler: VoiceInferenceScheduler | None = None,
        audit_hook: AuditHook | None = None,
    ) -> "VoiceRuntimeService":
        values = os.environ if env is None else env
        return cls(
            enabled=_read_bool(values, VOICE_RUNTIME_ENABLED_ENV, default=False),
            commercial_mode=_read_bool(values, VOICE_COMMERCIAL_MODE_ENV, default=True),
            registry=registry,
            scheduler=scheduler,
            audit_hook=audit_hook,
        )

    def register_tts_provider(self, provider: TTSProvider, *, replace: bool = False) -> None:
        self._register_provider(self._tts_providers, provider.provider_id, provider, replace=replace)

    def register_stt_provider(self, provider: STTProvider, *, replace: bool = False) -> None:
        self._register_provider(self._stt_providers, provider.provider_id, provider, replace=replace)

    async def start(self) -> None:
        self._ensure_enabled()
        if self._closed:
            raise RuntimeError("voice runtime is closed")
        if self._started:
            return
        await self.scheduler.start()
        self._started = True
        self._audit("voice.runtime_started", {})

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started:
            await self.scheduler.close()
            self._started = False
        self._audit("voice.runtime_stopped", {})

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        priority: VoicePriority = VoicePriority.AGENT_RESPONSE,
    ) -> SynthesisResult:
        self._ensure_enabled()
        spec = self.registry.assert_usable(
            request.model_id,
            capability=ModelCapability.TTS,
            commercial_mode=self.commercial_mode,
        )
        provider = self._tts_providers.get(spec.provider_id)
        if provider is None:
            raise VoiceProviderNotFoundError(f"TTS provider is not registered: {spec.provider_id}")
        await self.start()
        self._audit(
            "voice.synthesis_requested",
            {
                "model_id": request.model_id,
                "provider_id": spec.provider_id,
                "profile_id": request.profile_id,
                "language": request.language,
                "priority": priority.name.lower(),
            },
        )

        async def operation() -> SynthesisResult:
            try:
                result = await provider.synthesize(request)
            except Exception:
                self._audit(
                    "voice.synthesis_failed",
                    {"model_id": request.model_id, "provider_id": spec.provider_id},
                )
                raise
            self._audit(
                "voice.synthesis_completed",
                {
                    "model_id": request.model_id,
                    "provider_id": spec.provider_id,
                    "sample_rate_hz": result.sample_rate_hz,
                    "mime_type": result.mime_type,
                },
            )
            return result

        return await self.scheduler.submit(priority, operation)

    async def synthesize_long_form(
        self,
        request: SynthesisRequest,
        *,
        max_chunk_characters: int = 1_500,
    ) -> tuple[SynthesisResult, ...]:
        """Generate long text as bounded chunks through the same governed route.

        Encoded audio is intentionally returned per chunk. Audio decoding,
        crossfade, and re-encoding belong to the provider/audio pipeline rather
        than this model-agnostic routing layer.
        """

        chunks = chunk_speech_text(request.text, max_characters=max_chunk_characters)
        self._audit(
            "voice.long_form_requested",
            {"model_id": request.model_id, "chunk_count": len(chunks)},
        )
        results: list[SynthesisResult] = []
        for index, chunk in enumerate(chunks):
            intent = dict(request.intent)
            intent["long_form_chunk_index"] = index
            intent["long_form_chunk_count"] = len(chunks)
            results.append(
                await self.synthesize(
                    SynthesisRequest(
                        text=chunk,
                        model_id=request.model_id,
                        profile_id=request.profile_id,
                        language=request.language,
                        intent=intent,
                    ),
                    priority=VoicePriority.LONG_FORM,
                )
            )
        return tuple(results)

    async def transcribe(
        self,
        request: TranscriptionRequest,
        *,
        priority: VoicePriority = VoicePriority.LIVE_CONVERSATION,
    ) -> TranscriptionResult:
        self._ensure_enabled()
        spec = self.registry.assert_usable(
            request.model_id,
            capability=ModelCapability.STT,
            commercial_mode=self.commercial_mode,
        )
        provider = self._stt_providers.get(spec.provider_id)
        if provider is None:
            raise VoiceProviderNotFoundError(f"STT provider is not registered: {spec.provider_id}")
        await self.start()
        self._audit(
            "voice.transcription_requested",
            {
                "model_id": request.model_id,
                "provider_id": spec.provider_id,
                "language": request.language,
                "mime_type": request.mime_type,
                "priority": priority.name.lower(),
            },
        )

        async def operation() -> TranscriptionResult:
            try:
                result = await provider.transcribe(request)
            except Exception:
                self._audit(
                    "voice.transcription_failed",
                    {"model_id": request.model_id, "provider_id": spec.provider_id},
                )
                raise
            self._audit(
                "voice.transcription_completed",
                {
                    "model_id": request.model_id,
                    "provider_id": spec.provider_id,
                    "language": result.language,
                },
            )
            return result

        return await self.scheduler.submit(priority, operation)

    def health(self) -> dict[str, Any]:
        """Return non-sensitive state suitable for owner diagnostics."""

        return {
            "enabled": self.enabled,
            "started": self._started,
            "closed": self._closed,
            "commercial_mode": self.commercial_mode,
            "scheduler_running": self.scheduler.running,
            "scheduler_pending": self.scheduler.pending,
            "tts_providers": sorted(self._tts_providers),
            "stt_providers": sorted(self._stt_providers),
            "models": [spec.model_id for spec in self.registry.list()],
        }

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise VoiceRuntimeDisabledError(
                f"voice runtime is disabled; set {VOICE_RUNTIME_ENABLED_ENV}=true to opt in"
            )

    @staticmethod
    def _register_provider(
        providers: dict[str, Any],
        provider_id: str,
        provider: Any,
        *,
        replace: bool,
    ) -> None:
        normalized = provider_id.strip()
        if not normalized:
            raise ValueError("provider_id must not be empty")
        if normalized in providers and not replace:
            raise ValueError(f"voice provider already registered: {normalized}")
        providers[normalized] = provider

    def _audit(self, event: str, metadata: Mapping[str, Any]) -> None:
        if self._audit_hook is not None:
            self._audit_hook(event, metadata)
