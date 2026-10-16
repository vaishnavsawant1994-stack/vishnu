from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    healthy: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SpeechToTextRequest:
    audio: bytes
    sample_rate_hz: int = 16_000
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.audio:
            raise ValueError("audio must not be empty")
        if self.sample_rate_hz < 1:
            raise ValueError("sample_rate_hz must be >= 1")


@dataclass(frozen=True, slots=True)
class SpeechToTextResult:
    text: str
    language: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TextToSpeechRequest:
    text: str
    voice: str | None = None
    language: str | None = None
    sample_rate_hz: int | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if self.sample_rate_hz is not None and self.sample_rate_hz < 1:
            raise ValueError("sample_rate_hz must be >= 1")


@dataclass(frozen=True, slots=True)
class TextToSpeechResult:
    audio: bytes
    sample_rate_hz: int
    mime_type: str = "audio/wav"

    def __post_init__(self) -> None:
        if not self.audio:
            raise ValueError("audio must not be empty")
        if self.sample_rate_hz < 1:
            raise ValueError("sample_rate_hz must be >= 1")


@runtime_checkable
class SpeechToTextProvider(Protocol):
    provider_id: str

    def health(self) -> ProviderHealth: ...

    def capabilities(self) -> Mapping[str, object]: ...

    def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResult: ...


@runtime_checkable
class TextToSpeechProvider(Protocol):
    provider_id: str

    def health(self) -> ProviderHealth: ...

    def capabilities(self) -> Mapping[str, object]: ...

    def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult: ...
