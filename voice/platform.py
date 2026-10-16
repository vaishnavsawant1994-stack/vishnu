from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence

from voice.intelligence import (
    BUILTIN_VOICE_PACKS,
    PersonaStore,
    PronunciationLexicon,
    VoiceContext,
    VoiceDeviceCapabilities,
    VoiceDirector,
    VoicePersona,
    VoicePlan,
    VoicePreferences,
    VoiceQualityEvaluator,
    VoiceUtterance,
    chunk_text_for_voice,
    estimated_avatar_cues,
    segment_language_scripts,
)


@dataclass(frozen=True)
class VoiceSynthesisResult:
    audio: bytes
    plan: VoicePlan
    quality: dict
    pronunciation_hints: tuple[dict[str, str], ...]
    language_segments: tuple[dict[str, str], ...]
    avatar_cues: tuple[dict, ...]


class VoiceIntelligenceService:
    """Composition layer around Vishnu's existing ModelRouter voice authority.

    The service plans persona/expression/language first, then delegates actual
    synthesis/provider selection to the existing router. It never creates a second
    provider router or a second voice-cloning authority.
    """

    def __init__(self, model_router, *, data_dir: Path | None = None):
        self.model_router = model_router
        self.data_dir = Path(data_dir) if data_dir is not None else None
        custom_personas = {}
        if self.data_dir is not None:
            self.persona_store = PersonaStore(self.data_dir / "voice" / "personas.json")
            self.lexicon = PronunciationLexicon(self.data_dir / "voice" / "pronunciations.json")
            custom_personas = self.persona_store.list()
        else:
            self.persona_store = None
            self.lexicon = PronunciationLexicon()
        self.director = VoiceDirector(custom_personas)
        self.quality = VoiceQualityEvaluator()

    def refresh(self) -> None:
        custom = self.persona_store.list() if self.persona_store is not None else {}
        self.director = VoiceDirector(custom)

    def list_personas(self) -> list[dict]:
        return [asdict(persona) for _, persona in sorted(self.director.personas.items())]

    def put_persona(self, persona: VoicePersona) -> dict:
        if self.persona_store is None:
            raise RuntimeError("persistent voice persona storage is unavailable")
        if persona.id in BUILTIN_VOICE_PACKS:
            raise ValueError("built-in Vishnu voice packs cannot be overwritten")
        self.persona_store.put(persona)
        self.refresh()
        return asdict(persona)

    def delete_persona(self, persona_id: str) -> None:
        if self.persona_store is None:
            raise RuntimeError("persistent voice persona storage is unavailable")
        self.persona_store.delete(persona_id)
        self.refresh()

    def set_pronunciation(self, term: str, pronunciation: str) -> None:
        self.lexicon.set(term, pronunciation)

    def remove_pronunciation(self, term: str) -> None:
        self.lexicon.remove(term)

    def synthesize(
        self,
        text: str,
        *,
        persona_id: str | None = None,
        voice_profile_id: str | None = None,
        style: str | None = None,
        language: str | None = None,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
    ) -> VoiceSynthesisResult:
        plan = self.director.direct(
            persona_id=persona_id,
            manual_style=style,
            language=language,
            preferences=preferences,
            context=context,
        )
        governed_profile_id = voice_profile_id if voice_profile_id is not None else plan.voice_profile_id
        audio = self.model_router.synthesize(
            text,
            voice_profile_id=governed_profile_id,
            voice_style=plan.style,
        )
        quality = self.quality.inspect(audio)
        language_segments = tuple(asdict(item) for item in segment_language_scripts(text, default_language=plan.language))
        pronunciation_hints = tuple(self.lexicon.substitutions(text))
        avatar = tuple(
            asdict(item)
            for item in estimated_avatar_cues(
                text,
                quality.duration_seconds,
                expression=plan.avatar_expression,
            )
        )
        return VoiceSynthesisResult(
            audio=audio,
            plan=plan,
            quality=quality.public(),
            pronunciation_hints=pronunciation_hints,
            language_segments=language_segments,
            avatar_cues=avatar,
        )

    def synthesize_dialogue(
        self,
        utterances: Sequence[VoiceUtterance],
        *,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
    ) -> list[VoiceSynthesisResult]:
        results: list[VoiceSynthesisResult] = []
        for utterance, plan in self.director.plan_dialogue(
            utterances,
            preferences=preferences,
            context=context,
        ):
            results.append(
                self.synthesize(
                    utterance.text,
                    persona_id=plan.persona_id,
                    style=plan.style,
                    language=plan.language,
                    preferences=preferences,
                    context=context,
                )
            )
        return results

    def synthesize_stream(
        self,
        text: str,
        *,
        persona_id: str | None = None,
        style: str | None = None,
        language: str | None = None,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
        max_chars: int = 320,
        cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[VoiceSynthesisResult]:
        """Application-level chunk streaming with a cancellation/barge-in hook.

        This deliberately does not claim that the selected TTS or OpenVoice provider
        supports native streaming conversion. Each yielded item is a complete,
        independently synthesized chunk.
        """
        for chunk in chunk_text_for_voice(text, max_chars=max_chars):
            if cancelled is not None and cancelled():
                return
            result = self.synthesize(
                chunk,
                persona_id=persona_id,
                style=style,
                language=language,
                preferences=preferences,
                context=context,
            )
            if cancelled is not None and cancelled():
                return
            yield result

    def device_compatible(
        self,
        capabilities: VoiceDeviceCapabilities,
        *,
        persona_id: str | None = None,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
    ) -> bool:
        plan = self.director.direct(
            persona_id=persona_id,
            preferences=preferences,
            context=context,
        )
        return capabilities.supports(plan)

    def status(self) -> dict:
        return {
            "personas": len(self.director.personas),
            "builtin_voice_packs": list(BUILTIN_VOICE_PACKS),
            "custom_personas": max(0, len(self.director.personas) - len(BUILTIN_VOICE_PACKS)),
            "pronunciations": len(self.lexicon.items()),
            "application_streaming": True,
            "native_openvoice_streaming_claimed": False,
            "avatar_alignment": "estimated_without_provider_timestamps",
            "raw_transcripts_retained": False,
            "raw_audio_retained": False,
        }
