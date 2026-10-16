from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from voice.conversion import (
    CANONICAL_PROFILE_ID,
    OpenVoiceConverter,
    VoiceConversionError,
    VoiceConversionPipeline,
    VoiceConversionSettings,
    VoiceProfileError,
    VoiceProfileRegistry,
)


def _wav_bytes(*, seconds: float = 0.25, rate: int = 16000) -> bytes:
    buffer = BytesIO()
    frames = max(1, int(seconds * rate))
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b'\x00\x00' * frames)
    return buffer.getvalue()


def _settings(tmp_path: Path, *, enabled: bool = True, fallback: bool = True):
    return VoiceConversionSettings(
        enabled=enabled,
        profile_store=tmp_path / 'profiles',
        default_profile_id='owner-voice',
        converter_config_path=None,
        converter_checkpoint_path=None,
        source_se_path=None,
        device='cpu',
        watermark_message='@VISHNU',
        fallback_to_source=fallback,
        max_reference_bytes=1024 * 1024,
        max_reference_seconds=10.0,
    )


class _FakeConverter:
    def __init__(self, result: bytes = b'converted', *, fail: bool = False):
        self.result = result
        self.fail = fail
        self.calls = []

    def convert(self, source_wav, *, profile, reference_path, style, watermark_message):
        self.calls.append(
            {
                'source_wav': source_wav,
                'profile_id': profile.profile_id,
                'reference_path': reference_path,
                'style': style,
                'watermark_message': watermark_message,
            }
        )
        if self.fail:
            raise VoiceConversionError('expected failure')
        return self.result


def _enroll(registry: VoiceProfileRegistry, profile_id: str = 'owner-voice'):
    return registry.enroll(
        _wav_bytes(),
        profile_id=profile_id,
        display_name='Owner voice',
        purpose='Personal Vishnu speech output',
        consent_attested=True,
    )


def test_enrollment_requires_explicit_consent(tmp_path):
    registry = VoiceProfileRegistry(tmp_path / 'profiles')
    with pytest.raises(VoiceProfileError, match='consent'):
        registry.enroll(
            _wav_bytes(),
            profile_id='owner-voice',
            display_name='Owner voice',
            purpose='Personal Vishnu speech output',
            consent_attested=False,
        )


def test_enrollment_rejects_non_wav_and_oversized_reference(tmp_path):
    registry = VoiceProfileRegistry(tmp_path / 'profiles', max_reference_bytes=4096)
    with pytest.raises(VoiceProfileError, match='valid WAV'):
        registry.enroll(
            b'not-a-wave-file',
            profile_id='owner-voice',
            display_name='Owner voice',
            purpose='Personal Vishnu speech output',
            consent_attested=True,
        )
    with pytest.raises(VoiceProfileError, match='size limit'):
        registry.enroll(
            _wav_bytes(seconds=1.0),
            profile_id='owner-voice',
            display_name='Owner voice',
            purpose='Personal Vishnu speech output',
            consent_attested=True,
        )


def test_profile_integrity_is_verified_before_use(tmp_path):
    registry = VoiceProfileRegistry(tmp_path / 'profiles')
    profile = _enroll(registry)
    registry.reference_path(profile).write_bytes(_wav_bytes(seconds=0.5))
    with pytest.raises(VoiceProfileError, match='integrity'):
        registry.reference_path(profile)


def test_revoked_profile_cannot_be_used(tmp_path):
    registry = VoiceProfileRegistry(tmp_path / 'profiles')
    _enroll(registry)
    registry.revoke('owner-voice')
    with pytest.raises(VoiceProfileError, match='revoked'):
        registry.get('owner-voice')


def test_canonical_vishnu_profile_is_protected(tmp_path):
    registry = VoiceProfileRegistry(tmp_path / 'profiles')
    registry.enroll(
        _wav_bytes(),
        profile_id=CANONICAL_PROFILE_ID,
        display_name='Vishnu',
        purpose='Canonical Vishnu voice',
        consent_attested=True,
        canonical=True,
    )
    with pytest.raises(VoiceProfileError, match='protected revocation'):
        registry.revoke(CANONICAL_PROFILE_ID)
    with pytest.raises(VoiceProfileError, match='protected deletion'):
        registry.delete(CANONICAL_PROFILE_ID)


def test_disabled_pipeline_is_exact_passthrough(tmp_path):
    settings = _settings(tmp_path, enabled=False)
    provider = _FakeConverter()
    pipeline = VoiceConversionPipeline(settings, provider=provider)
    source = _wav_bytes()
    assert pipeline.convert(source) == source
    assert provider.calls == []


def test_pipeline_uses_only_enrolled_profile_and_bounded_style(tmp_path):
    settings = _settings(tmp_path)
    registry = VoiceProfileRegistry(settings.profile_store)
    _enroll(registry)
    provider = _FakeConverter(result=b'voice-converted')
    events = []
    pipeline = VoiceConversionPipeline(
        settings,
        registry=registry,
        provider=provider,
        event_sink=lambda event, payload: events.append((event, payload)),
    )

    assert pipeline.convert(_wav_bytes(), style='warm') == b'voice-converted'
    assert provider.calls[0]['profile_id'] == 'owner-voice'
    assert provider.calls[0]['style'] == 'warm'
    assert provider.calls[0]['watermark_message'] == '@VISHNU'
    assert events[0][0] == 'voice.conversion.completed'

    with pytest.raises(VoiceProfileError, match='unsupported voice style'):
        pipeline.convert(_wav_bytes(), style='imitate-anyone')
    with pytest.raises(VoiceProfileError, match='does not exist'):
        pipeline.convert(_wav_bytes(), profile_id='unknown-voice')


def test_provider_failure_falls_back_without_changing_source_audio(tmp_path):
    settings = _settings(tmp_path, fallback=True)
    registry = VoiceProfileRegistry(settings.profile_store)
    _enroll(registry)
    provider = _FakeConverter(fail=True)
    events = []
    pipeline = VoiceConversionPipeline(
        settings,
        registry=registry,
        provider=provider,
        event_sink=lambda event, payload: events.append((event, payload)),
    )
    source = _wav_bytes()

    assert pipeline.convert(source) == source
    assert pipeline.status()['metrics'] == {'converted': 0, 'fallbacks': 1, 'failures': 1}
    assert events == [
        (
            'voice.conversion.fallback',
            {
                'profile_id': 'owner-voice',
                'style': 'normal',
                'error_type': 'VoiceConversionError',
            },
        )
    ]


def test_provider_failure_can_be_fail_closed(tmp_path):
    settings = _settings(tmp_path, fallback=False)
    registry = VoiceProfileRegistry(settings.profile_store)
    _enroll(registry)
    pipeline = VoiceConversionPipeline(settings, registry=registry, provider=_FakeConverter(fail=True))
    with pytest.raises(VoiceConversionError, match='expected failure'):
        pipeline.convert(_wav_bytes())


def test_remote_model_paths_are_rejected(tmp_path):
    raw = SimpleNamespace(
        data_dir=tmp_path,
        openvoice_converter_config='https://example.invalid/config.json',
    )
    with pytest.raises(VoiceProfileError, match='local path'):
        VoiceConversionSettings.from_settings(raw)


def test_openvoice_adapter_is_lazy_and_requires_local_models(tmp_path):
    settings = _settings(tmp_path)
    converter = OpenVoiceConverter(settings)
    registry = VoiceProfileRegistry(settings.profile_store)
    profile = _enroll(registry)
    with pytest.raises(VoiceConversionError, match='existing local file'):
        converter.convert(
            _wav_bytes(),
            profile=profile,
            reference_path=registry.reference_path(profile),
            style='normal',
            watermark_message='@VISHNU',
        )
