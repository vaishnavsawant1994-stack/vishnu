"""Explicit, adapter-injected Voice Lab experiment runner."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import tempfile
import time
from typing import Protocol

from .benchmarks import BenchmarkEngine
from .evaluation import GateStatus, QualificationGate, VoiceLabReport
from .evidence import EvidenceRecord, EvidenceStore
from .experiments import VoiceExperimentSpec
from .fixtures import FixtureRegistry, VoiceFixture


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
    def run(self, spec: VoiceExperimentSpec, fixtures: tuple[VoiceFixture, ...], workspace: Path,
            *, deadline_monotonic: float) -> AdapterResult: ...


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    report: VoiceLabReport
    evidence_id: str
    metrics: tuple[tuple[str, float], ...]


class VoiceExperimentRunner:
    """Runs only explicitly injected Lab adapters; it never imports production providers."""
    def __init__(self, *, fixtures: FixtureRegistry, evidence: EvidenceStore,
                 adapters: dict[str, LabAdapter] | None = None, benchmarks: BenchmarkEngine | None = None):
        self.fixtures=fixtures; self.evidence=evidence; self.adapters=dict(adapters or {}); self.benchmarks=benchmarks or BenchmarkEngine()

    def run(self, spec: VoiceExperimentSpec, *, timeout_seconds: float = 120.0) -> ExperimentRun:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        resolved=self.fixtures.resolve(spec.fixture_refs)
        adapter=self.adapters.get(spec.provider)
        if adapter is None:
            gates=tuple(QualificationGate(g, GateStatus.BLOCKED, notes=f"no explicit Lab adapter registered for provider {spec.provider}") for g in spec.required_gate_ids)
            return self._persist(spec, AdapterResult(gates=gates), gates)
        workspace=Path(tempfile.mkdtemp(prefix="vishnu-voice-lab-"))
        try:
            start=time.monotonic()
            result=adapter.run(spec, resolved, workspace, deadline_monotonic=start+timeout_seconds)
            if time.monotonic()-start > timeout_seconds:
                gates=tuple(QualificationGate(g, GateStatus.BLOCKED, notes="experiment exceeded bounded timeout") for g in spec.required_gate_ids)
                return self._persist(spec, result, gates)
            metric_gates={g.gate_id:g for g in self.benchmarks.numeric_gates(dict(result.metrics))}
            explicit={g.gate_id:g for g in result.gates}
            gates=[]
            for gate_id in spec.required_gate_ids:
                gates.append(explicit.get(gate_id) or metric_gates.get(gate_id) or QualificationGate(gate_id, GateStatus.BLOCKED, notes="required evidence not produced"))
            return self._persist(spec, result, tuple(gates))
        except Exception as exc:
            gates=tuple(QualificationGate(g, GateStatus.BLOCKED, notes=f"adapter failure: {type(exc).__name__}") for g in spec.required_gate_ids)
            return self._persist(spec, AdapterResult(gates=gates), gates)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _persist(self, spec: VoiceExperimentSpec, result: AdapterResult, gates: tuple[QualificationGate, ...]) -> ExperimentRun:
        artifacts={name: hashlib.sha256(body).hexdigest() for name,body in result.artifacts}
        record=EvidenceRecord.build(experiment_id=spec.experiment_id, provider=spec.provider, model=spec.model,
            revision=result.revision, device=spec.device, device_class=result.device_class, os_name=result.os_name,
            language=spec.language, route=spec.route, configuration=dict(spec.metadata), provenance=dict(result.provenance),
            metrics=dict(result.metrics), gates=gates, artifact_digests=artifacts)
        self.evidence.append(record)
        report=VoiceLabReport(spec.experiment_id,spec.provider,spec.model,spec.device,spec.language,gates,spec.required_gate_ids)
        return ExperimentRun(report,record.evidence_id,result.metrics)
