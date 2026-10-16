from __future__ import annotations

from dataclasses import asdict, dataclass, field
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
import time
from typing import Callable, Final, Iterable, Iterator, Mapping, Sequence
import wave


SUPPORTED_VOICE_STYLES: Final[tuple[str, ...]] = (
    "neutral",
    "warm",
    "cheerful",
    "calm",
    "empathetic",
    "serious",
    "urgent",
    "storytelling",
)

_EMOTION_TO_STYLE: Final[dict[str, str]] = {
    "angry": "calm",
    "anger": "calm",
    "anxious": "calm",
    "concerned": "empathetic",
    "confused": "empathetic",
    "excited": "cheerful",
    "frustrated": "empathetic",
    "happy": "cheerful",
    "sad": "empathetic",
    "stressed": "calm",
}

_INTENT_TO_STYLE: Final[dict[str, str]] = {
    "bedtime": "calm",
    "customer_support": "empathetic",
    "emergency": "urgent",
    "meditation": "calm",
    "professional": "serious",
    "story": "storytelling",
    "storytelling": "storytelling",
    "teaching": "warm",
}

_STYLE_TO_AVATAR: Final[dict[str, str]] = {
    "neutral": "neutral",
    "warm": "friendly",
    "cheerful": "happy",
    "calm": "calm",
    "empathetic": "concerned",
    "serious": "serious",
    "urgent": "alert",
    "storytelling": "expressive",
}


@dataclass(frozen=True)
class VoiceProfile:
    """Provider-agnostic capture/playback behavior used by the live voice runtime."""

    personality: str = "calm, concise, warm and direct"
    speaking_rate: float = 1.0
    min_endpoint_ms: int = 420
    max_endpoint_ms: int = 1100
    noise_multiplier: float = 2.4
    min_voice_threshold: float = 0.008
    max_utterance_seconds: float = 45.0

    def __post_init__(self):
        if not 0.65 <= float(self.speaking_rate) <= 1.5:
            raise ValueError("speaking_rate must be between 0.65 and 1.5")
        if self.min_endpoint_ms < 150 or self.max_endpoint_ms < self.min_endpoint_ms:
            raise ValueError("invalid endpoint timing")
        if self.noise_multiplier < 1.1:
            raise ValueError("noise_multiplier must be >= 1.1")


@dataclass(frozen=True)
class VoicePersona:
    """A reusable Vishnu speaking identity, separate from provider/model choice.

    `voice_profile_id` may reference an enrolled governed conversion profile. Raw
    reference-audio paths and URLs intentionally do not belong in this object.
    """

    id: str
    name: str
    role: str = "assistant"
    voice_profile_id: str | None = None
    language: str = "en"
    style: str = "neutral"
    speaking_rate: float = 1.0
    pitch: float = 0.0
    energy: float = 1.0
    formality: float = 0.5
    avatar_expression: str = "neutral"
    character_id: str | None = None

    def __post_init__(self):
        _validate_identifier(self.id, "persona id")
        if not str(self.name).strip() or len(self.name) > 80:
            raise ValueError("persona name must contain 1-80 characters")
        if self.voice_profile_id is not None:
            _validate_identifier(self.voice_profile_id, "voice profile id")
        normalize_voice_style(self.style)
        _validate_language(self.language)
        if not 0.65 <= float(self.speaking_rate) <= 1.5:
            raise ValueError("persona speaking_rate must be between 0.65 and 1.5")
        if not -1.0 <= float(self.pitch) <= 1.0:
            raise ValueError("persona pitch must be between -1 and 1")
        if not 0.0 <= float(self.energy) <= 2.0:
            raise ValueError("persona energy must be between 0 and 2")
        if not 0.0 <= float(self.formality) <= 1.0:
            raise ValueError("persona formality must be between 0 and 1")


BUILTIN_VOICE_PACKS: Final[dict[str, VoicePersona]] = {
    "vishnu_original": VoicePersona("vishnu_original", "Vishnu Original"),
    "vishnu_warm": VoicePersona("vishnu_warm", "Vishnu Warm", style="warm", energy=1.05, avatar_expression="friendly"),
    "vishnu_professional": VoicePersona("vishnu_professional", "Vishnu Professional", style="serious", formality=0.9, avatar_expression="serious"),
    "vishnu_storyteller": VoicePersona("vishnu_storyteller", "Vishnu Storyteller", style="storytelling", speaking_rate=0.92, energy=1.15, avatar_expression="expressive"),
    "vishnu_calm": VoicePersona("vishnu_calm", "Vishnu Calm", style="calm", speaking_rate=0.9, energy=0.8, avatar_expression="calm"),
    "vishnu_energetic": VoicePersona("vishnu_energetic", "Vishnu Energetic", style="cheerful", speaking_rate=1.08, energy=1.25, avatar_expression="happy"),
}


@dataclass(frozen=True)
class VoicePreferences:
    persona_id: str | None = None
    language: str | None = None
    style: str | None = None
    speaking_rate: float | None = None
    expression_intensity: float = 1.0
    formality: float | None = None

    def __post_init__(self):
        if self.persona_id:
            _validate_identifier(self.persona_id, "persona id")
        if self.language:
            _validate_language(self.language)
        if self.style:
            normalize_voice_style(self.style)
        if self.speaking_rate is not None and not 0.65 <= float(self.speaking_rate) <= 1.5:
            raise ValueError("preferred speaking_rate must be between 0.65 and 1.5")
        if not 0.0 <= float(self.expression_intensity) <= 2.0:
            raise ValueError("expression_intensity must be between 0 and 2")
        if self.formality is not None and not 0.0 <= float(self.formality) <= 1.0:
            raise ValueError("formality must be between 0 and 1")


@dataclass(frozen=True)
class VoiceContext:
    intent: str | None = None
    emotion_label: str | None = None
    language: str | None = None
    urgent: bool = False
    audience: str | None = None
    character_id: str | None = None
    device_class: str | None = None
    privacy_required: bool = False
    offline: bool = False


@dataclass(frozen=True)
class VoiceStyleDecision:
    style: str = "neutral"
    source: str = "default"
    emotion_label: str | None = None


@dataclass(frozen=True)
class VoiceRouteRequirements:
    language: str
    offline_required: bool = False
    private_required: bool = False
    streaming_preferred: bool = True
    voice_conversion_requested: bool = False


@dataclass(frozen=True)
class VoicePlan:
    persona_id: str
    voice_profile_id: str | None
    style: str
    style_source: str
    language: str
    speaking_rate: float
    pitch: float
    energy: float
    formality: float
    avatar_expression: str
    character_id: str | None
    route: VoiceRouteRequirements

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VoiceUtterance:
    text: str
    speaker: str = "vishnu_original"
    language: str | None = None
    style: str | None = None

    def __post_init__(self):
        if not str(self.text).strip():
            raise ValueError("utterance text cannot be empty")
        if len(self.text) > 20_000:
            raise ValueError("utterance text is too large")
        _validate_identifier(self.speaker, "speaker persona id")
        if self.language:
            _validate_language(self.language)
        if self.style:
            normalize_voice_style(self.style)


@dataclass(frozen=True)
class LanguageSegment:
    text: str
    language_hint: str


@dataclass(frozen=True)
class VoiceDeviceCapabilities:
    device_class: str = "generic"
    offline_tts: bool = False
    streaming_tts: bool = False
    local_voice_conversion: bool = False
    languages: tuple[str, ...] = ()

    def supports(self, plan: VoicePlan) -> bool:
        base = plan.language.split("-", 1)[0].lower()
        languages = {item.split("-", 1)[0].lower() for item in self.languages}
        if languages and base not in languages:
            return False
        if plan.route.offline_required and not self.offline_tts:
            return False
        if plan.route.voice_conversion_requested and plan.route.offline_required and not self.local_voice_conversion:
            return False
        return True


@dataclass(frozen=True)
class AudioQualityReport:
    valid_wav: bool
    duration_seconds: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    peak: float = 0.0
    rms: float = 0.0
    silence_ratio: float = 1.0
    clipping_ratio: float = 0.0
    acceptable: bool = False
    reasons: tuple[str, ...] = ()

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AvatarCue:
    start_seconds: float
    end_seconds: float
    viseme: str
    expression: str = "neutral"
    alignment: str = "estimated"


class VoiceDirector:
    """Deterministic policy layer for persona, expression, language and routing."""

    def __init__(self, personas: Mapping[str, VoicePersona] | None = None):
        self.personas = dict(BUILTIN_VOICE_PACKS)
        self.personas.update(dict(personas or {}))

    def choose_style(
        self,
        *,
        manual_style: str | None = None,
        emotion_label: str | None = None,
        intent: str | None = None,
    ) -> VoiceStyleDecision:
        return choose_voice_style(
            manual_style=manual_style,
            emotion_label=emotion_label,
            intent=intent,
        )

    def direct(
        self,
        *,
        persona_id: str | None = None,
        manual_style: str | None = None,
        language: str | None = None,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
    ) -> VoicePlan:
        preferences = preferences or VoicePreferences()
        context = context or VoiceContext()
        selected_id = persona_id or preferences.persona_id or "vishnu_original"
        persona = self.personas.get(selected_id)
        if persona is None:
            raise ValueError(f"Unknown voice persona: {selected_id}")
        explicit_or_preferred_style = manual_style if manual_style is not None else preferences.style
        decision = self.choose_style(
            manual_style=explicit_or_preferred_style,
            emotion_label=context.emotion_label,
            intent=context.intent,
        )
        if decision.source == "default" and persona.style != "neutral":
            decision = VoiceStyleDecision(style=persona.style, source="persona")
        selected_language = language or preferences.language or context.language or persona.language
        _validate_language(selected_language)
        rate = preferences.speaking_rate if preferences.speaking_rate is not None else persona.speaking_rate
        formality = preferences.formality if preferences.formality is not None else persona.formality
        intensity = preferences.expression_intensity
        energy = max(0.0, min(2.0, 1.0 + (persona.energy - 1.0) * intensity))
        style = "urgent" if context.urgent and manual_style is None and preferences.style is None else decision.style
        style_source = "context" if style == "urgent" and style != decision.style else decision.source
        avatar_expression = _STYLE_TO_AVATAR.get(style, persona.avatar_expression)
        return VoicePlan(
            persona_id=persona.id,
            voice_profile_id=persona.voice_profile_id,
            style=style,
            style_source=style_source,
            language=selected_language,
            speaking_rate=float(rate),
            pitch=float(persona.pitch),
            energy=energy,
            formality=float(formality),
            avatar_expression=avatar_expression,
            character_id=context.character_id or persona.character_id,
            route=VoiceRouteRequirements(
                language=selected_language,
                offline_required=bool(context.offline),
                private_required=bool(context.privacy_required),
                streaming_preferred=True,
                voice_conversion_requested=bool(persona.voice_profile_id),
            ),
        )

    def plan_dialogue(
        self,
        utterances: Sequence[VoiceUtterance],
        *,
        preferences: VoicePreferences | None = None,
        context: VoiceContext | None = None,
    ) -> list[tuple[VoiceUtterance, VoicePlan]]:
        result: list[tuple[VoiceUtterance, VoicePlan]] = []
        for utterance in utterances:
            result.append(
                (
                    utterance,
                    self.direct(
                        persona_id=utterance.speaker,
                        manual_style=utterance.style,
                        language=utterance.language,
                        preferences=preferences,
                        context=context,
                    ),
                )
            )
        return result


class PersonaStore:
    """Atomic local JSON store for owner-created persona configuration."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def list(self) -> dict[str, VoicePersona]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("voice persona store is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("voice persona store is invalid")
        return {key: VoicePersona(**value) for key, value in payload.items() if isinstance(value, dict)}

    def put(self, persona: VoicePersona) -> None:
        rows = self.list()
        rows[persona.id] = persona
        self._write(rows)

    def delete(self, persona_id: str) -> None:
        if persona_id in BUILTIN_VOICE_PACKS:
            raise ValueError("built-in Vishnu voice packs cannot be deleted")
        rows = self.list()
        rows.pop(persona_id, None)
        self._write(rows)

    def _write(self, rows: Mapping[str, VoicePersona]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({key: asdict(value) for key, value in sorted(rows.items())}, indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class PronunciationLexicon:
    """Local pronunciation preferences without retaining transcripts or audio."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self._rows: dict[str, str] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("pronunciation lexicon is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("pronunciation lexicon is invalid")
        for term, pronunciation in payload.items():
            self._validate(term, pronunciation)
            self._rows[str(term)] = str(pronunciation)

    @staticmethod
    def _validate(term: str, pronunciation: str) -> None:
        if not str(term).strip() or len(str(term)) > 120:
            raise ValueError("pronunciation term must contain 1-120 characters")
        if not str(pronunciation).strip() or len(str(pronunciation)) > 240:
            raise ValueError("pronunciation value must contain 1-240 characters")
        if "\n" in str(term) or "\n" in str(pronunciation):
            raise ValueError("pronunciation entries must be single-line")

    def set(self, term: str, pronunciation: str) -> None:
        self._validate(term, pronunciation)
        self._rows[str(term)] = str(pronunciation)
        self._persist()

    def remove(self, term: str) -> None:
        self._rows.pop(str(term), None)
        self._persist()

    def items(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._rows.items(), key=lambda item: item[0].casefold()))

    def substitutions(self, text: str) -> list[dict[str, str]]:
        """Return provider-agnostic hints; never mutate semantic text automatically."""
        result = []
        for term, pronunciation in self.items():
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE):
                result.append({"term": term, "pronunciation": pronunciation})
        return result

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(self._rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class VoiceQualityEvaluator:
    """Dependency-light WAV integrity/level checks. It never performs speech recognition."""

    def inspect(self, audio: bytes) -> AudioQualityReport:
        try:
            with wave.open(io.BytesIO(audio), "rb") as reader:
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                sample_rate = reader.getframerate()
                frame_count = reader.getnframes()
                frames = reader.readframes(frame_count)
        except (wave.Error, EOFError):
            return AudioQualityReport(valid_wav=False, reasons=("invalid_wav",))
        if sample_width not in {1, 2, 4} or channels < 1 or sample_rate < 1 or frame_count < 1:
            return AudioQualityReport(valid_wav=False, reasons=("unsupported_wav",))
        samples = _pcm_samples(frames, sample_width)
        if not samples:
            return AudioQualityReport(valid_wav=False, reasons=("empty_audio",))
        scale = float((1 << (8 * sample_width - 1)) - 1) if sample_width > 1 else 127.0
        normalized = [abs(value) / scale for value in samples]
        peak = max(normalized)
        rms = math.sqrt(sum(value * value for value in normalized) / len(normalized))
        silence_ratio = sum(value < 0.01 for value in normalized) / len(normalized)
        clipping_ratio = sum(value >= 0.995 for value in normalized) / len(normalized)
        duration = frame_count / float(sample_rate)
        reasons: list[str] = []
        if duration < 0.05:
            reasons.append("too_short")
        if silence_ratio > 0.98:
            reasons.append("mostly_silence")
        if clipping_ratio > 0.01:
            reasons.append("clipping")
        return AudioQualityReport(
            valid_wav=True,
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=channels,
            peak=peak,
            rms=rms,
            silence_ratio=silence_ratio,
            clipping_ratio=clipping_ratio,
            acceptable=not reasons,
            reasons=tuple(reasons),
        )


class AdaptiveVoiceActivity:
    """Small deterministic VAD helper used by the provider-agnostic fallback path."""

    def __init__(self, profile: VoiceProfile, *, initial_noise: float = 0.002):
        self.profile = profile
        self.noise_floor = max(0.0001, float(initial_noise))
        self._alpha_idle = 0.06
        self._alpha_speech = 0.005

    @property
    def threshold(self) -> float:
        return max(float(self.profile.min_voice_threshold), self.noise_floor * float(self.profile.noise_multiplier))

    def observe(self, rms: float, *, speech_active: bool) -> bool:
        rms = max(0.0, float(rms))
        current_threshold = self.threshold
        is_voice = rms >= current_threshold
        alpha = self._alpha_speech if speech_active or is_voice else self._alpha_idle
        sample = min(rms, current_threshold * 1.25) if is_voice else rms
        self.noise_floor = (1.0 - alpha) * self.noise_floor + alpha * sample
        return is_voice


class SemanticEndpointDetector:
    """Energy/timing endpoint policy for the non-streaming STT fallback."""

    def __init__(self, profile: VoiceProfile):
        self.profile = profile
        self.started_at: float | None = None
        self.last_voice_at: float | None = None
        self.voice_seconds = 0.0

    def reset(self):
        self.started_at = None
        self.last_voice_at = None
        self.voice_seconds = 0.0

    def update(self, *, voice: bool, block_seconds: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        if voice:
            if self.started_at is None:
                self.started_at = now
            self.last_voice_at = now
            self.voice_seconds += max(0.0, float(block_seconds))
            return False
        if self.started_at is None or self.last_voice_at is None:
            return False
        if now - self.started_at >= float(self.profile.max_utterance_seconds):
            return True
        endpoint_ms = self.profile.min_endpoint_ms + min(
            self.profile.max_endpoint_ms - self.profile.min_endpoint_ms,
            int(self.voice_seconds * 75),
        )
        return (now - self.last_voice_at) * 1000.0 >= endpoint_ms


class AudioDeviceManager:
    """Resolve configured microphone/speaker names without pinning platform indexes."""

    @staticmethod
    def _rows(devices: Iterable) -> list[dict]:
        rows = []
        for index, item in enumerate(devices):
            row = dict(item) if not isinstance(item, dict) else item
            rows.append({"index": index, **row})
        return rows

    def list(self) -> list[dict]:
        import sounddevice as sd
        return self._rows(sd.query_devices())

    def resolve(self, name: str | None, *, kind: str, devices: Iterable | None = None):
        if kind not in {"input", "output"}:
            raise ValueError("kind must be input or output")
        if not name:
            return None
        rows = self._rows(devices) if devices is not None else self.list()
        needle = str(name).strip().lower()
        capacity_key = "max_input_channels" if kind == "input" else "max_output_channels"
        eligible = [row for row in rows if needle in str(row.get("name", "")).lower() and int(row.get(capacity_key, 0)) > 0]
        if not eligible:
            raise ValueError(f"Configured {kind} audio device was not found: {name}")
        exact = [row for row in eligible if str(row.get("name", "")).strip().lower() == needle]
        return (exact or eligible)[0]["index"]


def normalize_voice_style(style: str | None) -> str | None:
    if style is None:
        return None
    candidate = str(style).strip().lower()
    if candidate == "normal":
        candidate = "neutral"
    if not candidate:
        return None
    if candidate not in SUPPORTED_VOICE_STYLES:
        raise ValueError(f"Unsupported voice style {style!r}; expected one of {', '.join(SUPPORTED_VOICE_STYLES)}")
    return candidate


def choose_voice_style(
    *,
    manual_style: str | None = None,
    emotion_label: str | None = None,
    intent: str | None = None,
) -> VoiceStyleDecision:
    """Resolve bounded expression. Emotion labels are context signals, not feelings."""
    normalized_manual = normalize_voice_style(manual_style)
    if normalized_manual is not None:
        return VoiceStyleDecision(style=normalized_manual, source="manual")
    normalized_emotion = str(emotion_label or "").strip().lower()
    inferred = _EMOTION_TO_STYLE.get(normalized_emotion)
    if inferred is not None:
        return VoiceStyleDecision(inferred, "emotion", normalized_emotion)
    normalized_intent = str(intent or "").strip().lower().replace(" ", "_")
    inferred = _INTENT_TO_STYLE.get(normalized_intent)
    if inferred is not None:
        return VoiceStyleDecision(inferred, "intent", normalized_emotion or None)
    return VoiceStyleDecision("neutral", "default", normalized_emotion or None)


def segment_language_scripts(text: str, *, default_language: str = "en") -> list[LanguageSegment]:
    """Bounded script heuristic for code-switch planning, not full language detection."""
    _validate_language(default_language)
    if not text:
        return []
    script_language = {"devanagari": "hi", "arabic": "ar", "cyrillic": "ru", "han": "zh"}

    def classify(char: str) -> str | None:
        code = ord(char)
        if 0x0900 <= code <= 0x097F:
            return "devanagari"
        if 0x0600 <= code <= 0x06FF:
            return "arabic"
        if 0x0400 <= code <= 0x04FF:
            return "cyrillic"
        if 0x4E00 <= code <= 0x9FFF:
            return "han"
        if char.isalpha():
            return "latin"
        return None

    chunks: list[LanguageSegment] = []
    current_script: str | None = None
    current = ""
    for char in text:
        script = classify(char)
        if script is not None and current_script is not None and script != current_script:
            chunks.append(LanguageSegment(current, script_language.get(current_script, default_language)))
            current = ""
        current += char
        if script is not None:
            current_script = script
    if current:
        chunks.append(LanguageSegment(current, script_language.get(current_script or "latin", default_language)))
    return [chunk for chunk in chunks if chunk.text]


def chunk_text_for_voice(text: str, *, max_chars: int = 320) -> Iterator[str]:
    """Yield sentence-biased chunks for application-level streaming synthesis."""
    if max_chars < 32 or max_chars > 4000:
        raise ValueError("max_chars must be between 32 and 4000")
    remaining = str(text).strip()
    while remaining:
        if len(remaining) <= max_chars:
            yield remaining
            return
        window = remaining[: max_chars + 1]
        cuts = [window.rfind(mark) + 1 for mark in (". ", "! ", "? ", "; ", ", ")]
        cut = max(cuts)
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        chunk = remaining[:cut].strip()
        if chunk:
            yield chunk
        remaining = remaining[cut:].strip()


def estimated_avatar_cues(text: str, duration_seconds: float, *, expression: str = "neutral") -> list[AvatarCue]:
    """Generate coarse, explicitly estimated mouth cues when provider phonemes are absent."""
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+|[^\w\s]", str(text), flags=re.UNICODE)
    if not tokens or duration_seconds <= 0:
        return []
    weights = [max(1, len(token)) for token in tokens]
    total = sum(weights)
    cursor = 0.0
    result: list[AvatarCue] = []
    for token, weight in zip(tokens, weights):
        span = duration_seconds * weight / total
        viseme = "closed" if re.fullmatch(r"[^\w\s]", token, flags=re.UNICODE) else _rough_viseme(token)
        result.append(AvatarCue(cursor, min(duration_seconds, cursor + span), viseme, expression, "estimated"))
        cursor += span
    return result


def resample_for_rate(audio, rate: float):
    """Dependency-light playback rate adjustment for the fallback TTS path."""
    rate = float(rate)
    if math.isclose(rate, 1.0, rel_tol=1e-3):
        return audio
    import numpy as np
    if len(audio) < 2:
        return audio
    target = max(1, int(len(audio) / rate))
    old_x = np.linspace(0.0, 1.0, num=len(audio), endpoint=True)
    new_x = np.linspace(0.0, 1.0, num=target, endpoint=True)
    if getattr(audio, "ndim", 1) == 1:
        return np.interp(new_x, old_x, audio).astype("float32")
    channels = [np.interp(new_x, old_x, audio[:, i]) for i in range(audio.shape[1])]
    return np.stack(channels, axis=1).astype("float32")


def _validate_identifier(value: str, label: str) -> None:
    candidate = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", candidate):
        raise ValueError(f"invalid {label}")


def _validate_language(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}", str(value or "")):
        raise ValueError("language must be a bounded BCP-47-like tag")


def _pcm_samples(frames: bytes, width: int) -> list[int]:
    if width == 1:
        return [value - 128 for value in frames]
    if width == 2:
        count = len(frames) // 2
        return list(struct.unpack(f"<{count}h", frames[: count * 2]))
    count = len(frames) // 4
    return list(struct.unpack(f"<{count}i", frames[: count * 4]))


def _rough_viseme(token: str) -> str:
    first = token[:1].lower()
    if first in {"m", "b", "p"}:
        return "closed"
    if first in {"f", "v"}:
        return "teeth"
    if first in {"o", "u", "w", "q"}:
        return "round"
    if first in {"a", "e", "i", "y"}:
        return "open"
    return "mid"
