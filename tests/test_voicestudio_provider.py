from __future__ import annotations

import io
import json
import wave

import pytest

from voice.config import VoiceRuntimeSettings
from voice.providers import SpeechToTextProvider, SpeechToTextRequest, TextToSpeechProvider, TextToSpeechRequest
from voice.voicestudio import (
    VoiceStudioError,
    VoiceStudioProvider,
    VoiceStudioSettings,
    build_voicestudio_provider,
)
from voice.voicestudio_runtime import compose_voicestudio_runtime


def _wav_bytes(*, rate: int = 24_000, frames: int = 240) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeOpener:
    def __init__(self, *responses: bytes):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("unexpected VoiceStudio request")
        return FakeResponse(self.responses.pop(0))


class FakeVault:
    def __init__(self, value: str | None):
        self.value = value
        self.requested = []

    def get(self, name: str, default=None):
        self.requested.append(name)
        return self.value if self.value is not None else default


def test_voicestudio_is_default_off_and_does_not_change_current_voice_path():
    settings = VoiceStudioSettings()
    assert settings.enabled is False
    assert build_voicestudio_provider(settings=settings) is None


def test_voicestudio_remote_is_fail_closed():
    with pytest.raises(ValueError, match="allow_remote"):
        VoiceStudioSettings(enabled=True, base_url="https://voice.example")

    with pytest.raises(ValueError, match="https"):
        VoiceStudioSettings(
            enabled=True,
            base_url="http://voice.example",
            allow_remote=True,
        )

    settings = VoiceStudioSettings(
        enabled=True,
        base_url="https://voice.example",
        allow_remote=True,
    )
    with pytest.raises(ValueError, match="API key"):
        VoiceStudioProvider(settings)


def test_voicestudio_implements_existing_provider_contracts():
    provider = VoiceStudioProvider(VoiceStudioSettings(enabled=False))
    assert isinstance(provider, SpeechToTextProvider)
    assert isinstance(provider, TextToSpeechProvider)
    assert provider.capabilities()["external_process"] is True
    assert provider.capabilities()["vendored_code"] is False


def test_health_uses_versioned_discovery_without_starting_another_authority():
    opener = FakeOpener(json.dumps({"protocol": "voicestudio.speech.v1"}).encode())
    provider = VoiceStudioProvider(VoiceStudioSettings(enabled=True), opener=opener)

    health = provider.health()

    assert health.healthy is True
    assert "voicestudio.speech.v1" in (health.detail or "")
    request, timeout = opener.requests[0]
    assert request.full_url.endswith("/.well-known/voicestudio-speech")
    assert timeout == 30.0


def test_tts_uses_openai_compatible_speech_endpoint_and_returns_wav_rate():
    wav = _wav_bytes(rate=22_050)
    opener = FakeOpener(wav)
    provider = VoiceStudioProvider(
        VoiceStudioSettings(enabled=True, tts_model="tts-1-hd", tts_voice="alloy"),
        opener=opener,
    )

    result = provider.synthesize(TextToSpeechRequest("Hello Vishnu", voice="owner-voice"))

    assert result.audio == wav
    assert result.sample_rate_hz == 22_050
    request, _ = opener.requests[0]
    payload = json.loads(request.data.decode())
    assert request.full_url.endswith("/v1/audio/speech")
    assert payload == {
        "model": "tts-1-hd",
        "voice": "owner-voice",
        "input": "Hello Vishnu",
        "response_format": "wav",
    }


def test_stt_wraps_raw_pcm_and_uses_openai_compatible_transcription_endpoint():
    opener = FakeOpener(json.dumps({"text": "hello", "language": "en"}).encode())
    provider = VoiceStudioProvider(VoiceStudioSettings(enabled=True), opener=opener)

    result = provider.transcribe(
        SpeechToTextRequest(b"\x00\x00" * 100, sample_rate_hz=16_000, language="en")
    )

    assert result.text == "hello"
    assert result.language == "en"
    request, _ = opener.requests[0]
    assert request.full_url.endswith("/v1/audio/transcriptions")
    assert b'name="model"' in request.data
    assert b"whisper-1" in request.data
    assert b'name="language"' in request.data
    assert b'filename="audio.wav"' in request.data
    assert b"RIFF" in request.data


def test_translation_is_available_as_bounded_optional_provider_operation():
    opener = FakeOpener(json.dumps({"text": "Good morning"}).encode())
    provider = VoiceStudioProvider(VoiceStudioSettings(enabled=True), opener=opener)

    result = provider.translate_to_english(
        SpeechToTextRequest(_wav_bytes(rate=16_000), language="hi")
    )

    assert result.text == "Good morning"
    assert result.language == "en"
    assert opener.requests[0][0].full_url.endswith("/v1/audio/translations")


def test_remote_bearer_key_is_injected_but_not_exposed_in_capabilities():
    opener = FakeOpener(json.dumps({"data": []}).encode())
    provider = VoiceStudioProvider(
        VoiceStudioSettings(
            enabled=True,
            base_url="https://voice.example",
            allow_remote=True,
        ),
        api_key="secret-token",
        opener=opener,
    )

    provider.list_models()

    request, _ = opener.requests[0]
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert "secret-token" not in repr(provider.capabilities())


def test_response_and_request_bounds_fail_closed():
    provider = VoiceStudioProvider(
        VoiceStudioSettings(enabled=True, max_text_chars=4),
        opener=FakeOpener(_wav_bytes()),
    )
    with pytest.raises(VoiceStudioError, match="text exceeds"):
        provider.synthesize(TextToSpeechRequest("12345"))

    provider = VoiceStudioProvider(
        VoiceStudioSettings(enabled=True, max_output_audio_bytes=8),
        opener=FakeOpener(b"x" * 9),
    )
    with pytest.raises(VoiceStudioError, match="response exceeds"):
        provider.synthesize(TextToSpeechRequest("ok"))


def test_mcp_endpoint_is_exposed_for_universal_capabilities_not_reimplemented():
    provider = VoiceStudioProvider(VoiceStudioSettings(enabled=True))
    assert provider.mcp_endpoint == "http://127.0.0.1:3900/mcp/"


def test_application_binding_is_a_noop_while_voicestudio_is_disabled():
    binding = compose_voicestudio_runtime(
        provider_settings=VoiceStudioSettings(enabled=False),
        runtime_settings=VoiceRuntimeSettings(enabled=False),
    )

    assert binding.enabled is False
    assert binding.provider is None
    assert binding.runtime is None


def test_enabled_local_provider_reuses_existing_bounded_runtime_for_application_lifetime():
    binding = compose_voicestudio_runtime(
        provider_settings=VoiceStudioSettings(enabled=True),
        runtime_settings=VoiceRuntimeSettings(enabled=False),
    )

    assert binding.enabled is True
    assert binding.provider is binding.runtime.stt_provider
    assert binding.provider is binding.runtime.tts_provider
    assert binding.runtime.settings.enabled is True
    assert binding.runtime.state.value == "stopped"


def test_remote_application_binding_reads_bearer_key_only_from_existing_vault():
    vault = FakeVault("secret-token")
    binding = compose_voicestudio_runtime(
        vault=vault,
        provider_settings=VoiceStudioSettings(
            enabled=True,
            base_url="https://voice.example",
            allow_remote=True,
        ),
        runtime_settings=VoiceRuntimeSettings(enabled=False),
    )

    assert binding.enabled is True
    assert vault.requested == ["voicestudio.api_key"]
    assert "secret-token" not in repr(binding.provider.capabilities())


def test_remote_application_binding_without_vault_secret_fails_closed():
    with pytest.raises(ValueError, match="API key"):
        compose_voicestudio_runtime(
            vault=FakeVault(None),
            provider_settings=VoiceStudioSettings(
                enabled=True,
                base_url="https://voice.example",
                allow_remote=True,
            ),
            runtime_settings=VoiceRuntimeSettings(enabled=False),
        )
