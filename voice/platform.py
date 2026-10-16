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
from voice.preferences import VoicePreferenceStore
from voice.providers import TextToSpeechRequest

_AUTO_PROVIDER_RUNTIME = object()


@dataclass(frozen=True)
class VoiceSynthesisResult:
    audio: bytes
    plan: VoicePlan
    quality: dict
    pronunciation_hints: tuple[dict[str, str], ...]
    language_segments: tuple[dict[str, str], ...]
    avatar_cues: tuple[dict, ...]


class VoiceIntelligenceService:
    """Composition layer around Vishnu's existing voice authorities.

    Persona/expression/language planning stays here. An optional bounded provider
    runtime may supply source TTS audio, but Vishnu's existing ModelRouter and
    governed voice-conversion authority remain the fallback and cloning authority.
    """

    def __init__(
        self,
        model_router,
        *,
        data_dir: Path | None = None,
        provider_runtime=_AUTO_PROVIDER_RUNTIME,
    ):
        self.model_router = model_router
        if provider_runtime is _AUTO_PROVIDER_RUNTIME:
            from voice.voicestudio_runtime import active_voicestudio_runtime

            provider_runtime = active_voicestudio_runtime()
        self.provider_runtime = provider_runtime
        self.data_dir = Path(data_dir) if data_dir is not None else None
        custom_personas = {}
        if self.data_dir is not None:
            voice_dir = self.data_dir / "voice"
            self.persona_store = PersonaStore(voice_dir / "personas.json")
            self.lexicon = PronunciationLexicon(voice_dir / "pronunciations.json")
            self.preference_store = VoicePreferenceStore(voice_dir / "preferences.json")
            custom_personas = self.persona_store.list()
        else:
            self.persona_store = None
            self.lexicon = PronunciationLexicon()
            self.preference_store = None
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

    def preferences(self, *, owner_id: str = "owner") -> VoicePreferences:
        if self.preference_store is None:
            return VoicePreferences()
        return self.preference_store.get(owner_id)

    def set_preferences(
        self,
        preferences: VoicePreferences,
        *,
        owner_id: str = "owner",
    ) -> VoicePreferences:
        if self.preference_store is None:
            raise RuntimeError("persistent voice preference storage is unavailable")
        if preferences.persona_id and preferences.persona_id not in self.director.personas:
            raise ValueError("preferred persona does not exist")
        return self.preference_store.put(preferences, owner_id=owner_id)

    def set_pronunciation(self, term: str, pronunciation: str) -> None:
        self.lexicon.set(term, pronunciation)

    def remove_pronunciation(self, term: str) -> None:
        self.lexicon.remove(term)

    def list_voice_profiles(self, *, include_revoked: bool = True) -> list[dict]:
        registry = self._voice_profile_registry()
        if registry is None:
            return []
        return [
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "purpose": profile.purpose,
                "active": profile.active,
                "canonical": profile.canonical,
                "engine": profile.engine,
                "engine_version": profile.engine_version,
                "created_at": profile.created_at,
                "revoked_at": profile.revoked_at,
            }
            for profile in registry.list(include_revoked=include_revoked)
        ]

    def enroll_voice_profile(
        self,
        reference_wav: bytes,
        *,
        display_name: str,
        purpose: str,
        consent_attested: bool,
        profile_id: str | None = None,
    ) -> dict:
        registry = self._require_voice_profile_registry()
        profile = registry.enroll(
            reference_wav,
            display_name=display_name,
            purpose=purpose,
            consent_attested=consent_attested,
            profile_id=profile_id,
        )
        return {
            "profile_id": profile.profile_id,
            "display_name": profile.display_name,
            "purpose": profile.purpose,
            "active": profile.active,
            "canonical": profile.canonical,
            "engine": profile.engine,
            "engine_version": profile.engine_version,
            "created_at": profile.created_at,
            "revoked_at": profile.revoked_at,
        }

    def revoke_voice_profile(self, profile_id: str) -> dict:
        profile = self._require_voice_profile_registry().revoke(profile_id)
        return {
            "profile_id": profile.profile_id,
            "display_name": profile.display_name,
            "active": profile.active,
            "canonical": profile.canonical,
            "revoked_at": profile.revoked_at,
        }

    def delete_voice_profile(self, profile_id: str) -> None:
        self._require_voice_profile_registry().delete(profile_id)

    def _voice_profile_registry(self):
        conversion = getattr(self.model_router, "voice_conversion", None)
        return getattr(conversion, "registry", None)

    def _require_voice_profile_registry(self):
        registry = self._voice_profile_registry()
        if registry is None:
            raise RuntimeError("governed voice profile registry is unavailable")
        return registry

    def _provider_source_audio(self, text: str, *, language: str | None) -> bytes | None:
        runtime = self.provider_runtime
        if runtime is None:
            return None
        try:
            result = runtime.synthesize(
                TextToSpeechRequest(text=text, language=language),
            )
        except (RuntimeError, TimeoutError):
            return None
        return result.audio

    def _synthesize_audio(
        self,
        text: str,
        *,
        language: str | None,
        voice_profile_id: str | None,
        voice_style: str,
    ) -> bytes:
        source_audio = self._provider_source_audio(text, language=language)
        if source_audio is None:
            return self.model_router.synthesize(
                text,
                voice_profile_id=voice_profile_id,
                voice_style=voice_style,
            )

        conversion = getattr(self.model_router, "voice_conversion", None)
        if conversion is None:
            return source_audio
        return conversion.convert(
            source_audio,
            profile_id=voice_profile_id,
            style=voice_style,
        )

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
        selected_preferences = preferences if preferences is not None else self.preferences()
        plan = self.director.direct(
            persona_id=persona_id,
            manual_style=style,
            language=language,
            preferences=selected_preferences,
            context=context,
        )
        governed_profile_id = voice_profile_id if voice_profile_id is not None else plan.voice_profile_id
        conversion_style = "normal" if plan.style == "neutral" else plan.style
        audio = self._synthesize_audio(
            text,
            language=plan.language,
            voice_profile_id=governed_profile_id,
            voice_style=conversion_style,
        )
        quality = self.quality.inspect(audio)
        language_segments = tuple(
            asdict(item)
            for item in segment_language_scripts(text, default_language=plan.language)
        )
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
        selected_preferences = preferences if preferences is not None else self.preferences()
        results: list[VoiceSynthesisResult] = []
        for utterance, plan in self.director.plan_dialogue(
            utterances,
            preferences=selected_preferences,
            context=context,
        ):
            results.append(
                self.synthesize(
                    utterance.text,
                    persona_id=plan.persona_id,
                    style=plan.style,
                    language=plan.language,
                    preferences=selected_preferences,
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
        selected_preferences = preferences if preferences is not None else self.preferences()
        for chunk in chunk_text_for_voice(text, max_chars=max_chars):
            if cancelled is not None and cancelled():
                return
            result = self.synthesize(
                chunk,
                persona_id=persona_id,
                style=style,
                language=language,
                preferences=selected_preferences,
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
        selected_preferences = preferences if preferences is not None else self.preferences()
        plan = self.director.direct(
            persona_id=persona_id,
            preferences=selected_preferences,
            context=context,
        )
        return capabilities.supports(plan)

    def status(self) -> dict:
        profiles = self.list_voice_profiles(include_revoked=True)
        runtime = self.provider_runtime
        provider = getattr(runtime, "tts_provider", None) if runtime is not None else None
        runtime_state = getattr(getattr(runtime, "state", None), "value", None)
        return {
            "personas": len(self.director.personas),
            "builtin_voice_packs": list(BUILTIN_VOICE_PACKS),
            "custom_personas": max(0, len(self.director.personas) - len(BUILTIN_VOICE_PACKS)),
            "pronunciations": len(self.lexicon.items()),
            "voice_profiles": len(profiles),
            "active_voice_profiles": sum(bool(row["active"]) for row in profiles),
            "application_streaming": True,
            "native_openvoice_streaming_claimed": False,
            "external_provider_runtime": runtime is not None,
            "external_tts_provider": getattr(provider, "provider_id", None),
            "external_provider_state": runtime_state,
            "avatar_alignment": "estimated_without_provider_timestamps",
            "emotion_model": "bounded_context_signal_not_feeling",
            "raw_transcripts_retained": False,
            "raw_audio_retained": False,
        }
