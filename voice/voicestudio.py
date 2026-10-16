from __future__ import annotations

import json
import os
import secrets
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from voice.providers import (
    ProviderHealth,
    SpeechToTextRequest,
    SpeechToTextResult,
    TextToSpeechRequest,
    TextToSpeechResult,
)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_DEFAULT_BASE_URL = "http://127.0.0.1:3900"


class VoiceStudioError(RuntimeError):
    """Raised when the optional external VoiceStudio provider cannot serve a request."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True, slots=True)
class VoiceStudioSettings:
    """Configuration for Vishnu's external VoiceStudio adapter.

    The adapter is disabled and loopback-only by default. Remote endpoints require
    explicit opt-in and HTTPS. Credentials are deliberately not loaded here; inject
    them from Vishnu's existing secret authority at composition time.
    """

    enabled: bool = False
    base_url: str = _DEFAULT_BASE_URL
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    stt_model: str = "whisper-1"
    timeout_seconds: float = 30.0
    max_text_chars: int = 20_000
    max_input_audio_bytes: int = 32 * 1024 * 1024
    max_output_audio_bytes: int = 64 * 1024 * 1024
    allow_remote: bool = False
    require_https_remote: bool = True

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("VoiceStudio base_url must use http or https")
        if not parsed.hostname:
            raise ValueError("VoiceStudio base_url must include a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("VoiceStudio base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("VoiceStudio base_url must not contain query or fragment")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.max_text_chars < 1:
            raise ValueError("max_text_chars must be >= 1")
        if self.max_input_audio_bytes < 1 or self.max_output_audio_bytes < 1:
            raise ValueError("audio byte limits must be >= 1")
        if self.is_remote:
            if not self.allow_remote:
                raise ValueError("remote VoiceStudio endpoints require allow_remote=True")
            if self.require_https_remote and parsed.scheme != "https":
                raise ValueError("remote VoiceStudio endpoints require https")

    @property
    def is_remote(self) -> bool:
        return (urlsplit(self.base_url).hostname or "").lower() not in _LOOPBACK_HOSTS

    @classmethod
    def from_env(cls) -> "VoiceStudioSettings":
        return cls(
            enabled=_env_bool("VISHNU_VOICESTUDIO_ENABLED", False),
            base_url=os.getenv("VISHNU_VOICESTUDIO_URL", _DEFAULT_BASE_URL).strip(),
            tts_model=os.getenv("VISHNU_VOICESTUDIO_TTS_MODEL", "tts-1").strip() or "tts-1",
            tts_voice=os.getenv("VISHNU_VOICESTUDIO_TTS_VOICE", "alloy").strip() or "alloy",
            stt_model=os.getenv("VISHNU_VOICESTUDIO_STT_MODEL", "whisper-1").strip() or "whisper-1",
            timeout_seconds=float(os.getenv("VISHNU_VOICESTUDIO_TIMEOUT_SECONDS", "30")),
            max_text_chars=int(os.getenv("VISHNU_VOICESTUDIO_MAX_TEXT_CHARS", "20000")),
            max_input_audio_bytes=int(
                os.getenv("VISHNU_VOICESTUDIO_MAX_INPUT_AUDIO_BYTES", str(32 * 1024 * 1024))
            ),
            max_output_audio_bytes=int(
                os.getenv("VISHNU_VOICESTUDIO_MAX_OUTPUT_AUDIO_BYTES", str(64 * 1024 * 1024))
            ),
            allow_remote=_env_bool("VISHNU_VOICESTUDIO_ALLOW_REMOTE", False),
            require_https_remote=_env_bool("VISHNU_VOICESTUDIO_REQUIRE_HTTPS_REMOTE", True),
        )


class VoiceStudioProvider:
    """OpenAI-compatible VoiceStudio adapter for Vishnu's existing voice runtime.

    This class intentionally implements only transport/provider responsibilities.
    Vishnu remains authoritative for approvals, tool execution, device trust,
    voice-profile consent, secrets, routing, scheduling, memory, and auditing.
    """

    provider_id = "voicestudio"

    def __init__(
        self,
        settings: VoiceStudioSettings | None = None,
        *,
        api_key: str | None = None,
        opener=None,
    ) -> None:
        self.settings = settings or VoiceStudioSettings.from_env()
        self._api_key = str(api_key or "").strip() or None
        if self.settings.is_remote and self.settings.enabled and not self._api_key:
            raise ValueError("remote VoiceStudio endpoints require an injected API key")
        self._opener = opener or build_opener(_NoRedirectHandler())

    @property
    def mcp_endpoint(self) -> str:
        return self._url("/mcp/")

    def health(self) -> ProviderHealth:
        if not self.settings.enabled:
            return ProviderHealth(False, "VoiceStudio provider is disabled")
        try:
            payload = self.discover()
        except VoiceStudioError as exc:
            return ProviderHealth(False, str(exc))
        protocol = payload.get("protocol") or payload.get("schema") or payload.get("name")
        detail = "VoiceStudio speech endpoint reachable"
        if protocol:
            detail = f"{detail}: {protocol}"
        return ProviderHealth(True, detail)

    def capabilities(self) -> Mapping[str, object]:
        return {
            "provider": self.provider_id,
            "enabled": self.settings.enabled,
            "remote": self.settings.is_remote,
            "tts": True,
            "stt": True,
            "translations": True,
            "models": True,
            "voices": True,
            "mcp": True,
            "openai_compatible": True,
            "external_process": True,
            "vendored_code": False,
            "vendored_models": False,
        }

    def discover(self) -> dict:
        return self._json_request("GET", "/.well-known/voicestudio-speech")

    def list_models(self) -> dict:
        return self._json_request("GET", "/v1/models")

    def list_voices(self) -> dict:
        return self._json_request("GET", "/v1/audio/voices")

    def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult:
        self._require_enabled()
        if len(request.text) > self.settings.max_text_chars:
            raise VoiceStudioError("speech text exceeds configured size limit")
        body = {
            "model": self.settings.tts_model,
            "voice": request.voice or self.settings.tts_voice,
            "input": request.text,
            "response_format": "wav",
        }
        audio = self._request(
            "POST",
            "/v1/audio/speech",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            limit=self.settings.max_output_audio_bytes,
        )
        sample_rate = _wav_sample_rate(audio)
        return TextToSpeechResult(audio=audio, sample_rate_hz=sample_rate, mime_type="audio/wav")

    def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResult:
        self._require_enabled()
        payload = self._audio_multipart(
            request,
            endpoint="/v1/audio/transcriptions",
            fields={"model": self.settings.stt_model, "response_format": "json"},
        )
        text = str(payload.get("text") or "")
        language = payload.get("language")
        if not text.strip():
            raise VoiceStudioError("VoiceStudio transcription returned no text")
        return SpeechToTextResult(text=text, language=str(language) if language else request.language)

    def translate_to_english(self, request: SpeechToTextRequest) -> SpeechToTextResult:
        self._require_enabled()
        payload = self._audio_multipart(
            request,
            endpoint="/v1/audio/translations",
            fields={"model": self.settings.stt_model, "response_format": "json"},
        )
        text = str(payload.get("text") or "")
        if not text.strip():
            raise VoiceStudioError("VoiceStudio translation returned no text")
        return SpeechToTextResult(text=text, language="en")

    def _audio_multipart(
        self,
        request: SpeechToTextRequest,
        *,
        endpoint: str,
        fields: dict[str, str],
    ) -> dict:
        if len(request.audio) > self.settings.max_input_audio_bytes:
            raise VoiceStudioError("input audio exceeds configured size limit")
        wav_audio = _ensure_wav(request.audio, request.sample_rate_hz)
        boundary = f"vishnu-{secrets.token_hex(12)}"
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        if request.language:
            parts.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    b'Content-Disposition: form-data; name="language"\r\n\r\n',
                    request.language.encode("utf-8"),
                    b"\r\n",
                ]
            )
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n',
                b"Content-Type: audio/wav\r\n\r\n",
                wav_audio,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        body = b"".join(parts)
        if len(body) > self.settings.max_input_audio_bytes + 64 * 1024:
            raise VoiceStudioError("multipart audio request exceeds configured size limit")
        raw = self._request(
            "POST",
            endpoint,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            limit=4 * 1024 * 1024,
        )
        return _decode_json(raw)

    def _json_request(self, method: str, path: str) -> dict:
        self._require_enabled()
        raw = self._request(method, path, limit=4 * 1024 * 1024)
        return _decode_json(raw)

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        limit: int,
    ) -> bytes:
        request_headers = {
            "Accept": "application/json, audio/wav;q=0.9, */*;q=0.1",
            "User-Agent": "Vishnu-VoiceStudio/1",
        }
        request_headers.update(headers or {})
        if self._api_key:
            request_headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(
            self._url(path),
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self.settings.timeout_seconds) as response:
                return _read_bounded(response, limit)
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            raise VoiceStudioError(f"VoiceStudio HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise VoiceStudioError("VoiceStudio endpoint is unavailable") from exc

    def _url(self, path: str) -> str:
        return urljoin(self.settings.base_url.rstrip("/") + "/", path.lstrip("/"))

    def _require_enabled(self) -> None:
        if not self.settings.enabled:
            raise VoiceStudioError("VoiceStudio provider is disabled")


def build_voicestudio_provider(
    *,
    settings: VoiceStudioSettings | None = None,
    api_key: str | None = None,
    opener=None,
) -> VoiceStudioProvider | None:
    """Return an optional provider without changing Vishnu's default voice path."""

    resolved = settings or VoiceStudioSettings.from_env()
    if not resolved.enabled:
        return None
    return VoiceStudioProvider(resolved, api_key=api_key, opener=opener)


def _read_bounded(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise VoiceStudioError("VoiceStudio response exceeds configured size limit")
    return data


def _decode_json(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceStudioError("VoiceStudio returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise VoiceStudioError("VoiceStudio returned an unexpected JSON shape")
    return payload


def _http_error_detail(exc: HTTPError) -> str:
    try:
        raw = exc.read(16 * 1024)
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "request failed"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:500]
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail[:500]
    return "request failed"


def _ensure_wav(audio: bytes, sample_rate_hz: int) -> bytes:
    try:
        with wave.open(BytesIO(audio), "rb") as source:
            if source.getframerate() > 0 and source.getnchannels() in {1, 2}:
                return audio
    except (wave.Error, EOFError):
        pass

    if len(audio) % 2:
        raise VoiceStudioError("raw PCM input must contain complete 16-bit samples")
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate_hz)
        target.writeframes(audio)
    return output.getvalue()


def _wav_sample_rate(audio: bytes) -> int:
    try:
        with wave.open(BytesIO(audio), "rb") as source:
            sample_rate = source.getframerate()
            frames = source.getnframes()
    except (wave.Error, EOFError) as exc:
        raise VoiceStudioError("VoiceStudio TTS did not return valid WAV audio") from exc
    if sample_rate < 1 or frames < 1:
        raise VoiceStudioError("VoiceStudio TTS returned an empty WAV")
    return sample_rate
