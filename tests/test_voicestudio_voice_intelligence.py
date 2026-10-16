from __future__ import annotations

import io
import wave

import pytest

from voice.conversion import VoiceProfileError
from voice.platform import VoiceIntelligenceService
from voice.providers import TextToSpeechResult


def _wav_bytes(*, rate: int = 24_000, amplitude: int = 0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        sample = int(amplitude).to_bytes(2, "little", signed=True)
        audio.writeframes(sample * 1200)
    return output.getvalue()


class FakeProvider:
    provider_id = "voicestudio"


class FakeRuntimeState:
    value = "running"


class FakeProviderRuntime:
    def __init__(self, audio: bytes | None = None, error: BaseException | None = None):
        self.audio = audio or _wav_bytes(amplitude=100)
        self.error = error
        self.requests = []
        self.tts_provider = FakeProvider()
        self.state = FakeRuntimeState()

    def synthesize(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return TextToSpeechResult(self.audio, sample_rate_hz=24_000)


class FakeConversion:
    def __init__(self, *, output: bytes | None = None, error: BaseException | None = None):
        self.output = output or _wav_bytes(amplitude=200)
        self.error = error
        self.calls = []
        self.registry = None

    def convert(self, source_wav: bytes, *, profile_id=None, style="normal") -> bytes:
        self.calls.append((source_wav, profile_id, style))
        if self.error is not None:
            raise self.error
        return self.output


class FakeRouter:
    def __init__(self, *, fallback: bytes | None = None, conversion=None):
        self.fallback = fallback or _wav_bytes(amplitude=300)
        self.voice_conversion = conversion
        self.calls = []

    def synthesize(self, text: str, *, voice_profile_id=None, voice_style="normal") -> bytes:
        self.calls.append((text, voice_profile_id, voice_style))
        return self.fallback


def test_existing_model_router_path_is_unchanged_without_provider_runtime():
    router = FakeRouter()
    service = VoiceIntelligenceService(router, provider_runtime=None)

    result = service.synthesize(
        "Hello Vishnu",
        voice_profile_id="owner-voice",
        style="warm",
        language="en",
    )

    assert result.audio == router.fallback
    assert router.calls == [("Hello Vishnu", "owner-voice", "warm")]


def test_external_provider_supplies_source_audio_but_existing_conversion_owns_voice_identity():
    provider_audio = _wav_bytes(amplitude=100)
    converted_audio = _wav_bytes(amplitude=200)
    runtime = FakeProviderRuntime(provider_audio)
    conversion = FakeConversion(output=converted_audio)
    router = FakeRouter(conversion=conversion)
    service = VoiceIntelligenceService(router, provider_runtime=runtime)

    result = service.synthesize(
        "Hello Vishnu",
        voice_profile_id="owner-voice",
        style="warm",
        language="en",
    )

    assert result.audio == converted_audio
    assert len(runtime.requests) == 1
    assert runtime.requests[0].text == "Hello Vishnu"
    assert runtime.requests[0].language == "en"
    assert router.calls == []
    assert conversion.calls == [(provider_audio, "owner-voice", "warm")]


def test_provider_failure_falls_back_to_current_model_router_path():
    runtime = FakeProviderRuntime(error=RuntimeError("VoiceStudio offline"))
    router = FakeRouter()
    service = VoiceIntelligenceService(router, provider_runtime=runtime)

    result = service.synthesize(
        "Fallback please",
        voice_profile_id="owner-voice",
        style="serious",
    )

    assert result.audio == router.fallback
    assert router.calls == [("Fallback please", "owner-voice", "serious")]


def test_governed_conversion_failure_is_not_bypassed_by_fallback():
    runtime = FakeProviderRuntime()
    conversion = FakeConversion(error=VoiceProfileError("profile revoked"))
    router = FakeRouter(conversion=conversion)
    service = VoiceIntelligenceService(router, provider_runtime=runtime)

    with pytest.raises(VoiceProfileError, match="revoked"):
        service.synthesize(
            "Do not bypass consent",
            voice_profile_id="revoked-profile",
            style="normal",
        )

    assert router.calls == []
    assert conversion.calls


def test_external_source_can_be_used_without_conversion_authority_when_no_profile_conversion_is_configured():
    provider_audio = _wav_bytes(amplitude=100)
    runtime = FakeProviderRuntime(provider_audio)
    router = FakeRouter(conversion=None)
    service = VoiceIntelligenceService(router, provider_runtime=runtime)

    result = service.synthesize("Plain external source", language="en")

    assert result.audio == provider_audio
    assert router.calls == []


def test_status_exposes_only_non_sensitive_provider_runtime_state():
    runtime = FakeProviderRuntime()
    service = VoiceIntelligenceService(FakeRouter(), provider_runtime=runtime)

    status = service.status()

    assert status["external_provider_runtime"] is True
    assert status["external_tts_provider"] == "voicestudio"
    assert status["external_provider_state"] == "running"
