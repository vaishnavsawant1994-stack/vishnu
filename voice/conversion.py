from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Callable, Protocol
from uuid import uuid4
import wave


PROFILE_SCHEMA_VERSION = 1
CANONICAL_PROFILE_ID = 'vishnu'
ALLOWED_VOICE_STYLES = frozenset(
    {
        'normal',
        'warm',
        'empathetic',
        'cheerful',
        'serious',
        'urgent',
        'storytelling',
        'calm',
    }
)
_PROFILE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')


class VoiceProfileError(ValueError):
    """Raised when a governed voice profile cannot be used safely."""


class VoiceConversionError(RuntimeError):
    """Raised when the optional conversion engine cannot produce audio."""


@dataclass(frozen=True)
class VoiceProfile:
    profile_id: str
    display_name: str
    reference_file: str
    reference_sha256: str
    consent_attested: bool
    purpose: str
    created_at: float
    revoked_at: float | None = None
    engine: str = 'openvoice'
    engine_version: str = 'v2'
    canonical: bool = False

    @property
    def active(self) -> bool:
        return self.consent_attested and self.revoked_at is None


@dataclass(frozen=True)
class VoiceConversionSettings:
    enabled: bool
    profile_store: Path
    default_profile_id: str
    converter_config_path: Path | None
    converter_checkpoint_path: Path | None
    source_se_path: Path | None
    device: str
    watermark_message: str
    fallback_to_source: bool
    max_reference_bytes: int
    max_reference_seconds: float

    @classmethod
    def from_settings(cls, settings) -> 'VoiceConversionSettings':
        data_dir = Path(getattr(settings, 'data_dir', Path.home() / '.personal_ai')).expanduser().resolve()
        profile_store_raw = str(getattr(settings, 'openvoice_profile_store', '') or '').strip()
        profile_store = (
            Path(profile_store_raw).expanduser().resolve()
            if profile_store_raw
            else data_dir / 'voice' / 'profiles'
        )

        def optional_path(attribute: str) -> Path | None:
            value = str(getattr(settings, attribute, '') or '').strip()
            if not value:
                return None
            if value.startswith(('http://', 'https://')):
                raise VoiceProfileError(f'{attribute} must be a local path')
            return Path(value).expanduser().resolve()

        return cls(
            enabled=bool(getattr(settings, 'openvoice_enabled', False)),
            profile_store=profile_store,
            default_profile_id=str(
                getattr(settings, 'openvoice_default_profile_id', CANONICAL_PROFILE_ID)
                or CANONICAL_PROFILE_ID
            ).strip().lower(),
            converter_config_path=optional_path('openvoice_converter_config'),
            converter_checkpoint_path=optional_path('openvoice_converter_checkpoint'),
            source_se_path=optional_path('openvoice_source_se_path'),
            device=str(getattr(settings, 'openvoice_device', 'cpu') or 'cpu').strip(),
            watermark_message=str(
                getattr(settings, 'openvoice_watermark_message', '@VISHNU') or ''
            )[:128],
            fallback_to_source=bool(getattr(settings, 'openvoice_fallback_to_source', True)),
            max_reference_bytes=max(
                64 * 1024,
                min(
                    64 * 1024 * 1024,
                    int(getattr(settings, 'openvoice_max_reference_bytes', 20 * 1024 * 1024)),
                ),
            ),
            max_reference_seconds=max(
                1.0,
                min(
                    600.0,
                    float(getattr(settings, 'openvoice_max_reference_seconds', 120.0)),
                ),
            ),
        )


class VoiceProfileRegistry:
    """Local-only, consent-gated voice enrollment with revocation and provenance."""

    def __init__(
        self,
        root: Path,
        *,
        max_reference_bytes: int = 20 * 1024 * 1024,
        max_reference_seconds: float = 120.0,
    ):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_reference_bytes = max_reference_bytes
        self.max_reference_seconds = max_reference_seconds
        self._manifest_path = self.root / 'profiles.json'
        self._lock = threading.RLock()

    @staticmethod
    def _validate_profile_id(profile_id: str) -> str:
        normalized = str(profile_id or '').strip().lower()
        if not _PROFILE_ID_RE.fullmatch(normalized):
            raise VoiceProfileError(
                'profile_id must be 1-64 lowercase letters, numbers, dot, underscore or dash'
            )
        return normalized

    def _load(self) -> dict[str, VoiceProfile]:
        if not self._manifest_path.exists():
            return {}
        try:
            payload = json.loads(self._manifest_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise VoiceProfileError('voice profile manifest is unreadable') from exc
        if payload.get('version') != PROFILE_SCHEMA_VERSION:
            raise VoiceProfileError('unsupported voice profile manifest version')
        raw_profiles = payload.get('profiles')
        if not isinstance(raw_profiles, dict):
            raise VoiceProfileError('voice profile manifest is invalid')
        profiles: dict[str, VoiceProfile] = {}
        try:
            for key, value in raw_profiles.items():
                profile = VoiceProfile(**value)
                if self._validate_profile_id(key) != profile.profile_id:
                    raise VoiceProfileError('voice profile manifest identity mismatch')
                profiles[key] = profile
        except (TypeError, ValueError) as exc:
            raise VoiceProfileError('voice profile manifest is invalid') from exc
        return profiles

    def _save(self, profiles: dict[str, VoiceProfile]) -> None:
        payload = {
            'version': PROFILE_SCHEMA_VERSION,
            'profiles': {key: asdict(value) for key, value in sorted(profiles.items())},
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True) + '\n'
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=self.root,
            prefix='.profiles-',
            suffix='.tmp',
            delete=False,
        ) as handle:
            handle.write(encoded)
            handle.flush()
            temp_path = Path(handle.name)
        try:
            temp_path.chmod(0o600)
            temp_path.replace(self._manifest_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _validate_reference(self, reference_wav: bytes) -> None:
        if not isinstance(reference_wav, (bytes, bytearray)) or not reference_wav:
            raise VoiceProfileError('reference audio must contain WAV bytes')
        if len(reference_wav) > self.max_reference_bytes:
            raise VoiceProfileError('reference audio exceeds configured size limit')
        try:
            with wave.open(BytesIO(reference_wav), 'rb') as audio:
                rate = audio.getframerate()
                frames = audio.getnframes()
                channels = audio.getnchannels()
                width = audio.getsampwidth()
        except (wave.Error, EOFError) as exc:
            raise VoiceProfileError('reference audio must be a valid WAV file') from exc
        if rate <= 0 or frames <= 0 or channels not in {1, 2} or width not in {1, 2, 3, 4}:
            raise VoiceProfileError('reference WAV has unsupported audio parameters')
        duration = frames / rate
        if duration < 0.2:
            raise VoiceProfileError('reference audio is too short')
        if duration > self.max_reference_seconds:
            raise VoiceProfileError('reference audio exceeds configured duration limit')

    def enroll(
        self,
        reference_wav: bytes,
        *,
        display_name: str,
        purpose: str,
        consent_attested: bool,
        profile_id: str | None = None,
        canonical: bool = False,
        engine: str = 'openvoice',
        engine_version: str = 'v2',
    ) -> VoiceProfile:
        if not consent_attested:
            raise VoiceProfileError('explicit consent attestation is required for voice enrollment')
        self._validate_reference(reference_wav)
        normalized_id = self._validate_profile_id(profile_id or f'voice-{uuid4().hex[:16]}')
        if canonical and normalized_id != CANONICAL_PROFILE_ID:
            raise VoiceProfileError(f'canonical voice profile must use id {CANONICAL_PROFILE_ID!r}')
        if normalized_id == CANONICAL_PROFILE_ID and not canonical:
            raise VoiceProfileError('the canonical Vishnu voice id is reserved')
        name = str(display_name or '').strip()
        allowed_purpose = str(purpose or '').strip()
        if not name:
            raise VoiceProfileError('display_name is required')
        if not allowed_purpose:
            raise VoiceProfileError('purpose is required')

        digest = sha256(reference_wav).hexdigest()
        reference_file = f'{normalized_id}-{digest[:16]}.wav'
        reference_path = self.root / reference_file
        with self._lock:
            profiles = self._load()
            if normalized_id in profiles:
                raise VoiceProfileError('voice profile already exists')
            reference_path.write_bytes(reference_wav)
            reference_path.chmod(0o600)
            profile = VoiceProfile(
                profile_id=normalized_id,
                display_name=name,
                reference_file=reference_file,
                reference_sha256=digest,
                consent_attested=True,
                purpose=allowed_purpose,
                created_at=time.time(),
                engine=str(engine or 'openvoice'),
                engine_version=str(engine_version or 'v2'),
                canonical=canonical,
            )
            try:
                profiles[normalized_id] = profile
                self._save(profiles)
            except Exception:
                reference_path.unlink(missing_ok=True)
                raise
            return profile

    def list(self, *, include_revoked: bool = False) -> list[VoiceProfile]:
        with self._lock:
            profiles = self._load().values()
            return [profile for profile in profiles if include_revoked or profile.active]

    def get(self, profile_id: str, *, require_active: bool = True) -> VoiceProfile:
        normalized_id = self._validate_profile_id(profile_id)
        with self._lock:
            profile = self._load().get(normalized_id)
        if profile is None:
            raise VoiceProfileError('voice profile does not exist')
        if require_active and not profile.active:
            raise VoiceProfileError('voice profile is revoked or lacks consent')
        return profile

    def reference_path(self, profile: VoiceProfile) -> Path:
        candidate = (self.root / profile.reference_file).resolve()
        if candidate.parent != self.root:
            raise VoiceProfileError('voice profile reference path is invalid')
        if not candidate.is_file():
            raise VoiceProfileError('voice profile reference audio is missing')
        digest = sha256(candidate.read_bytes()).hexdigest()
        if digest != profile.reference_sha256:
            raise VoiceProfileError('voice profile reference audio failed integrity validation')
        return candidate

    def revoke(self, profile_id: str, *, allow_canonical: bool = False) -> VoiceProfile:
        normalized_id = self._validate_profile_id(profile_id)
        with self._lock:
            profiles = self._load()
            profile = profiles.get(normalized_id)
            if profile is None:
                raise VoiceProfileError('voice profile does not exist')
            if profile.canonical and not allow_canonical:
                raise VoiceProfileError('canonical Vishnu voice requires explicit protected revocation')
            if profile.revoked_at is not None:
                return profile
            revoked = VoiceProfile(**{**asdict(profile), 'revoked_at': time.time()})
            profiles[normalized_id] = revoked
            self._save(profiles)
            return revoked

    def delete(self, profile_id: str, *, allow_canonical: bool = False) -> None:
        normalized_id = self._validate_profile_id(profile_id)
        with self._lock:
            profiles = self._load()
            profile = profiles.get(normalized_id)
            if profile is None:
                return
            if profile.canonical and not allow_canonical:
                raise VoiceProfileError('canonical Vishnu voice requires explicit protected deletion')
            profiles.pop(normalized_id)
            self._save(profiles)
            (self.root / profile.reference_file).unlink(missing_ok=True)


class VoiceConversionProvider(Protocol):
    def convert(
        self,
        source_wav: bytes,
        *,
        profile: VoiceProfile,
        reference_path: Path,
        style: str,
        watermark_message: str,
    ) -> bytes: ...


class OpenVoiceConverter:
    """Lazy OpenVoice V2 adapter. It never downloads models or accepts remote references."""

    def __init__(self, settings: VoiceConversionSettings):
        self.settings = settings
        self._converter = None
        self._source_se = None
        self._se_extractor = None
        self._target_cache: dict[tuple[str, str], object] = {}
        self._lock = threading.RLock()

    def _require_local_file(self, path: Path | None, label: str) -> Path:
        if path is None or not path.is_file():
            raise VoiceConversionError(f'{label} is not configured as an existing local file')
        return path

    def _ensure_loaded(self):
        with self._lock:
            if self._converter is not None:
                return self._converter
            config_path = self._require_local_file(
                self.settings.converter_config_path,
                'OpenVoice converter config',
            )
            checkpoint_path = self._require_local_file(
                self.settings.converter_checkpoint_path,
                'OpenVoice converter checkpoint',
            )
            source_se_path = self._require_local_file(
                self.settings.source_se_path,
                'OpenVoice source speaker embedding',
            )
            try:
                import torch
                from openvoice.api import ToneColorConverter
                from openvoice import se_extractor
            except ImportError as exc:
                raise VoiceConversionError(
                    'OpenVoice dependencies are not installed; install the optional voice engine locally'
                ) from exc
            try:
                converter = ToneColorConverter(str(config_path), device=self.settings.device)
                converter.load_ckpt(str(checkpoint_path))
                try:
                    source_se = torch.load(
                        str(source_se_path),
                        map_location=self.settings.device,
                        weights_only=True,
                    )
                except TypeError:
                    source_se = torch.load(str(source_se_path), map_location=self.settings.device)
                if hasattr(source_se, 'to'):
                    source_se = source_se.to(self.settings.device)
            except Exception as exc:
                raise VoiceConversionError('OpenVoice local model initialization failed') from exc
            self._converter = converter
            self._source_se = source_se
            self._se_extractor = se_extractor
            return converter

    def _target_embedding(self, profile: VoiceProfile, reference_path: Path):
        converter = self._ensure_loaded()
        checkpoint = self.settings.converter_checkpoint_path
        revision = sha256(str(checkpoint).encode('utf-8')).hexdigest()[:16]
        key = (profile.reference_sha256, revision)
        with self._lock:
            cached = self._target_cache.get(key)
            if cached is not None:
                return cached
        try:
            result = self._se_extractor.get_se(str(reference_path), converter, vad=True)
            target = result[0] if isinstance(result, tuple) else result
        except Exception as exc:
            raise VoiceConversionError('OpenVoice target speaker extraction failed') from exc
        with self._lock:
            self._target_cache[key] = target
        return target

    def convert(
        self,
        source_wav: bytes,
        *,
        profile: VoiceProfile,
        reference_path: Path,
        style: str,
        watermark_message: str,
    ) -> bytes:
        del style  # ToneColorConverter changes timbre; style remains a bounded pipeline capability hook.
        converter = self._ensure_loaded()
        target_se = self._target_embedding(profile, reference_path)
        with tempfile.TemporaryDirectory(prefix='vishnu-openvoice-') as directory:
            source_path = Path(directory) / 'source.wav'
            output_path = Path(directory) / 'converted.wav'
            source_path.write_bytes(source_wav)
            try:
                converter.convert(
                    audio_src_path=str(source_path),
                    src_se=self._source_se,
                    tgt_se=target_se,
                    output_path=str(output_path),
                    message=watermark_message,
                )
            except Exception as exc:
                raise VoiceConversionError('OpenVoice conversion failed') from exc
            if not output_path.is_file():
                raise VoiceConversionError('OpenVoice conversion produced no output')
            converted = output_path.read_bytes()
            if not converted:
                raise VoiceConversionError('OpenVoice conversion produced empty output')
            return converted


class VoiceConversionPipeline:
    """Governed post-TTS conversion with safe source-audio fallback."""

    def __init__(
        self,
        settings: VoiceConversionSettings,
        *,
        registry: VoiceProfileRegistry | None = None,
        provider: VoiceConversionProvider | None = None,
        event_sink: Callable[[str, dict], None] | None = None,
    ):
        self.settings = settings
        self.registry = registry or VoiceProfileRegistry(
            settings.profile_store,
            max_reference_bytes=settings.max_reference_bytes,
            max_reference_seconds=settings.max_reference_seconds,
        )
        self.provider = provider or OpenVoiceConverter(settings)
        self.event_sink = event_sink
        self._metrics = {'converted': 0, 'fallbacks': 0, 'failures': 0}
        self._lock = threading.RLock()

    @classmethod
    def from_settings(
        cls,
        settings,
        *,
        event_sink: Callable[[str, dict], None] | None = None,
    ) -> 'VoiceConversionPipeline':
        return cls(VoiceConversionSettings.from_settings(settings), event_sink=event_sink)

    def _emit(self, event: str, payload: dict) -> None:
        if self.event_sink is not None:
            self.event_sink(event, payload)

    def convert(
        self,
        source_wav: bytes,
        *,
        profile_id: str | None = None,
        style: str = 'normal',
    ) -> bytes:
        if not source_wav or not self.settings.enabled:
            return source_wav
        normalized_style = str(style or 'normal').strip().lower()
        if normalized_style not in ALLOWED_VOICE_STYLES:
            raise VoiceProfileError('unsupported voice style')
        selected_profile = str(profile_id or self.settings.default_profile_id).strip().lower()
        profile = self.registry.get(selected_profile, require_active=True)
        reference_path = self.registry.reference_path(profile)
        started = time.perf_counter()
        try:
            converted = self.provider.convert(
                source_wav,
                profile=profile,
                reference_path=reference_path,
                style=normalized_style,
                watermark_message=self.settings.watermark_message,
            )
        except VoiceConversionError as exc:
            with self._lock:
                self._metrics['failures'] += 1
            if not self.settings.fallback_to_source:
                raise
            with self._lock:
                self._metrics['fallbacks'] += 1
            self._emit(
                'voice.conversion.fallback',
                {
                    'profile_id': profile.profile_id,
                    'style': normalized_style,
                    'error_type': type(exc).__name__,
                },
            )
            return source_wav
        with self._lock:
            self._metrics['converted'] += 1
        self._emit(
            'voice.conversion.completed',
            {
                'profile_id': profile.profile_id,
                'style': normalized_style,
                'latency_ms': round((time.perf_counter() - started) * 1000, 3),
                'watermarked': bool(self.settings.watermark_message),
            },
        )
        return converted

    def status(self) -> dict:
        with self._lock:
            metrics = dict(self._metrics)
        active_profiles = []
        if self.settings.enabled:
            active_profiles = [profile.profile_id for profile in self.registry.list()]
        return {
            'enabled': self.settings.enabled,
            'provider': 'openvoice',
            'default_profile_id': self.settings.default_profile_id,
            'active_profiles': active_profiles,
            'fallback_to_source': self.settings.fallback_to_source,
            'metrics': metrics,
        }
