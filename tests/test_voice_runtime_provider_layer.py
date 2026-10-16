from __future__ import annotations

import asyncio

import pytest

from voice.bootstrap import build_voice_runtime
from voice.chunking import chunk_speech_text
from voice.governance import (
    VoiceConsentError,
    VoiceConsentRecord,
    VoiceSampleProvenance,
    VoiceSourceKind,
    VoiceStoragePolicy,
    assert_sample_usable_for_clone,
)
from voice.intelligence import VoicePlan, VoiceRouteRequirements
from voice.model_registry import ModelCapability, ModelPolicyError, VoiceModelRegistry, VoiceModelSpec
from voice.plan_adapter import priority_from_plan, synthesis_request_from_plan
from voice.providers import CallableTTSProvider, SynthesisRequest, SynthesisResult
from voice.runtime_service import VoiceRuntimeDisabledError, VoiceRuntimeService, voice_runtime_enabled
from voice.scheduler import VoiceInferenceScheduler, VoicePriority


def _tts_spec(*, commercial_allowed: bool = True) -> VoiceModelSpec:
    return VoiceModelSpec(
        model_id="test-tts",
        provider_id="test-provider",
        version="1",
        capabilities=frozenset({ModelCapability.TTS}),
        code_license="MIT",
        weights_license="test-license",
        commercial_allowed=commercial_allowed,
        redistribution_allowed=False,
        supported_languages=("en",),
        hardware=("cpu",),
    )


def test_voice_runtime_is_disabled_by_default() -> None:
    assert voice_runtime_enabled({}) is False

    registry = VoiceModelRegistry()
    registry.register(_tts_spec())
    called = False

    async def synthesize(_request: SynthesisRequest) -> SynthesisResult:
        nonlocal called
        called = True
        return SynthesisResult(audio=b"unused", sample_rate_hz=24_000)

    runtime = VoiceRuntimeService(enabled=False, registry=registry)
    runtime.register_tts_provider(CallableTTSProvider("test-provider", synthesize))

    async def scenario() -> None:
        with pytest.raises(VoiceRuntimeDisabledError):
            await runtime.synthesize(SynthesisRequest(text="hello", model_id="test-tts"))

    asyncio.run(scenario())
    assert called is False
    assert runtime.health()["scheduler_running"] is False


def test_bootstrap_composes_without_activating_runtime() -> None:
    called = False

    async def synthesize(_request: SynthesisRequest) -> SynthesisResult:
        nonlocal called
        called = True
        return SynthesisResult(audio=b"unused", sample_rate_hz=24_000)

    runtime = build_voice_runtime(
        env={},
        models=(_tts_spec(),),
        tts_providers=(CallableTTSProvider("test-provider", synthesize),),
    )
    assert runtime.health() == {
        "enabled": False,
        "started": False,
        "closed": False,
        "commercial_mode": True,
        "scheduler_running": False,
        "scheduler_pending": 0,
        "tts_providers": ["test-provider"],
        "stt_providers": [],
        "models": ["test-tts"],
    }
    assert called is False


def test_model_registry_fails_closed_for_noncommercial_model() -> None:
    registry = VoiceModelRegistry()
    registry.register(_tts_spec(commercial_allowed=False))

    with pytest.raises(ModelPolicyError, match="commercial use"):
        registry.assert_usable("test-tts", capability=ModelCapability.TTS, commercial_mode=True)

    assert registry.assert_usable(
        "test-tts", capability=ModelCapability.TTS, commercial_mode=False
    ).model_id == "test-tts"


def test_scheduler_serializes_and_prioritizes_queued_work() -> None:
    async def scenario() -> None:
        scheduler = VoiceInferenceScheduler()
        order: list[str] = []
        active = 0
        max_active = 0

        async def operation(name: str) -> str:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            order.append(name)
            await asyncio.sleep(0)
            active -= 1
            return name

        low = asyncio.create_task(
            scheduler.submit(VoicePriority.LONG_FORM, lambda: operation("long-form"))
        )
        high = asyncio.create_task(
            scheduler.submit(VoicePriority.LIVE_CONVERSATION, lambda: operation("live"))
        )
        await asyncio.sleep(0)
        await scheduler.start()
        assert set(await asyncio.gather(low, high)) == {"long-form", "live"}
        assert order == ["live", "long-form"]
        assert max_active == 1
        await scheduler.close()

    asyncio.run(scenario())


def test_runtime_routes_through_registered_provider_without_logging_content() -> None:
    registry = VoiceModelRegistry()
    registry.register(_tts_spec())
    events: list[tuple[str, dict]] = []

    async def synthesize(request: SynthesisRequest) -> SynthesisResult:
        assert request.text == "private spoken text"
        return SynthesisResult(audio=b"wav", sample_rate_hz=24_000, metadata={"engine": "fake"})

    runtime = VoiceRuntimeService(
        enabled=True,
        registry=registry,
        audit_hook=lambda event, metadata: events.append((event, dict(metadata))),
    )
    runtime.register_tts_provider(CallableTTSProvider("test-provider", synthesize))

    async def scenario() -> None:
        result = await runtime.synthesize(
            SynthesisRequest(text="private spoken text", model_id="test-tts", language="en")
        )
        assert result.audio == b"wav"
        assert result.sample_rate_hz == 24_000
        await runtime.close()

    asyncio.run(scenario())
    assert any(event == "voice.synthesis_completed" for event, _metadata in events)
    assert all("private spoken text" not in str(metadata) for _event, metadata in events)


def test_long_form_synthesis_uses_bounded_chunks_and_preserves_order() -> None:
    registry = VoiceModelRegistry()
    registry.register(_tts_spec())
    seen: list[str] = []

    async def synthesize(request: SynthesisRequest) -> SynthesisResult:
        seen.append(request.text)
        assert "long_form_chunk_index" in request.intent
        return SynthesisResult(audio=request.text.encode(), sample_rate_hz=24_000)

    runtime = VoiceRuntimeService(enabled=True, registry=registry)
    runtime.register_tts_provider(CallableTTSProvider("test-provider", synthesize))
    text = " ".join(["This sentence is suitable for long form speech."] * 12)

    async def scenario() -> None:
        results = await runtime.synthesize_long_form(
            SynthesisRequest(text=text, model_id="test-tts", language="en"),
            max_chunk_characters=120,
        )
        assert len(results) == len(seen) > 1
        assert " ".join(seen) == text
        await runtime.close()

    asyncio.run(scenario())


def test_voice_clone_requires_matching_active_consent_and_defaults_device_only() -> None:
    consent = VoiceConsentRecord(
        consent_id="consent-1",
        subject_id="owner",
        granted_by_owner=True,
        allows_voice_cloning=True,
    )
    sample = VoiceSampleProvenance(
        sample_id="sample-1",
        subject_id="owner",
        source_kind=VoiceSourceKind.OWNER_RECORDING,
        consent_id="consent-1",
        content_hash="sha256:abc",
    )
    assert sample.storage_policy is VoiceStoragePolicy.DEVICE_ONLY
    assert_sample_usable_for_clone(sample, consent)

    mismatched = VoiceConsentRecord(
        consent_id="consent-2",
        subject_id="owner",
        granted_by_owner=True,
        allows_voice_cloning=True,
    )
    with pytest.raises(VoiceConsentError):
        assert_sample_usable_for_clone(sample, mismatched)


def test_voice_intelligence_plan_bridges_without_replacing_intelligence_authority() -> None:
    plan = VoicePlan(
        persona_id="vishnu_original",
        voice_profile_id="owner_voice",
        style="urgent",
        style_source="context",
        language="en",
        speaking_rate=1.05,
        pitch=0.0,
        energy=1.2,
        formality=0.6,
        avatar_expression="alert",
        character_id=None,
        route=VoiceRouteRequirements(language="en", streaming_preferred=True),
    )
    request = synthesis_request_from_plan(text="Build complete", model_id="test-tts", plan=plan)

    assert request.profile_id == "owner_voice"
    assert request.intent["style"] == "urgent"
    assert request.intent["speaking_rate"] == 1.05
    assert priority_from_plan(plan) is VoicePriority.EMERGENCY


def test_long_form_chunking_is_bounded_and_preserves_content_order() -> None:
    text = "First sentence. Second sentence is longer. Third sentence finishes the sample."
    chunks = chunk_speech_text(text, max_characters=100)
    assert chunks == (text,)

    repeated = " ".join(["A sentence that can be spoken clearly."] * 20)
    chunks = chunk_speech_text(repeated, max_characters=120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert " ".join(chunks) == repeated
