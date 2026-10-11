from __future__ import annotations

from typing import Iterable, Mapping

from .qualification import VerificationObservation


def observation_to_dict(item: VerificationObservation) -> dict[str, object]:
    return {
        "gate": item.gate,
        "passed": bool(item.passed),
        "summary": item.summary,
        "evidence": list(item.evidence),
        "warning": bool(item.warning),
        "metadata": dict(item.metadata or {}),
    }


def observation_from_dict(data: Mapping[str, object]) -> VerificationObservation:
    gate = str(data.get("gate") or "").strip()
    if not gate:
        raise ValueError("verification observation gate is required")
    evidence_raw = data.get("evidence") or ()
    if isinstance(evidence_raw, str):
        evidence_raw = (evidence_raw,)
    if not isinstance(evidence_raw, (list, tuple)):
        raise ValueError("verification observation evidence must be a list")
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("verification observation metadata must be an object")
    return VerificationObservation(
        gate=gate,
        passed=bool(data.get("passed", False)),
        summary=str(data.get("summary") or "")[:4000],
        evidence=tuple(str(item) for item in evidence_raw if str(item)),
        warning=bool(data.get("warning", False)),
        metadata=dict(metadata or {}),
    )


def observations_from_verification_report(report, *, gate_map: Mapping[str, str] | None = None) -> tuple[VerificationObservation, ...]:
    """Convert existing revision-bound verification checks into engineering gates."""
    mapping = dict(gate_map or {})
    observations = []
    for check in report.checks:
        lower = str(check.name).lower()
        if check.name in mapping:
            gate = mapping[check.name]
        elif "security" in lower or "protected" in lower or "manifest" in lower:
            gate = "security"
        elif "lint" in lower or "type" in lower or "build" in lower or "package" in lower:
            gate = "build"
        elif "integration" in lower or "browser" in lower or "e2e" in lower:
            gate = "integration"
        else:
            gate = "unit"
        observations.append(VerificationObservation(
            gate=gate,
            passed=bool(check.passed),
            summary=f"{check.name}: {'passed' if check.passed else 'failed'}",
            evidence=(str(check.output_hash),),
            metadata={"returncode": int(check.returncode), "duration_ms": int(check.duration_ms), "command": list(check.command)},
        ))
    return collapse_observations(observations)


def observations_from_browser_payload(payload: Mapping[str, object]) -> tuple[VerificationObservation, ...]:
    browser = str(payload.get("browser") or "chromium").lower()
    responsive = bool(payload.get("responsive_passed", False))
    runtime = bool(payload.get("runtime_passed", False))
    visual = bool(payload.get("visual_passed", False))
    candidate_revision = str(payload.get("candidate_revision") or "").strip()
    evidence_raw = payload.get("evidence", ())
    if isinstance(evidence_raw, str):
        evidence_raw = (evidence_raw,)
    evidence = tuple(str(item) for item in evidence_raw)  # type: ignore[arg-type]
    metadata = {"candidate_revision": candidate_revision} if candidate_revision else {}
    observations = [
        VerificationObservation("responsive", responsive, f"{browser} responsive qualification", evidence, metadata=metadata),
        VerificationObservation(browser, responsive and runtime, f"{browser} compatibility qualification", evidence, metadata=metadata),
        VerificationObservation("runtime", runtime, f"{browser} console/network/runtime qualification", evidence, metadata=metadata),
        VerificationObservation("visual", visual, f"{browser} visual qualification", evidence, metadata=metadata),
    ]
    optional = {
        "accessibility_passed": ("accessibility", "accessibility qualification"),
        "performance_passed": ("performance", "performance budget qualification"),
        "localization_passed": ("localization", "localization/content-stress qualification"),
        "three_d_passed": ("three_d", "living Vishnu / 3D qualification"),
        "physical_device_passed": ("physical_device", "physical-device qualification"),
        "preview_passed": ("preview", "deployed-preview qualification"),
    }
    for key, (gate, label) in optional.items():
        if key in payload:
            observations.append(VerificationObservation(gate, bool(payload.get(key)), label, evidence, metadata=metadata))
    return tuple(observations)


def collapse_observations(observations: Iterable[VerificationObservation]) -> tuple[VerificationObservation, ...]:
    grouped: dict[str, list[VerificationObservation]] = {}
    for item in observations:
        grouped.setdefault(item.gate, []).append(item)
    result = []
    for gate, items in grouped.items():
        result.append(VerificationObservation(
            gate=gate,
            passed=all(item.passed for item in items),
            summary="; ".join(item.summary for item in items)[:4000],
            evidence=tuple(dict.fromkeys(value for item in items for value in item.evidence)),
            warning=all(item.warning for item in items),
            metadata={"checks": len(items)},
        ))
    return tuple(result)


# Backwards-compatible private alias for earlier callers/tests.
_collapse = collapse_observations
