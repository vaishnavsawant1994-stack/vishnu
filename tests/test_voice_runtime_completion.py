from __future__ import annotations

import asyncio
import io
import wave
from hashlib import sha256

import pytest

from voice.config import VoiceRuntimeSettings
from voice.conversion import VoiceProfileError, VoiceProfileRegistry
from voice.device_output import TrustedVoiceOutputRouter
from voice.model_manager import LocalModelState, LocalVoiceModelManager
from voice.profile_archive import EncryptedVoiceSampleStore, VoiceProfileArchive
from voice.providers import ProviderHealth, SpeechToTextRequest, SpeechToTextResult
from voice.registry import ModelKind, ModelLicenseError, VoiceModelMetadata, VoiceModelRegistry
from voice.runtime import VoiceRuntime
from voice.scheduler import InferencePriority
from voice.sensorium import SpeechIntentBridge
from voice.streaming import ProgressiveVoiceStreamer, VoiceStreamState


def _wav_bytes(*, rate: int = 8_000, frames: int = 2_400, amplitude: int = 0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        sample = int(amplitude).to_bytes(2, "little", signed=True)
        audio.writeframes(sample * frames)
    return output.getvalue()


class FakeSTT:
    provider_id = "fake-stt"

    def health(self):
        return ProviderHealth(True)

    def capabilities(self):
        return {"languages": ["en"]}

    def transcribe(self, request):
        return SpeechToTextResult("turn on the lights", language="en", confidence=0.91)


class FakeGateway:
    def __init__(self):
        self.sent = []

    def online(self):
        return ["phone", "tablet"]

    def capabilities(self, device_id):
        if device_id == "phone":
            return ("voice.play_audio",)
        return ()

    async def send(self, device_id, command):
        self.sent.append((device_id, command))
        return {"queued": True, "request_id": command.request_id}


class FakeVoiceService:
    def __init__(self):
        self.chunks = []

    def synthesize(self, text, **kwargs):
        self.chunks.append((text, kwargs))
        return text.upper()


def test_scheduler_exposes_full_priority_order_and_legacy_aliases():
    assert list(
        map(
            int,
            (
                InferencePriority.EMERGENCY,
                InferencePriority.LIVE,
                InferencePriority.AGENT,
                InferencePriority.NOTIFICATION,
                InferencePriority.LONG_FORM,
            ),
        )
    ) == [0, 10, 20, 30, 40]
    assert InferencePriority.INTERACTIVE is InferencePriority.LIVE
    assert InferencePriority.NORMAL is InferencePriority.AGENT
    assert InferencePriority.BACKGROUND is InferencePriority.LONG_FORM


def test_model_registry_tracks_independent_code_and_weight_licenses():
    registry = VoiceModelRegistry()
    metadata = VoiceModelMetadata(
        model_id="voice-model",
        provider_id="local",
        kind=ModelKind.TTS,
        upstream="https://example.invalid/voice-model",
        license_id=None,
        code_license_id="MIT",
        weights_license_id="Apache-2.0",
        redistributable=True,
        commercial_use=True,
        artifact_sha256="0" * 64,
        languages=("en", "hi"),
        hardware=("cpu", "cuda"),
        revision="r1",
    )
    registry.register(metadata)
    assert registry.get("voice-model").effective_weights_license == "Apache-2.0"

    with pytest.raises(ModelLicenseError, match="weights license"):
        registry.register(
            VoiceModelMetadata(
                model_id="blocked-weights",
                provider_id="local",
                kind=ModelKind.TTS,
                upstream="https://example.invalid/blocked",
                license_id=None,
                code_license_id="MIT",
                weights_license_id="Unknown",
            )
        )


def test_local_model_manager_verifies_exact_local_artifact(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"voice-model-bytes")
    digest = sha256(artifact.read_bytes()).hexdigest()
    metadata = VoiceModelMetadata(
        model_id="local-verified",
        provider_id="local",
        kind=ModelKind.STT,
        upstream="https://example.invalid/local-verified",
        license_id="MIT",
        artifact_sha256=digest,
        size_bytes=artifact.stat().st_size,
        local_only=True,
    )
    manager = LocalVoiceModelManager(VoiceModelRegistry())
    status = manager.register_local(metadata, artifact)
    assert status.state is LocalModelState.READY
    assert manager.require_ready("local-verified") == artifact.resolve()

    artifact.write_bytes(b"tampered")
    assert manager.verify("local-verified").state is LocalModelState.SIZE_MISMATCH


def test_local_model_manager_rejects_remote_artifact_paths(tmp_path):
    metadata = VoiceModelMetadata(
        model_id="remote-path",
        provider_id="local",
        kind=ModelKind.STT,
        upstream="https://example.invalid/remote-path",
        license_id="MIT",
    )
    manager = LocalVoiceModelManager(VoiceModelRegistry())
    with pytest.raises(ValueError, match="local path"):
        manager.register_local(metadata, "https://example.invalid/model.bin")


def test_speech_intent_bridge_uses_sensorium_context_without_authority():
    bridge = SpeechIntentBridge()
    intent = bridge.from_transcription(
        SpeechToTextResult("hello Vishnu", language="en", confidence=0.8),
        source="phone-microphone",
        device_id="phone",
        audio_features={"label": "speech_likely", "confidence": 0.9, "speech": True},
    )
    assert intent.text == "hello Vishnu"
    assert intent.audio_context["label"] == "speech_likely"
    assert intent.audio_context["raw_audio_retained"] is False
    assert intent.execution_authority is False


def test_voice_runtime_can_return_sensorium_speech_intent(tmp_path):
    runtime = VoiceRuntime(
        settings=VoiceRuntimeSettings(enabled=True, workspace_root=tmp_path),
        stt_provider=FakeSTT(),
    )
    runtime.start()
    try:
        intent = runtime.transcribe_intent(
            SpeechToTextRequest(b"pcm"),
            source="desktop-voice",
            device_id="desktop",
            audio_features={"label": "speech_likely", "speech": True},
        )
    finally:
        runtime.stop()
    assert intent.text == "turn on the lights"
    assert intent.device_id == "desktop"
    assert intent.execution_authority is False


def test_trusted_device_output_requires_advertised_gateway_capability():
    gateway = FakeGateway()
    router = TrustedVoiceOutputRouter(gateway)
    assert router.available_devices() == ("phone",)
    result = asyncio.run(router.send_wav("phone", _wav_bytes(), request_id="req-1"))
    assert result["queued"] is True
    device_id, command = gateway.sent[0]
    assert device_id == "phone"
    assert command.action == "voice.play_audio"
    assert command.parameters["mime_type"] == "audio/wav"
    with pytest.raises(PermissionError):
        asyncio.run(router.send_wav("tablet", _wav_bytes()))


def test_progressive_streamer_reports_bounded_progress():
    service = FakeVoiceService()
    streamer = ProgressiveVoiceStreamer(service)
    progress = []
    output = list(
        streamer.synthesize(
            "First sentence. Second sentence.",
            max_chars=18,
            progress=progress.append,
            persona_id="vishnu-warm",
        )
    )
    assert output
    assert progress[0].state is VoiceStreamState.STARTED
    assert progress[-1].state is VoiceStreamState.COMPLETED
    assert progress[-1].fraction == 1.0
    assert all(item.total_chars >= item.completed_chars for item in progress)


def test_encrypted_multi_sample_profile_export_import_requires_fresh_consent(tmp_path):
    primary = _wav_bytes(amplitude=0)
    extra_one = _wav_bytes(amplitude=50)
    extra_two = _wav_bytes(amplitude=100)

    source_registry = VoiceProfileRegistry(tmp_path / "source-profiles")
    source_profile = source_registry.enroll(
        primary,
        display_name="Owner voice",
        purpose="Personal Vishnu speech output",
        consent_attested=True,
        profile_id="owner-voice",
    )
    source_samples = EncryptedVoiceSampleStore(
        tmp_path / "source-samples.vault",
        registry=source_registry,
        password="local-samples-password",
    )
    source_samples.put(
        source_profile.profile_id,
        (extra_one,),
        consent_attested=True,
        purpose=source_profile.purpose,
    )
    bundle = tmp_path / "owner-voice.bundle"
    VoiceProfileArchive(source_registry, sample_store=source_samples).export_profile(
        source_profile.profile_id,
        bundle,
        password="portable-export-password",
        extra_samples=(extra_two,),
    )
    encrypted_text = bundle.read_text()
    assert "ciphertext" in encrypted_text
    assert "audio_base64" not in encrypted_text

    target_registry = VoiceProfileRegistry(tmp_path / "target-profiles")
    target_samples = EncryptedVoiceSampleStore(
        tmp_path / "target-samples.vault",
        registry=target_registry,
        password="target-samples-password",
    )
    archive = VoiceProfileArchive(target_registry, sample_store=target_samples)
    with pytest.raises(VoiceProfileError, match="fresh explicit consent"):
        archive.import_profile(
            bundle,
            password="portable-export-password",
            consent_attested=False,
        )
    imported = archive.import_profile(
        bundle,
        password="portable-export-password",
        consent_attested=True,
        profile_id="imported-owner",
        purpose="Restored personal Vishnu speech output",
    )
    assert imported.active is True
    assert len(target_samples.get(imported.profile_id)) == 2
