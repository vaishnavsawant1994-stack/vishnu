from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sensorium.audio_intelligence import EnvironmentalAudioIntelligence
from voice.providers import SpeechToTextResult


@dataclass(frozen=True, slots=True)
class SpeechIntent:
    """Bounded speech observation passed into Vishnu's canonical turn runtime.

    It carries the transcript and local acoustic context but grants no tool,
    approval, device, or execution authority.
    """

    text: str
    source: str = "microphone"
    device_id: str | None = None
    language: str | None = None
    confidence: float | None = None
    captured_at: float = field(default_factory=time.time)
    audio_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("speech intent text must not be empty")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("speech intent confidence must be between 0 and 1")

    @property
    def execution_authority(self) -> bool:
        return False


class SpeechIntentBridge:
    """Convert STT output plus Sensorium audio features into a safe intent."""

    def __init__(self, *, events=None, audio_intelligence=None) -> None:
        self.events = events
        self.audio_intelligence = audio_intelligence or EnvironmentalAudioIntelligence(events=events)

    def from_transcription(
        self,
        transcription: SpeechToTextResult | str,
        *,
        source: str = "microphone",
        device_id: str | None = None,
        audio_features: dict[str, Any] | None = None,
    ) -> SpeechIntent:
        if isinstance(transcription, SpeechToTextResult):
            text = transcription.text
            language = transcription.language
            confidence = transcription.confidence
        else:
            text = str(transcription)
            language = None
            confidence = None

        context = {}
        if audio_features is not None:
            context = self.audio_intelligence.normalize(audio_features, source=source)

        intent = SpeechIntent(
            text=text.strip(),
            source=str(source or "microphone")[:160],
            device_id=(str(device_id)[:160] if device_id else None),
            language=language,
            confidence=confidence,
            audio_context=context,
        )
        if self.events is not None:
            self.events.emit(
                "voice.speech_intent",
                source=intent.source,
                device_id=intent.device_id,
                language=intent.language,
                confidence=intent.confidence,
                text_chars=len(intent.text),
                audio_label=context.get("label") if context else None,
                raw_audio_retained=False,
                execution_authority=False,
            )
        return intent
