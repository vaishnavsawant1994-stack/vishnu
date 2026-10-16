from __future__ import annotations

import io
import json
import wave

import pytest

from voice.providers import SpeechToTextRequest, TextToSpeechRequest
from voice.voicestudio import (
    VoiceStudioClient,
    VoiceStudioError,
    VoiceStudioSettings,
    VoiceStudioSpeechToTextProvider,
    VoiceStudioTextToSpeechProvider,
    build_voicestudio_providers,
)


def _wav_bytes(sample_rate: int = 24_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * 8)
    return output.getvalue()


def test_settings_are_disabled_and_local_by_default(monkeypatch):
    for name in (
        "VISHNU_VOICESTUDIO_ENABLED",
        "VISHNU_VOICESTUDIO_BASE_URL",
        "VISHNU_VOICESTUDIO_API_KEY",
        "VISHNU_VOICESTUDIO_SHARE_PIN",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = VoiceStudioSettings.from_env()

    assert settings.enabled is False
    assert settings.base_url == "http://localhost:3900"
    assert settings.api_key is None
    assert settings.share_pin is None


def test_disabled_factory_allocates_no_client(monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "0")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_BASE_URL", "not-a-url")

    assert build_voicestudio_providers() is None


def test_tts_provider_uses_openai_compatible_endpoint_and_returns_wav_rate():
    captured = {}
    wav_audio = _wav_bytes(32_000)

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return 200, {"Content-Type": "audio/wav"}, wav_audio

    settings = VoiceStudioSettings(
        enabled=True,
        base_url="http://localhost:3900",
        api_key="secret-key",
        share_pin="123456",
        tts_model="tts-1",
        default_voice="default",
        timeout_seconds=17,
    )
    provider = VoiceStudioTextToSpeechProvider(VoiceStudioClient(settings, transport=transport))

    result = provider.synthesize(TextToSpeechRequest(text="Hello", voice="Narrator", language="en"))

    assert captured["url"] == "http://localhost:3900/v1/audio/speech"
    assert captured["payload"] == {
        "model": "tts-1",
        "input": "Hello",
        "voice": "Narrator",
        "response_format": "wav",
        "language": "en",
    }
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["headers"]["X-omnivoice-pin"] == "123456"
    assert captured["timeout"] == 17
    assert result.audio == wav_audio
    assert result.sample_rate_hz == 32_000
    assert result.mime_type == "audio/wav"


def test_stt_provider_wraps_pcm_as_wav_and_parses_text():
    captured = {}

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["content_type"] = dict(request.header_items())["Content-type"]
        captured["body"] = request.data
        return 200, {"Content-Type": "application/json"}, b'{"text":"hello vishnu"}'

    settings = VoiceStudioSettings(enabled=True)
    provider = VoiceStudioSpeechToTextProvider(VoiceStudioClient(settings, transport=transport))

    result = provider.transcribe(
        SpeechToTextRequest(audio=b"\x00\x00" * 16, sample_rate_hz=16_000, language="en")
    )

    assert captured["url"] == "http://localhost:3900/v1/audio/transcriptions"
    assert captured["content_type"].startswith("multipart/form-data; boundary=vishnu-")
    assert b'name="model"' in captured["body"]
    assert b"whisper-1" in captured["body"]
    assert b'name="language"' in captured["body"]
    assert b"\r\n\r\nen\r\n" in captured["body"]
    assert b"RIFF" in captured["body"]
    assert result.text == "hello vishnu"
    assert result.language == "en"


def test_health_failure_is_contained():
    def transport(request, timeout):
        raise VoiceStudioError("VoiceStudio is unreachable", retryable=True)

    client = VoiceStudioClient(VoiceStudioSettings(enabled=True), transport=transport)

    health = client.health()

    assert health.healthy is False
    assert health.detail == "VoiceStudio is unreachable"


def test_non_2xx_is_sanitized_and_retryable():
    def transport(request, timeout):
        return 503, {}, b"do not expose arbitrary response bodies"

    client = VoiceStudioClient(VoiceStudioSettings(enabled=True, api_key="never-print-me"), transport=transport)

    with pytest.raises(VoiceStudioError) as exc_info:
        client.synthesize("hello")

    assert exc_info.value.status_code == 503
    assert exc_info.value.retryable is True
    assert "never-print-me" not in str(exc_info.value)
    assert "do not expose" not in str(exc_info.value)


def test_provider_protocol_capabilities_are_explicit():
    client = VoiceStudioClient(
        VoiceStudioSettings(enabled=True),
        transport=lambda request, timeout: (200, {}, b"{}"),
    )
    stt = VoiceStudioSpeechToTextProvider(client)
    tts = VoiceStudioTextToSpeechProvider(client)

    assert stt.provider_id == "voicestudio"
    assert stt.capabilities()["external_service"] is True
    assert tts.provider_id == "voicestudio"
    assert tts.capabilities()["voice_profiles"] is True
