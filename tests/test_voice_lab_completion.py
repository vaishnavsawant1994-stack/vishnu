from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from voice.lab.benchmarks import BenchmarkEngine, acoustic_quality_score
from voice.lab.catalog import CapabilityState, find_capability, gaps
from voice.lab.comparison import ComparisonCandidate, ProviderComparison
from voice.lab.dashboard import VOICE_LAB_SECTIONS
from voice.lab.evidence import EvidenceStore
from voice.lab.experiments import VoiceExperimentSpec
from voice.lab.fixtures import FixtureRegistry
from voice.lab.runner import LabRunControl, VoiceExperimentRunner
from voice.lab.subprocess_adapter import BoundedSubprocessAdapter
from voice.lab.telephony import (
    CallState,
    TelephonyApproval,
    TelephonyCallRequest,
    TelephonyLab,
    TelephonyPolicy,
    TelephonyProviderResult,
    destination_fingerprint,
    looks_like_emergency_destination,
    masked_destination,
)


class SandboxTelephonyProvider:
    sandbox = True

    def __init__(self):
        self.calls = 0
        self.hangups = []

    def place_call(self, request, *, control, max_call_seconds):
        control.checkpoint()
        self.calls += 1
        assert max_call_seconds <= 300
        return TelephonyProviderResult(
            call_id="sandbox-call-1",
            connected=True,
            connect_latency_ms=120.0,
            duration_ms=500.0,
            recording_active=request.recording_requested,
            provider_reference="sandbox:1",
        )

    def hangup(self, call_id):
        self.hangups.append(call_id)
        return True


def _call_request(destination="+49 170 1234567", *, recording=False, consent=None):
    return TelephonyCallRequest(
        provider="sandbox",
        destination=destination,
        purpose="Voice Lab telephony qualification",
        recording_requested=recording,
        consent_reference=consent,
    )


def test_telephony_is_first_class_voice_lab_capability_and_section():
    capability = find_capability("telephony")
    assert capability is not None
    assert capability.state is CapabilityState.IMPLEMENTED
    assert "Telephony" in VOICE_LAB_SECTIONS
    assert "telephony" not in {item.capability_id for item in gaps()}


def test_telephony_defaults_fail_closed_and_never_contacts_provider():
    provider = SandboxTelephonyProvider()
    request = _call_request()
    approval = TelephonyApproval.for_request(request, owner_id="owner", attestation="approve exact sandbox call")
    run = TelephonyLab(providers={"sandbox": provider}).place_call(
        request,
        approval=approval,
        control=LabRunControl.bounded(5),
    )
    assert run.state is CallState.BLOCKED
    assert provider.calls == 0
    assert not run.qualified


def test_telephony_exact_owner_approval_allows_sandbox_call_without_leaking_destination():
    provider = SandboxTelephonyProvider()
    request = _call_request()
    policy = TelephonyPolicy(enabled=True, allow_outbound=True)
    approval = TelephonyApproval.for_request(request, owner_id="owner", attestation="approve exact sandbox call")
    run = TelephonyLab(policy=policy, providers={"sandbox": provider}).place_call(
        request,
        approval=approval,
        control=LabRunControl.bounded(5),
    )
    assert run.state is CallState.CONNECTED
    assert run.qualified
    assert provider.calls == 1
    metadata = run.evidence_metadata()
    rendered = json.dumps(metadata, sort_keys=True)
    assert request.destination not in rendered
    assert metadata["destination_sha256"] == destination_fingerprint(request.destination)
    assert metadata["destination_masked"] == masked_destination(request.destination)


def test_telephony_emergency_numbers_are_hard_blocked_inside_lab():
    provider = SandboxTelephonyProvider()
    request = _call_request("112")
    assert looks_like_emergency_destination(request.destination)
    approval = TelephonyApproval.for_request(request, owner_id="owner", attestation="attempt emergency qualification")
    run = TelephonyLab(
        policy=TelephonyPolicy(enabled=True, allow_outbound=True, allow_live_provider=True),
        providers={"sandbox": provider},
    ).place_call(request, approval=approval, control=LabRunControl.bounded(5))
    assert run.state is CallState.BLOCKED
    assert provider.calls == 0
    gate = next(item for item in run.gates if item.gate_id == "telephony-emergency-boundary")
    assert gate.status.value == "blocked"


def test_telephony_recording_requires_policy_consent_and_exact_approval():
    provider = SandboxTelephonyProvider()
    request = _call_request(recording=True, consent="consent:telephony-recording")
    approval_without_recording = TelephonyApproval.for_request(
        request,
        owner_id="owner",
        attestation="approve call but not recording",
        allow_recording=False,
    )
    lab = TelephonyLab(
        policy=TelephonyPolicy(enabled=True, allow_outbound=True, allow_recording=True),
        providers={"sandbox": provider},
    )
    blocked = lab.place_call(request, approval=approval_without_recording, control=LabRunControl.bounded(5))
    assert blocked.state is CallState.BLOCKED
    approval = TelephonyApproval.for_request(
        request,
        owner_id="owner",
        attestation="approve exact call and recording",
        allow_recording=True,
    )
    allowed = lab.place_call(request, approval=approval, control=LabRunControl.bounded(5))
    assert allowed.qualified
    assert allowed.result is not None and allowed.result.recording_active is True


def test_telephony_hangup_is_explicit_and_qualified():
    provider = SandboxTelephonyProvider()
    lab = TelephonyLab(
        policy=TelephonyPolicy(enabled=True, allow_outbound=True),
        providers={"sandbox": provider},
    )
    gate = lab.hangup("sandbox", "sandbox-call-1")
    assert gate.status.value == "pass"
    assert provider.hangups == ["sandbox-call-1"]


def test_provider_comparison_carries_privacy_hardware_cost_license_and_reliability():
    first = ComparisonCandidate(
        "local",
        ("clean-short",),
        (("wer", 0.05),),
        privacy="local-only",
        hardware="CPU",
        licensing="proprietary-compatible",
        cost="local-compute",
        reliability=(("success_rate", 0.99),),
    )
    second = ComparisonCandidate(
        "remote",
        ("clean-short",),
        (("wer", 0.04),),
        privacy="remote-processor",
        hardware="provider-managed",
        licensing="provider-terms",
        cost="metered",
        reliability=(("success_rate", 0.97),),
    )
    result = ProviderComparison((first, second), ("wer",), ("wer",)).evaluate()
    assert result["comparable"] is True
    assert result["context_complete"] is True
    assert result["context"]["local"]["privacy"] == "local-only"
    assert result["context"]["remote"]["cost"] == "metered"


def test_benchmark_engine_covers_reliability_resources_and_acoustics():
    engine = BenchmarkEngine()
    reliability = engine.reliability_metrics(
        successful_runs=99,
        total_runs=100,
        recovered_failures=19,
        provider_failures=20,
    )
    assert reliability["success_rate"] == 0.99
    assert reliability["failure_recovery_rate"] == 0.95
    resources = engine.resource_metrics(cpu_percent=35.0, memory_mb=256.0, peak_memory_mb=300.0)
    assert resources["cpu_percent"] == 35.0
    assert resources["peak_memory_mb"] == 300.0
    score = acoustic_quality_score(snr_db=30.0, clipping_ratio=0.0, dropped_ratio=0.0)
    assert score == 1.0
    acoustic = engine.acoustic_metrics(snr_db=30.0, clipping_ratio=0.0)
    assert acoustic["acoustic_quality_score"] == 1.0


def test_subprocess_adapter_hard_stops_child_when_deadline_expires(tmp_path):
    script = tmp_path / "slow_adapter.py"
    script.write_text(
        "import json,sys,time\n"
        "sys.stdin.read()\n"
        "time.sleep(5)\n"
        "print(json.dumps({'metrics': {}, 'gates': []}))\n",
        encoding="utf-8",
    )
    adapter = BoundedSubprocessAdapter((sys.executable, str(script.resolve())))
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    runner = VoiceExperimentRunner(
        fixtures=FixtureRegistry(),
        evidence=store,
        adapters={"subprocess": adapter},
    )
    spec = VoiceExperimentSpec(
        title="hard timeout qualification",
        provider="subprocess",
        model="test",
        device="desktop",
        language="en",
        fixture_refs=("clean-short",),
    )
    started = time.monotonic()
    run = runner.run(spec, timeout_seconds=0.15)
    elapsed = time.monotonic() - started
    assert elapsed < 2.5
    assert not run.report.is_qualified
    assert all(gate.status.value == "blocked" for gate in run.report.gates)


def test_new_voice_lab_modules_are_present():
    root = Path(__file__).resolve().parents[1]
    assert (root / "voice" / "lab" / "telephony.py").is_file()
    assert (root / "voice" / "lab" / "subprocess_adapter.py").is_file()
