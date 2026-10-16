from __future__ import annotations

from dataclasses import asdict
import io
import math
import struct
import wave

import pytest

from voice.intelligence import (
    BUILTIN_VOICE_PACKS,
    PersonaStore,
    PronunciationLexicon,
    VoiceContext,
    VoiceDeviceCapabilities,
    VoiceDirector,
    VoicePersona,
    VoicePreferences,
    VoiceQualityEvaluator,
    VoiceUtterance,
    choose_voice_style,
    chunk_text_for_voice,
    estimated_avatar_cues,
    normalize_voice_style,
    segment_language_scripts,
)
from voice.platform import VoiceIntelligenceService


def wav_bytes(*, seconds: float = 0.2, sample_rate: int = 16000, amplitude: float = 0.2) -> bytes:
    count = max(1, int(seconds * sample_rate))
    frames = bytearray()
    for index in range(count):
        value = int(32767 * amplitude * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.extend(struct.pack('<h', value))
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(bytes(frames))
    return output.getvalue()


class FakeRouter:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, *, voice_profile_id=None, voice_style='normal'):
        self.calls.append((text, voice_profile_id, voice_style))
        return wav_bytes()


def test_builtin_voice_packs_are_bounded_and_distinct():
    assert set(BUILTIN_VOICE_PACKS) == {
        'vishnu_original',
        'vishnu_warm',
        'vishnu_professional',
        'vishnu_storyteller',
        'vishnu_calm',
        'vishnu_energetic',
    }
    assert BUILTIN_VOICE_PACKS['vishnu_storyteller'].style == 'storytelling'
    assert BUILTIN_VOICE_PACKS['vishnu_professional'].formality == pytest.approx(0.9)


def test_persona_rejects_unbounded_or_invalid_configuration():
    with pytest.raises(ValueError):
        VoicePersona('bad id with spaces', 'Bad')
    with pytest.raises(ValueError):
        VoicePersona('ok', 'Bad rate', speaking_rate=2.0)
    with pytest.raises(ValueError):
        VoicePersona('ok', 'Bad style', style='menacing')
    with pytest.raises(TypeError):
        VoicePersona(id='ok', name='No raw clone path', reference_audio='/tmp/person.wav')


def test_style_policy_preserves_normal_alias_and_context_signals():
    assert normalize_voice_style('normal') == 'neutral'
    assert choose_voice_style(manual_style='warm', emotion_label='sad').style == 'warm'
    assert choose_voice_style(emotion_label='sad').style == 'empathetic'
    assert choose_voice_style(intent='bedtime').style == 'calm'
    assert choose_voice_style().style == 'neutral'


def test_voice_director_precedence_and_emergency_context():
    director = VoiceDirector()
    plan = director.direct(
        persona_id='vishnu_storyteller',
        manual_style='warm',
        language='de-DE',
        preferences=VoicePreferences(style='calm', speaking_rate=1.1),
        context=VoiceContext(emotion_label='sad', urgent=True),
    )
    assert plan.style == 'warm'
    assert plan.style_source == 'manual'
    assert plan.language == 'de-DE'
    assert plan.speaking_rate == pytest.approx(1.1)

    emergency = director.direct(context=VoiceContext(urgent=True))
    assert emergency.style == 'urgent'
    assert emergency.style_source == 'context'


def test_persona_store_is_atomic_and_round_trips(tmp_path):
    store = PersonaStore(tmp_path / 'personas.json')
    persona = VoicePersona('teacher_one', 'Teacher One', style='warm', language='en-GB')
    store.put(persona)
    assert store.list()['teacher_one'] == persona
    store.delete('teacher_one')
    assert store.list() == {}
    with pytest.raises(ValueError):
        store.delete('vishnu_original')


def test_pronunciation_lexicon_persists_and_returns_only_matching_hints(tmp_path):
    path = tmp_path / 'pronunciations.json'
    lexicon = PronunciationLexicon(path)
    lexicon.set('Vishnu', 'VISH-noo')
    lexicon.set('Rudra', 'ROOD-ra')
    assert lexicon.substitutions('Ask Vishnu about this.') == [
        {'term': 'Vishnu', 'pronunciation': 'VISH-noo'}
    ]
    loaded = PronunciationLexicon(path)
    assert loaded.items() == (('Rudra', 'ROOD-ra'), ('Vishnu', 'VISH-noo'))
    loaded.remove('Rudra')
    assert dict(PronunciationLexicon(path).items()) == {'Vishnu': 'VISH-noo'}


def test_script_segmentation_supports_code_switch_planning_without_claiming_detection():
    segments = segment_language_scripts('Tomorrow मी येतो okay', default_language='en')
    assert any(segment.language_hint == 'hi' and 'मी' in segment.text for segment in segments)
    assert segments[0].language_hint == 'en'


def test_chunked_streaming_prefers_sentence_boundaries_and_is_bounded():
    text = 'First sentence. Second sentence is a little longer. Third sentence.'
    chunks = list(chunk_text_for_voice(text, max_chars=32))
    assert ''.join(chunks).replace(' ', '') == text.replace(' ', '')
    assert all(len(chunk) <= 33 for chunk in chunks)
    with pytest.raises(ValueError):
        list(chunk_text_for_voice(text, max_chars=10))


def test_quality_evaluator_reports_valid_wav_without_semantic_inspection():
    report = VoiceQualityEvaluator().inspect(wav_bytes())
    assert report.valid_wav is True
    assert report.acceptable is True
    assert report.duration_seconds == pytest.approx(0.2, abs=0.01)
    assert report.sample_rate == 16000
    assert report.rms > 0
    bad = VoiceQualityEvaluator().inspect(b'not a wav')
    assert bad.valid_wav is False
    assert bad.reasons == ('invalid_wav',)


def test_avatar_alignment_is_explicitly_estimated():
    cues = estimated_avatar_cues('Hello Vishnu!', 1.2, expression='friendly')
    assert cues
    assert all(cue.alignment == 'estimated' for cue in cues)
    assert cues[-1].end_seconds == pytest.approx(1.2)
    assert all(cue.expression == 'friendly' for cue in cues)


def test_device_capabilities_enforce_offline_and_language_requirements():
    plan = VoiceDirector().direct(language='de', context=VoiceContext(offline=True))
    assert VoiceDeviceCapabilities(offline_tts=True, languages=('de',)).supports(plan)
    assert not VoiceDeviceCapabilities(offline_tts=False, languages=('de',)).supports(plan)
    assert not VoiceDeviceCapabilities(offline_tts=True, languages=('en',)).supports(plan)


def test_service_routes_persona_style_to_existing_model_router(tmp_path):
    router = FakeRouter()
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    service.put_persona(
        VoicePersona(
            'narrator',
            'Narrator',
            voice_profile_id='enrolled-narrator',
            style='storytelling',
            language='en',
        )
    )
    service.set_pronunciation('Vishnu', 'VISH-noo')
    result = service.synthesize('Welcome, Vishnu.', persona_id='narrator')
    assert router.calls == [('Welcome, Vishnu.', 'enrolled-narrator', 'storytelling')]
    assert result.plan.persona_id == 'narrator'
    assert result.quality['acceptable'] is True
    assert result.pronunciation_hints == ({'term': 'Vishnu', 'pronunciation': 'VISH-noo'},)
    assert result.avatar_cues


def test_service_multi_speaker_dialogue_uses_distinct_personas(tmp_path):
    router = FakeRouter()
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    service.put_persona(VoicePersona('guide', 'Guide', voice_profile_id='guide-profile', style='warm'))
    results = service.synthesize_dialogue(
        [
            VoiceUtterance('Hello.', speaker='vishnu_original'),
            VoiceUtterance('Welcome.', speaker='guide'),
        ]
    )
    assert len(results) == 2
    assert router.calls[0][1] is None
    assert router.calls[1][1] == 'guide-profile'


def test_service_stream_cancellation_stops_new_chunks(tmp_path):
    router = FakeRouter()
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    checks = {'count': 0}

    def cancelled():
        checks['count'] += 1
        return checks['count'] >= 3

    results = list(
        service.synthesize_stream(
            'One sentence is here. Another sentence is here. A final sentence is here.',
            max_chars=32,
            cancelled=cancelled,
        )
    )
    assert len(results) == 1
    assert len(router.calls) == 1


def test_status_is_privacy_safe_and_truthful_about_streaming(tmp_path):
    service = VoiceIntelligenceService(FakeRouter(), data_dir=tmp_path)
    status = service.status()
    assert status['application_streaming'] is True
    assert status['native_openvoice_streaming_claimed'] is False
    assert status['raw_transcripts_retained'] is False
    assert status['raw_audio_retained'] is False
    assert 'text' not in str(status).lower()
