from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from voice.lab.benchmarks import BenchmarkEngine, character_error_rate, word_error_rate
from voice.lab.comparison import ComparisonCandidate, ProviderComparison
from voice.lab.components import missing_modules, unregistered_modules
from voice.lab.dashboard import VOICE_LAB_SECTIONS, snapshot
from voice.lab.devices import DeviceClass, DeviceQualificationEvidence, physical_acoustics_gate
from voice.lab.evaluation import BASELINE_REQUIRED_GATES, GateStatus, passed_gate
from voice.lab.evidence import EvidenceRecord, EvidenceStore
from voice.lab.experiments import VoiceExperimentSpec
from voice.lab.fixtures import FixtureKind, FixtureRegistry, VoiceFixture, builtin_fixture_ids
from voice.lab.regression import MetricDirection, RegressionEngine, RegressionRule
from voice.lab.release import ReleaseManager
from voice.lab.runner import AdapterResult, VoiceExperimentRunner


class PassingAdapter:
    def run(self, spec, fixtures, workspace, *, deadline_monotonic):
        assert workspace.is_dir()
        assert fixtures
        metrics = (
            ("wer", 0.0),
            ("cer", 0.0),
            ("endpoint_latency_ms", 100.0),
            ("first_audio_latency_ms", 200.0),
            ("real_time_factor", 0.2),
            ("barge_in_latency_ms", 50.0),
            ("dropped_audio_blocks", 0.0),
            ("code_switch_retention", 1.0),
            ("pronunciation_accuracy", 1.0),
        )
        numeric = {item.gate_id for item in BenchmarkEngine().numeric_gates(dict(metrics))}
        gates = tuple(
            passed_gate(gate_id)
            for gate_id in BASELINE_REQUIRED_GATES
            if gate_id not in numeric
        )
        return AdapterResult(
            metrics=metrics,
            gates=gates,
            revision="test-revision",
            os_name="test-os",
            device_class="desktop_vm",
            provenance=(("fixture", "deterministic"),),
            artifacts=(("summary.json", b"{}"),),
        )


def _spec(provider="fake"):
    return VoiceExperimentSpec(
        title="operational qualification",
        provider=provider,
        model="test-model",
        device="test-device",
        language="en",
        fixture_refs=("clean-short",),
    )


def test_benchmarks_are_deterministic_and_dependency_light():
    assert word_error_rate("hello world", "hello world") == 0.0
    assert word_error_rate("hello world", "hello") == 0.5
    assert character_error_rate("abc", "abc") == 0.0
    gates = BenchmarkEngine().numeric_gates({"wer": 0.01})
    assert next(gate for gate in gates if gate.gate_id == "stt-wer").status is GateStatus.PASS
    assert next(gate for gate in gates if gate.gate_id == "stt-cer").status is GateStatus.BLOCKED


def test_fixture_registry_covers_required_scenarios_and_protects_sensitive_audio(tmp_path):
    kinds = {fixture.kind for fixture in FixtureRegistry().list()}
    assert kinds == set(FixtureKind)
    assert len(builtin_fixture_ids()) == len(set(builtin_fixture_ids()))
    with pytest.raises(ValueError):
        VoiceFixture("bad", FixtureKind.CLEAN, sensitive=True)
    path = (tmp_path / "owner.wav").resolve()
    fixture = VoiceFixture(
        "owner-consented",
        FixtureKind.CLEAN,
        local_audio_path=str(path),
        sensitive=True,
        consent_reference="consent:test",
    )
    assert fixture.sensitive
    with pytest.raises(ValueError):
        VoiceFixture("remote", FixtureKind.CLEAN, local_audio_path="https://example.com/audio.wav")


def test_runner_blocks_unregistered_provider_and_persists_evidence(tmp_path):
    store = EvidenceStore(tmp_path / "lab.sqlite3")
    run = VoiceExperimentRunner(fixtures=FixtureRegistry(), evidence=store).run(_spec("missing"))
    assert not run.report.is_qualified
    assert all(gate.status is GateStatus.BLOCKED for gate in run.report.gates)
    assert store.get(run.evidence_id)["experiment_id"] == run.report.experiment_id


def test_runner_qualifies_explicit_adapter_and_hashes_artifacts(tmp_path):
    store = EvidenceStore(tmp_path / "lab.sqlite3")
    runner = VoiceExperimentRunner(
        fixtures=FixtureRegistry(),
        evidence=store,
        adapters={"fake": PassingAdapter()},
    )
    run = runner.run(_spec())
    assert run.report.is_qualified
    row = store.get(run.evidence_id)
    assert row is not None
    assert row["artifact_digests"][0][0] == "summary.json"
    assert "raw_audio" not in str(row).casefold()


def test_evidence_and_baselines_are_append_only(tmp_path):
    store = EvidenceStore(tmp_path / "lab.sqlite3")
    run = VoiceExperimentRunner(
        fixtures=FixtureRegistry(),
        evidence=store,
        adapters={"fake": PassingAdapter()},
    ).run(_spec())
    store.accept_baseline("baseline-v1", run.evidence_id)
    assert store.baseline("baseline-v1")["evidence_id"] == run.evidence_id
    other = VoiceExperimentRunner(
        fixtures=FixtureRegistry(),
        evidence=store,
        adapters={"fake": PassingAdapter()},
    ).run(replace(_spec(), title="other run"))
    with pytest.raises(ValueError):
        store.accept_baseline("baseline-v1", other.evidence_id)


def test_provider_comparison_requires_identical_fixtures_and_complete_metrics():
    first = ComparisonCandidate("a", ("clean-short",), (("wer", 0.1),))
    second = ComparisonCandidate("b", ("clean-short",), (("wer", 0.2),))
    result = ProviderComparison((first, second), ("wer",), ("wer",)).evaluate()
    assert result["comparable"] is True
    assert result["winners"]["wer"] == "a"
    mismatch = replace(second, fixture_ids=("noise-metadata",))
    assert ProviderComparison((first, mismatch), ("wer",)).evaluate()["comparable"] is False


def test_regression_is_fail_closed_and_direction_aware():
    engine = RegressionEngine()
    rule = RegressionRule("wer", MetricDirection.LOWER, max_relative_degradation=0.1)
    assert engine.compare(None, {"wer": 0.1}, (rule,))[0].status == "blocked"
    assert engine.compare({"wer": 0.1}, {"wer": 0.2}, (rule,))[0].status == "fail"
    assert engine.compare({"wer": 0.1}, {"wer": 0.105}, (rule,))[0].status == "pass"


def test_simulator_or_vm_can_never_satisfy_physical_acoustics():
    for device_class in (DeviceClass.ANDROID_EMULATOR, DeviceClass.IOS_SIMULATOR, DeviceClass.DESKTOP_VM):
        gate = physical_acoustics_gate(
            DeviceQualificationEvidence(
                "device",
                device_class,
                "os",
                microphone_route="mic",
                speaker_route="speaker",
                bluetooth_tested=True,
                echo_tested=True,
                noise_tested=True,
                route_switch_tested=True,
                acoustic_latency_ms=20.0,
                attestation="fake physical-like fields",
            )
        )
        assert gate.status is GateStatus.BLOCKED


def test_complete_physical_evidence_can_pass_physical_gate():
    evidence = DeviceQualificationEvidence(
        "physical-1",
        DeviceClass.PHYSICAL,
        "mobile-os",
        microphone_route="built-in",
        speaker_route="built-in",
        bluetooth_tested=True,
        echo_tested=True,
        noise_tested=True,
        route_switch_tested=True,
        acoustic_latency_ms=80.0,
        attestation="signed-lab-evidence-reference",
    )
    assert physical_acoustics_gate(evidence).status is GateStatus.PASS


def test_release_candidate_requires_full_baseline_evidence_and_exact_owner_approval(tmp_path):
    store = EvidenceStore(tmp_path / "lab.sqlite3")
    run = VoiceExperimentRunner(
        fixtures=FixtureRegistry(),
        evidence=store,
        adapters={"fake": PassingAdapter()},
    ).run(_spec())
    manager = ReleaseManager(store)
    candidate = manager.prepare(("tts",), (run.evidence_id,))
    assert manager.evaluate(candidate, None).allowed is False
    approval = manager.approve(candidate, owner_id="owner", attestation="approve exact qualified candidate")
    assert manager.evaluate(candidate, approval).allowed is True
    tampered = replace(candidate, manifest_digest="0" * 64)
    assert manager.evaluate(tampered, approval).allowed is False


def test_release_rejects_partial_passing_evidence(tmp_path):
    store = EvidenceStore(tmp_path / "lab.sqlite3")
    record = EvidenceRecord.build(
        experiment_id="partial",
        provider="fake",
        model="model",
        device="device",
        language="en",
        route="canonical-stt-runtime-tts",
        gates=(passed_gate("stt-wer"),),
    )
    store.append(record)
    with pytest.raises(ValueError):
        ReleaseManager(store).prepare(("tts",), (record.evidence_id,))


def test_voice_lab_dashboard_has_all_owner_sections():
    required = {
        "Overview",
        "Conversation",
        "STT",
        "TTS",
        "Voice Profiles",
        "Voice Intelligence",
        "Multilingual",
        "Realtime",
        "Audio / Sensorium",
        "Devices",
        "Providers & Models",
        "Experiments",
        "Benchmarks",
        "Qualification",
        "Release",
    }
    assert set(VOICE_LAB_SECTIONS) == required
    assert snapshot().capabilities > 0


def test_every_voice_lab_module_is_registered_for_continuous_completeness():
    package_dir = Path(__file__).resolve().parents[1] / "voice" / "lab"
    assert unregistered_modules(package_dir) == ()
    assert missing_modules(package_dir) == ()


def test_owner_control_center_exposes_voice_lab_without_replacing_voice_studio():
    source = (Path(__file__).resolve().parents[1] / "ui" / "control_panel.py").read_text(encoding="utf-8")
    assert "Voice Studio" in source
    assert "Voice Lab" in source
    assert "VoiceLabDialog" in source
