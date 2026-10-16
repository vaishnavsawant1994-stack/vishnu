"""Explicit, cancellable, adapter-injected Voice Lab experiment runner."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from typing import Protocol

from .benchmarks import BenchmarkEngine
from .evaluation import GateStatus, QualificationGate, VoiceLabReport
from .evidence import EvidenceRecord, EvidenceStore
from .experiments import VoiceExperimentSpec
from .fixtures import FixtureRegistry, VoiceFixture
from .regression import RegressionEngine


class LabRunCancelled(RuntimeError):
    pass


class LabRunTimedOut(RuntimeError):
    pass


class LabRunControl:
    """Cooperative stop authority shared with explicitly registered Lab adapters."""

    def __init__(self, deadline_monotonic: float, cancel_event: threading.Event | None = None):
        self.deadline_monotonic = deadline_monotonic
        self._cancel_event = cancel_event or threading.Event()

    @classmethod
    def bounded(cls, timeout_seconds: float) -> "LabRunControl":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        return cls(time.monotonic() + timeout_seconds)

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def timed_out(self) -> bool:
        return time.monotonic() >= self.deadline_monotonic

    def checkpoint(self) -> None:
        if self.cancelled:
            raise LabRunCancelled("Voice Lab experiment was cancelled")
        if self.timed_out:
            raise LabRunTimedOut("Voice Lab experiment exceeded its bounded deadline")


@dataclass(frozen=True, slots=True)
class AdapterResult:
    metrics: tuple[tuple[str, float], ...] = ()
    gates: tuple[QualificationGate, ...] = ()
    artifacts: tuple[tuple[str, bytes], ...] = ()
    revision: str = ""
    os_name: str = ""
    device_class: str = "unknown"
    provenance: tuple[tuple[str, str], ...] = ()


class LabAdapter(Protocol):
    def run(
        self,
        spec: VoiceExperimentSpec,
        fixtures: tuple[VoiceFixture, ...],
        workspace: Path,
        *,
        control: LabRunControl,
    ) -> AdapterResult: ...


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    report: VoiceLabReport
    evidence_id: str
    metrics: tuple[tuple[str, float], ...]
    regressions: tuple[tuple[str, str], ...] = ()


class VoiceExperimentRunner:
    """Runs only explicitly injected Lab adapters; it never imports production providers."""

    _SENSITIVE_CONFIG_TOKENS = ("token", "secret", "password", "api_key", "apikey", "authorization", "bearer")

    def __init__(
        self,
        *,
        fixtures: FixtureRegistry,
        evidence: EvidenceStore,
        adapters: dict[str, LabAdapter] | None = None,
        benchmarks: BenchmarkEngine | None = None,
        regressions: RegressionEngine | None = None,
    ):
        self.fixtures = fixtures
        self.evidence = evidence
        self.adapters = dict(adapters or {})
        self.benchmarks = benchmarks or BenchmarkEngine()
        self.regressions = regressions or RegressionEngine()

    @staticmethod
    def new_control(timeout_seconds: float = 120.0) -> LabRunControl:
        return LabRunControl.bounded(timeout_seconds)

    def run(
        self,
        spec: VoiceExperimentSpec,
        *,
        timeout_seconds: float = 120.0,
        control: LabRunControl | None = None,
    ) -> ExperimentRun:
        control = control or self.new_control(timeout_seconds)
        resolved = self.fixtures.resolve(spec.fixture_refs)
        adapter = self.adapters.get(spec.provider)
        if adapter is None:
            gates = self._blocked_gates(spec, f"no explicit Lab adapter registered for provider {spec.provider}")
            return self._persist(spec, AdapterResult(gates=gates), gates)
        workspace = Path(tempfile.mkdtemp(prefix="vishnu-voice-lab-"))
        try:
            control.checkpoint()
            result = adapter.run(spec, resolved, workspace, control=control)
            control.checkpoint()
            metric_gates = {gate.gate_id: gate for gate in self.benchmarks.numeric_gates(dict(result.metrics))}
            explicit = {gate.gate_id: gate for gate in result.gates}
            gates = []
            for gate_id in spec.required_gate_ids:
                gates.append(
                    explicit.get(gate_id)
                    or metric_gates.get(gate_id)
                    or QualificationGate(gate_id, GateStatus.BLOCKED, notes="required evidence not produced")
                )
            baseline = self.evidence.baseline(spec.baseline_key)
            regression_summary = ()
            report_required = spec.required_gate_ids
            if baseline is not None:
                regression_gate, findings = self.regressions.qualification_gate(
                    dict(baseline.get("metrics", ())),
                    dict(result.metrics),
                )
                gates.append(regression_gate)
                report_required = (*report_required, "baseline-regression")
                regression_summary = tuple((item.metric, item.status) for item in findings)
            return self._persist(spec, result, tuple(gates), regression_summary, report_required)
        except LabRunCancelled:
            gates = self._blocked_gates(spec, "experiment cancelled; adapter must stop at control checkpoints")
            return self._persist(spec, AdapterResult(gates=gates), gates)
        except LabRunTimedOut:
            gates = self._blocked_gates(spec, "experiment exceeded bounded deadline")
            return self._persist(spec, AdapterResult(gates=gates), gates)
        except Exception as exc:
            gates = self._blocked_gates(spec, f"adapter failure: {type(exc).__name__}")
            return self._persist(spec, AdapterResult(gates=gates), gates)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def _blocked_gates(spec: VoiceExperimentSpec, notes: str) -> tuple[QualificationGate, ...]:
        return tuple(QualificationGate(gate_id, GateStatus.BLOCKED, notes=notes) for gate_id in spec.required_gate_ids)

    @classmethod
    def _configuration(cls, spec: VoiceExperimentSpec) -> dict[str, str]:
        config = {
            "style": spec.style,
            "required_gate_ids": json.dumps(spec.required_gate_ids),
            "retain_raw_audio": str(spec.retain_raw_audio).lower(),
            "raw_audio_retention_seconds": str(spec.raw_audio_retention_seconds),
            "contains_voice_biometrics": str(spec.contains_voice_biometrics).lower(),
        }
        if spec.consent_reference:
            config["consent_reference_sha256"] = hashlib.sha256(spec.consent_reference.encode()).hexdigest()
        for key, value in spec.metadata:
            if any(token in key.casefold() for token in cls._SENSITIVE_CONFIG_TOKENS):
                config[f"metadata:{key}:sha256"] = hashlib.sha256(value.encode()).hexdigest()
            else:
                config[f"metadata:{key}"] = value
        return config

    def _persist(
        self,
        spec: VoiceExperimentSpec,
        result: AdapterResult,
        gates: tuple[QualificationGate, ...],
        regression_summary: tuple[tuple[str, str], ...] = (),
        report_required_gate_ids: tuple[str, ...] | None = None,
    ) -> ExperimentRun:
        artifacts = {name: hashlib.sha256(body).hexdigest() for name, body in result.artifacts}
        record = EvidenceRecord.build(
            experiment_id=spec.experiment_id,
            baseline_key=spec.baseline_key,
            provider=spec.provider,
            model=spec.model,
            revision=result.revision,
            device=spec.device,
            device_class=result.device_class,
            os_name=result.os_name,
            language=spec.language,
            route=spec.route,
            fixture_refs=spec.fixture_refs,
            configuration=self._configuration(spec),
            provenance=dict(result.provenance),
            metrics=dict(result.metrics),
            gates=gates,
            regression_summary=regression_summary,
            artifact_digests=artifacts,
        )
        self.evidence.append(record)
        required = report_required_gate_ids or spec.required_gate_ids
        report = VoiceLabReport(
            spec.experiment_id,
            spec.provider,
            spec.model,
            spec.device,
            spec.language,
            tuple(gate for gate in gates if gate.gate_id in required),
            required,
        )
        return ExperimentRun(report, record.evidence_id, result.metrics, regression_summary)
