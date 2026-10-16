"""Stable provider contracts for Vishnu voice input and output.

This module deliberately contains no model imports. Providers are registered at
runtime so heavy or optional speech dependencies cannot affect Vishnu startup.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Model-agnostic request for text-to-speech synthesis."""

    text: str
    model_id: str
    profile_id: str | None = None
    language: str | None = None
    intent: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Normalized TTS output returned by every provider."""

    audio: bytes
    sample_rate_hz: int
    mime_type: str = "audio/wav"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    """Model-agnostic request for speech-to-text transcription."""

    audio: bytes
    model_id: str
    language: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Normalized STT output returned by every provider."""

    text: str
    language: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class TTSProvider(Protocol):
    """Minimal contract implemented by every text-to-speech provider."""

    @property
    def provider_id(self) -> str: ...

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult: ...


@runtime_checkable
class STTProvider(Protocol):
    """Minimal contract implemented by every speech-to-text provider."""

    @property
    def provider_id(self) -> str: ...

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult: ...


TTSCallable = Callable[[SynthesisRequest], SynthesisResult | Awaitable[SynthesisResult]]
STTCallable = Callable[[TranscriptionRequest], TranscriptionResult | Awaitable[TranscriptionResult]]


@dataclass(slots=True)
class CallableTTSProvider:
    """Adapter for bridging an existing Vishnu TTS callable into the provider API."""

    provider_id: str
    function: TTSCallable

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        result = self.function(request)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, SynthesisResult):
            raise TypeError("TTS provider callable must return SynthesisResult")
        return result


@dataclass(slots=True)
class CallableSTTProvider:
    """Adapter for bridging an existing Vishnu STT callable into the provider API."""

    provider_id: str
    function: STTCallable

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        result = self.function(request)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, TranscriptionResult):
            raise TypeError("STT provider callable must return TranscriptionResult")
        return result
