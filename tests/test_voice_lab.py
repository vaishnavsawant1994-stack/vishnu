from __future__ import annotations

from pathlib import Path

import pytest

from voice.lab import (
    BASELINE_REQUIRED_GATES,
    CapabilityState,
    GateStatus,
    PromotionRequest,
    QualificationGate,
    VoiceExperimentSpec,
    VoiceLabReport,
    all_capabilities,
    evaluate_promotion,
    find_capability,
    gaps,
    passed_gate,
)


def _qualified_report(*, extra_gates: tuple[QualificationGate, ...] = ()) -> VoiceLabReport:
    return VoiceLabReport(
        experiment_id="voice-lab-test",
        provider="test-provider",
        model="test-model",
        device="test-device",
        language="en",
        gates=tuple(passed_gate(gate_id) for gate_id in BASELINE_REQUIRED_GATES) + extra_gates,
    )


def test_capability_catalog_is_unique_and_covers_every_major_voice_workstream() -> None:
    capabilities = all_capabilities()
    ids = [item.capability_id for item in capabilities]

    assert len(ids) == len(set(ids))
    assert {
        "microphone-capture",
        "adaptive-vad",
        "semantic-endpointing",
        "local-stt",
        "provider-stt",
        "canonical-runtime-bridge",
        "tts",
        "streaming-synthesis",
        "barge-in",
        "stale-output-rejection",
        "personas-and-styles",
        "bounded-affect-signals",
        "multilingual-planning",
        "code-switch-planning",
        "pronunciation-lexicon",
        "long-form-speech",
        "voice-profile-governance",
        "openvoice-conversion",
        "encrypted-profile-portability",
        "audio-quality-evaluator",
        "avatar-viseme-cues",
        "trusted-device-output",
        "openai-realtime-compatibility",
        "voicestudio-http",
        "voicestudio-mcp-governance",
        "media-transcription-intelligence",
        "sensorium-vision-voice",
        "environmental-audio",
        "model-license-provenance",
        "raw-audio-privacy",
        "provider-failure-isolation",
        "voice-runtime-configuration",
        "provider-contracts-registry",
        "voice-runtime-lifecycle",
        "voice-inference-scheduling",
        "sensorium-speech-intent-bridge",
        "wake-phrase",
        "telephony",
        "physical-device-acoustics",
        "provider-model-device-parity",
    } <= set(ids)


def test_every_top_level_voice_module_is_tracked_by_the_catalog() -> None:
    voice_modules = {
        path.as_posix()
        for path in Path("voice").glob("*.py")
        if path.name != "__init__.py"
    }
    covered_paths = {
        evidence_path
        for capability in all_capabilities()
        for evidence_path in capability.evidence_paths
        if evidence_path.endswith(".py")
    }

    assert voice_modules <= covered_paths


def test_unimplemented_telephony_is_explicitly_a_gap() -> None:
    telephony = find_capability("telephony")
    assert telephony is not None
    assert telephony.state is CapabilityState.GAP
    assert telephony in gaps()


def test_physical_device_acoustics_are_not_assumed_from_emulators() -> None:
    capability = find_capability("physical-device-acoustics")
    assert capability is not None
    assert capability.state is CapabilityState.QUALIFICATION_REQUIRED
    assert any("simulator" in note.lower() for note in capability.qualification_notes)


def test_missing_required_gate_fails_closed() -> None:
    report = VoiceLabReport(
        experiment_id="missing-gate",
        provider="provider",
        model="model",
        device="device",
        language="en",
        gates=(passed_gate(BASELINE_REQUIRED_GATES[0]),),
    )

    assert not report.is_qualified
    assert BASELINE_REQUIRED_GATES[1] in report.missing_gate_ids


def test_failed_gate_blocks_qualification() -> None:
    gates = [passed_gate(gate_id) for gate_id in BASELINE_REQUIRED_GATES]
    failed_id = "barge-in-cancellation-latency"
    gates[BASELINE_REQUIRED_GATES.index(failed_id)] = QualificationGate(
        gate_id=failed_id,
        status=GateStatus.FAIL,
        observed="too slow",
    )
    report = VoiceLabReport(
        experiment_id="failed-gate",
        provider="provider",
        model="model",
        device="device",
        language="en",
        gates=tuple(gates),
    )

    assert not report.is_qualified
    assert failed_id in report.non_passing_gate_ids


def test_duplicate_required_gate_fails_closed() -> None:
    gates = tuple(passed_gate(gate_id) for gate_id in BASELINE_REQUIRED_GATES)
    report = VoiceLabReport(
        experiment_id="duplicate-gate",
        provider="provider",
        model="model",
        device="device",
        language="en",
        gates=gates + (passed_gate(BASELINE_REQUIRED_GATES[0]),),
    )

    assert not report.is_qualified
    assert BASELINE_REQUIRED_GATES[0] in report.missing_gate_ids


def test_experiment_ids_are_deterministic_and_raw_audio_retention_is_off_by_default() -> None:
    first = VoiceExperimentSpec(
        title="English desktop baseline",
        provider="local",
        model="model-a",
        device="desktop",
        language="en",
        fixture_refs=("fixtures/voice/en-001.wav",),
    )
    second = VoiceExperimentSpec(
        title="English desktop baseline",
        provider="local",
        model="model-a",
        device="desktop",
        language="en",
        fixture_refs=("fixtures/voice/en-001.wav",),
    )

    assert first.experiment_id == second.experiment_id
    assert not first.retain_raw_audio
    assert first.raw_audio_retention_seconds == 0


def test_raw_audio_retention_requires_explicit_bounded_consent() -> None:
    with pytest.raises(ValueError, match="consent"):
        VoiceExperimentSpec(
            title="unsafe retention",
            provider="local",
            model="model-a",
            device="desktop",
            language="en",
            retain_raw_audio=True,
            raw_audio_retention_seconds=60,
        )


def test_voice_biometric_experiment_requires_explicit_consent() -> None:
    with pytest.raises(ValueError, match="consent"):
        VoiceExperimentSpec(
            title="voice profile evaluation",
            provider="local",
            model="model-a",
            device="desktop",
            language="en",
            contains_voice_biometrics=True,
        )


def test_promotion_never_allows_a_known_gap() -> None:
    decision = evaluate_promotion(
        PromotionRequest(target_capability_ids=("telephony",), manual_owner_approval=True),
        _qualified_report(),
    )

    assert not decision.allowed
    assert any("gap" in reason for reason in decision.reasons)


def test_promotion_requires_manual_owner_approval() -> None:
    decision = evaluate_promotion(
        PromotionRequest(target_capability_ids=("tts",)),
        _qualified_report(),
    )

    assert not decision.allowed
    assert any("manual owner approval" in reason for reason in decision.reasons)


def test_qualified_existing_capability_can_pass_promotion_policy_after_manual_approval() -> None:
    decision = evaluate_promotion(
        PromotionRequest(target_capability_ids=("tts",), manual_owner_approval=True),
        _qualified_report(),
    )

    assert decision.allowed
    assert not decision.reasons


def test_physical_device_promotion_requires_real_physical_gate() -> None:
    without_physical_evidence = evaluate_promotion(
        PromotionRequest(
            target_capability_ids=("physical-device-acoustics",),
            manual_owner_approval=True,
            targets_physical_device=True,
        ),
        _qualified_report(),
    )
    assert not without_physical_evidence.allowed

    with_physical_evidence = evaluate_promotion(
        PromotionRequest(
            target_capability_ids=("physical-device-acoustics",),
            manual_owner_approval=True,
            targets_physical_device=True,
        ),
        _qualified_report(extra_gates=(passed_gate("physical-device-acoustics"),)),
    )
    assert with_physical_evidence.allowed


def test_noncanonical_voice_authority_requires_explicit_architecture_review() -> None:
    blocked = evaluate_promotion(
        PromotionRequest(
            target_capability_ids=("openai-realtime-compatibility",),
            manual_owner_approval=True,
            changes_canonical_authority=True,
        ),
        _qualified_report(),
    )
    assert not blocked.allowed
    assert any("architecture/security review" in reason for reason in blocked.reasons)

    reviewed = evaluate_promotion(
        PromotionRequest(
            target_capability_ids=("openai-realtime-compatibility",),
            manual_owner_approval=True,
            changes_canonical_authority=True,
            architecture_review_approved=True,
        ),
        _qualified_report(),
    )
    assert reviewed.allowed


def test_report_rejects_duplicate_required_gate_ids() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        VoiceLabReport(
            experiment_id="duplicate-required",
            provider="provider",
            model="model",
            device="device",
            language="en",
            gates=(passed_gate("a"),),
            required_gate_ids=("a", "a"),
        )


def test_experiment_metadata_is_immutable_and_part_of_identity() -> None:
    first = VoiceExperimentSpec(
        title="metadata",
        provider="local",
        model="model-a",
        device="desktop",
        language="en",
        metadata=(("revision", "abc123"),),
    )
    second = VoiceExperimentSpec(
        title="metadata",
        provider="local",
        model="model-a",
        device="desktop",
        language="en",
        metadata=(("revision", "def456"),),
    )

    assert first.experiment_id != second.experiment_id
