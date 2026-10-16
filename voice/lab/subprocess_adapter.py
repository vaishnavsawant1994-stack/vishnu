"""Hard-bounded subprocess adapter for isolated Voice Lab experiments."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from .evaluation import GateStatus, QualificationGate
from .experiments import VoiceExperimentSpec
from .fixtures import VoiceFixture
from .runner import AdapterResult, LabRunCancelled, LabRunControl, LabRunTimedOut


_SENSITIVE_TOKENS = ("token", "secret", "password", "api_key", "apikey", "authorization", "bearer")


def _safe_metadata(spec: VoiceExperimentSpec) -> dict[str, str]:
    return {
        key: value
        for key, value in spec.metadata
        if not any(token in key.casefold() for token in _SENSITIVE_TOKENS)
    }


def _gate(payload: dict[str, Any]) -> QualificationGate:
    try:
        status = GateStatus(str(payload["status"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("subprocess gate status is invalid") from exc
    return QualificationGate(
        gate_id=str(payload.get("gate_id", "")),
        status=status,
        observed=payload.get("observed"),
        threshold=str(payload.get("threshold", "")),
        notes=str(payload.get("notes", "")),
    )


class BoundedSubprocessAdapter:
    """Execute one fixed absolute argv without a shell and enforce hard stop.

    The child receives one JSON request on stdin and must emit one JSON object on
    stdout. Credentials are intentionally not taken from experiment metadata.
    Provider-specific secrets belong in the provider's own governed secret
    boundary, not in Voice Lab experiment definitions.
    """

    def __init__(
        self,
        argv: tuple[str, ...],
        *,
        revision: str = "",
        os_name: str = "",
        device_class: str = "unknown",
        max_output_bytes: int = 1_048_576,
        terminate_grace_seconds: float = 1.0,
    ):
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("subprocess adapter requires a fixed absolute executable path")
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be positive")
        self.argv = tuple(argv)
        self.revision = revision
        self.os_name = os_name
        self.device_class = device_class
        self.max_output_bytes = int(max_output_bytes)
        self.terminate_grace_seconds = float(terminate_grace_seconds)

    def _request(self, spec: VoiceExperimentSpec, fixtures: tuple[VoiceFixture, ...]) -> str:
        return json.dumps(
            {
                "experiment_id": spec.experiment_id,
                "provider": spec.provider,
                "model": spec.model,
                "device": spec.device,
                "language": spec.language,
                "route": spec.route,
                "style": spec.style,
                "fixture_refs": spec.fixture_refs,
                "fixtures": [
                    {
                        "fixture_id": item.fixture_id,
                        "kind": item.kind.value,
                        "transcript": item.transcript,
                        "languages": item.languages,
                        "tags": item.tags,
                    }
                    for item in fixtures
                ],
                "metadata": _safe_metadata(spec),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _stop(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.terminate_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self.terminate_grace_seconds)

    def run(
        self,
        spec: VoiceExperimentSpec,
        fixtures: tuple[VoiceFixture, ...],
        workspace: Path,
        *,
        control: LabRunControl,
    ) -> AdapterResult:
        control.checkpoint()
        process = subprocess.Popen(
            self.argv,
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            shell=False,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
        request = self._request(spec, fixtures)
        stdout = ""
        stderr = ""
        first = True
        try:
            while True:
                try:
                    control.checkpoint()
                except (LabRunCancelled, LabRunTimedOut):
                    self._stop(process)
                    raise
                try:
                    stdout, stderr = process.communicate(input=request if first else None, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    time.sleep(0.01)
            if process.returncode != 0:
                raise RuntimeError(f"Voice Lab subprocess failed with exit code {process.returncode}")
        finally:
            if process.poll() is None:
                self._stop(process)
        if len(stdout.encode("utf-8")) > self.max_output_bytes:
            raise ValueError("Voice Lab subprocess response exceeded size bound")
        if len(stderr.encode("utf-8")) > self.max_output_bytes:
            raise ValueError("Voice Lab subprocess diagnostic output exceeded size bound")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Voice Lab subprocess returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Voice Lab subprocess response must be a JSON object")
        raw_metrics = payload.get("metrics", {})
        raw_gates = payload.get("gates", [])
        if not isinstance(raw_metrics, dict) or not isinstance(raw_gates, list):
            raise ValueError("Voice Lab subprocess metrics/gates schema is invalid")
        metrics = tuple(sorted((str(key), float(value)) for key, value in raw_metrics.items()))
        gates = tuple(_gate(item) for item in raw_gates if isinstance(item, dict))
        provenance = payload.get("provenance", {})
        if not isinstance(provenance, dict):
            raise ValueError("Voice Lab subprocess provenance must be an object")
        return AdapterResult(
            metrics=metrics,
            gates=gates,
            revision=str(payload.get("revision") or self.revision),
            os_name=str(payload.get("os_name") or self.os_name),
            device_class=str(payload.get("device_class") or self.device_class),
            provenance=tuple(sorted((str(key), str(value)) for key, value in provenance.items())),
        )
