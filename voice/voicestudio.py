from __future__ import annotations

import io
import json
import os
import uuid
import wave
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from voice.providers import (
    ProviderHealth,
    SpeechToTextRequest,
    SpeechToTextResult,
    TextToSpeechRequest,
    TextToSpeechResult,
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def _validate_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("VoiceStudio base URL must be an absolute http(s) URL")
    if parsed.query or parsed.fragment:
        raise ValueError("VoiceStudio base URL must not contain a query or fragment")
    return candidate


@dataclass(frozen=True, slots=True)
class VoiceStudioSettings:
    """Settings for the optional external VoiceStudio bridge.

    VoiceStudio is disabled by default. It runs as a separate service, which
    keeps Vishnu's proprietary runtime isolated from VoiceStudio's AGPL code.
    """

    enabled: bool = False
    base_url: str = "http://localhost:3900"
    api_key: str | None = None
    share_pin: str | None = None
    tts_model: str = "tts-1"
    stt_model: str = "whisper-1"
    default_voice: str = "default"
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        if not self.tts_model.strip():
            raise ValueError("VoiceStudio TTS model must not be empty")
        if not self.stt_model.strip():
            raise ValueError("VoiceStudio STT model must not be empty")
        if not self.default_voice.strip():
            raise ValueError("VoiceStudio default voice must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("VoiceStudio timeout must be > 0")

    @classmethod
    def from_env(cls) -> "VoiceStudioSettings":
        return cls(
            enabled=_env_bool("VISHNU_VOICESTUDIO_ENABLED", False),
            base_url=os.getenv("VISHNU_VOICESTUDIO_BASE_URL", "http://localhost:3900"),
            api_key=os.getenv("VISHNU_VOICESTUDIO_API_KEY") or None,
            share_pin=os.getenv("VISHNU_VOICESTUDIO_SHARE_PIN") or None,
            tts_model=os.getenv("VISHNU_VOICESTUDIO_TTS_MODEL", "tts-1"),
            stt_model=os.getenv("VISHNU_VOICESTUDIO_STT_MODEL", "whisper-1"),
            default_voice=os.getenv("VISHNU_VOICESTUDIO_VOICE", "default"),
            timeout_seconds=_env_positive_float("VISHNU_VOICESTUDIO_TIMEOUT_SECONDS", 300.0),
        )


class VoiceStudioError(RuntimeError):
    """Sanitized failure returned by the external VoiceStudio service."""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


Transport = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]


def _default_transport(request: Request, timeout_seconds: float) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is owner-configured
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        try:
            body = exc.read(4096)
        except Exception:
            body = b""
        message = _error_message(body) or f"VoiceStudio returned HTTP {exc.code}"
        raise VoiceStudioError(
            message,
            status_code=exc.code,
            retryable=exc.code in _RETRYABLE_STATUS,
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VoiceStudioError("VoiceStudio is unreachable", retryable=True) from exc


def _error_message(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"][:500]
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail[:500]
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"][:500]
    return None


def _wav_sample_rate(audio: bytes, fallback: int = 24_000) -> int:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            return wav_file.getframerate()
    except (wave.Error, EOFError):
        return fallback


def _ensure_wav(audio: bytes, sample_rate_hz: int) -> bytes:
    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return audio
    out = io.BytesIO()
    with wave.open(out, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(audio)
    return out.getvalue()


def _multipart_audio(audio: bytes, *, model: str, language: str | None) -> tuple[bytes, str]:
    boundary = f"vishnu-{uuid.uuid4().hex}"
    marker = f"--{boundary}\r\n".encode()
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.extend(
            [
                marker,
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    field("model", model)
    field("response_format", "json")
    if language:
        field("language", language)
    parts.extend(
        [
            marker,
            b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class VoiceStudioClient:
    """Small dependency-free client for VoiceStudio's stable HTTP boundary."""

    def __init__(self, settings: VoiceStudioSettings, *, transport: Transport | None = None):
        self.settings = settings
        self._transport = transport or _default_transport

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "Vishnu-VoiceStudio/1"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        if self.settings.share_pin:
            headers["X-OmniVoice-Pin"] = self.settings.share_pin
        return headers

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str | None = None,
        accept: str | None = None,
    ) -> tuple[Mapping[str, str], bytes]:
        headers = self._headers(content_type=content_type)
        if accept:
            headers["Accept"] = accept
        request = Request(
            f"{self.settings.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        status, response_headers, body = self._transport(request, self.settings.timeout_seconds)
        if status < 200 or status >= 300:
            raise VoiceStudioError(
                f"VoiceStudio returned HTTP {status}",
                status_code=status,
                retryable=status in _RETRYABLE_STATUS,
            )
        return response_headers, body

    def health(self) -> ProviderHealth:
        try:
            self._request("/health")
        except VoiceStudioError as exc:
            return ProviderHealth(healthy=False, detail=str(exc))
        return ProviderHealth(healthy=True, detail="VoiceStudio reachable")

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
    ) -> tuple[bytes, int]:
        payload: dict[str, object] = {
            "model": self.settings.tts_model,
            "input": text,
            "voice": voice or self.settings.default_voice,
            "response_format": "wav",
        }
        if language:
            payload["language"] = language
        _, audio = self._request(
            "/v1/audio/speech",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            accept="audio/wav",
        )
        if not audio:
            raise VoiceStudioError("VoiceStudio returned empty synthesized audio", retryable=True)
        return audio, _wav_sample_rate(audio)

    def transcribe(self, audio: bytes, *, sample_rate_hz: int, language: str | None = None) -> str:
        wav_audio = _ensure_wav(audio, sample_rate_hz)
        body, content_type = _multipart_audio(
            wav_audio,
            model=self.settings.stt_model,
            language=language,
        )
        _, response = self._request(
            "/v1/audio/transcriptions",
            method="POST",
            data=body,
            content_type=content_type,
        )
        try:
            payload = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VoiceStudioError("VoiceStudio returned an invalid transcription response") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise VoiceStudioError("VoiceStudio transcription response did not contain text")
        return text


class VoiceStudioSpeechToTextProvider:
    provider_id = "voicestudio"

    def __init__(self, client: VoiceStudioClient):
        self.client = client

    def health(self) -> ProviderHealth:
        return self.client.health()

    def capabilities(self) -> Mapping[str, object]:
        return {
            "provider": self.provider_id,
            "streaming": False,
            "languages": "engine-dependent",
            "external_service": True,
        }

    def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResult:
        text = self.client.transcribe(
            request.audio,
            sample_rate_hz=request.sample_rate_hz,
            language=request.language,
        )
        return SpeechToTextResult(text=text, language=request.language)


class VoiceStudioTextToSpeechProvider:
    provider_id = "voicestudio"

    def __init__(self, client: VoiceStudioClient):
        self.client = client

    def health(self) -> ProviderHealth:
        return self.client.health()

    def capabilities(self) -> Mapping[str, object]:
        return {
            "provider": self.provider_id,
            "voice_profiles": True,
            "languages": "engine-dependent",
            "external_service": True,
            "output": "audio/wav",
        }

    def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        audio, sample_rate_hz = self.client.synthesize(
            request.text,
            voice=request.voice,
            language=request.language,
        )
        return TextToSpeechResult(audio=audio, sample_rate_hz=sample_rate_hz, mime_type="audio/wav")


def build_voicestudio_providers(
    settings: VoiceStudioSettings | None = None,
    *,
    transport: Transport | None = None,
) -> tuple[VoiceStudioSpeechToTextProvider, VoiceStudioTextToSpeechProvider] | None:
    """Build the optional providers without changing Vishnu's default voice path."""

    resolved = settings or VoiceStudioSettings.from_env()
    if not resolved.enabled:
        return None
    client = VoiceStudioClient(resolved, transport=transport)
    return VoiceStudioSpeechToTextProvider(client), VoiceStudioTextToSpeechProvider(client)
