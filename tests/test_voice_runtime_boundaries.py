from __future__ import annotations

import threading
from pathlib import Path

import pytest

from voice.config import VoiceRuntimeSettings
from voice.providers import (
    ProviderHealth,
    SpeechToTextRequest,
    SpeechToTextResult,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from voice.registry import ModelKind, ModelLicenseError, VoiceModelMetadata, VoiceModelRegistry
from voice.runtime import VoiceRuntime, VoiceRuntimeState
from voice.scheduler import InferencePriority, InferenceScheduler


class FakeSTT:
    provider_id = "fake-stt"

    def health(self):
        return ProviderHealth(True)

    def capabilities(self):
        return {"languages": ["en"]}

    def transcribe(self, request):
        return SpeechToTextResult(text=f"bytes:{len(request.audio)}", language=request.language)


class FakeTTS:
    provider_id = "fake-tts"

    def health(self):
        return ProviderHealth(True)

    def capabilities(self):
        return {"voices": ["test"]}

    def synthesize(self, request):
        return TextToSpeechResult(audio=request.text.encode(), sample_rate_hz=24_000)


def test_runtime_is_default_off_and_allocates_nothing(monkeypatch):
    monkeypatch.delenv("VISHNU_VOICE_RUNTIME_ENABLED", raising=False)
    runtime = VoiceRuntime()
    assert runtime.settings.enabled is False
    assert runtime.start() is False
    assert runtime.state is VoiceRuntimeState.STOPPED
    assert runtime.workspace is None


def test_runtime_creates_isolated_workspace_and_cleans_it(tmp_path):
    settings = VoiceRuntimeSettings(enabled=True, workspace_root=tmp_path)
    first = VoiceRuntime(settings=settings)
    second = VoiceRuntime(settings=settings)
    assert first.start() is True
    assert second.start() is True
    first_workspace = first.workspace
    second_workspace = second.workspace
    assert isinstance(first_workspace, Path) and first_workspace.exists()
    assert isinstance(second_workspace, Path) and second_workspace.exists()
    assert first_workspace != second_workspace
    first.stop()
    second.stop()
    assert not first_workspace.exists()
    assert not second_workspace.exists()
    assert first.state is VoiceRuntimeState.STOPPED


def test_runtime_executes_formal_provider_contracts(tmp_path):
    runtime = VoiceRuntime(
        settings=VoiceRuntimeSettings(enabled=True, workspace_root=tmp_path),
        stt_provider=FakeSTT(),
        tts_provider=FakeTTS(),
    )
    runtime.start()
    assert runtime.transcribe(SpeechToTextRequest(b"abc", language="en")).text == "bytes:3"
    assert runtime.synthesize(TextToSpeechRequest("hello")).audio == b"hello"
    runtime.stop()


def test_legacy_streaming_api_does_not_require_new_runtime():
    runtime = VoiceRuntime(settings=VoiceRuntimeSettings(enabled=False))
    assert runtime.push_pcm(b"x") is False
    runtime.start_listening()
    assert runtime.push_pcm(b"x") is True
    runtime.stop_listening()


def test_registry_rejects_unknown_license_by_default():
    registry = VoiceModelRegistry()
    model = VoiceModelMetadata(
        model_id="unknown-model",
        provider_id="provider",
        kind=ModelKind.TTS,
        upstream="https://example.invalid/model",
        license_id=None,
    )
    with pytest.raises(ModelLicenseError):
        registry.register(model)


def test_registry_tracks_license_and_usage_constraints():
    registry = VoiceModelRegistry()
    model = VoiceModelMetadata(
        model_id="safe-model",
        provider_id="provider",
        kind=ModelKind.STT,
        upstream="https://example.invalid/model",
        license_id="MIT",
        redistributable=False,
        commercial_use=True,
    )
    registry.register(model)
    assert registry.get("safe-model") is model
    registry.validate_license(model, require_commercial=True)
    with pytest.raises(ModelLicenseError):
        registry.validate_license(model, require_redistribution=True)


def test_scheduler_prioritizes_interactive_work():
    scheduler = InferenceScheduler(max_workers=1, max_pending=4)
    gate = threading.Event()
    order = []
    scheduler.start()
    first = scheduler.submit(lambda: gate.wait(1), priority=InferencePriority.NORMAL)
    background = scheduler.submit(lambda: order.append("background"), priority=InferencePriority.BACKGROUND)
    interactive = scheduler.submit(lambda: order.append("interactive"), priority=InferencePriority.INTERACTIVE)
    gate.set()
    first.result(timeout=2)
    interactive.result(timeout=2)
    background.result(timeout=2)
    scheduler.shutdown()
    assert order == ["interactive", "background"]


def test_scheduler_is_bounded():
    scheduler = InferenceScheduler(max_workers=1, max_pending=1)
    gate = threading.Event()
    started = threading.Event()

    def blocking():
        started.set()
        gate.wait(1)

    scheduler.start()
    running = scheduler.submit(blocking)
    assert started.wait(1)
    pending = scheduler.submit(lambda: None)
    with pytest.raises(RuntimeError, match="queue is full"):
        scheduler.submit(lambda: None)
    gate.set()
    running.result(timeout=2)
    pending.result(timeout=2)
    scheduler.shutdown()


def test_scheduler_cancels_pending_jobs_on_shutdown():
    scheduler = InferenceScheduler(max_workers=1, max_pending=2)
    gate = threading.Event()
    started = threading.Event()

    def blocking():
        started.set()
        gate.wait(1)

    scheduler.start()
    running = scheduler.submit(blocking)
    assert started.wait(1)
    pending = scheduler.submit(lambda: "should-not-run")
    gate.set()
    scheduler.shutdown(wait=True, cancel_pending=True)
    running.result(timeout=2)
    assert pending.cancelled()
