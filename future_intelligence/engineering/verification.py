from __future__ import annotations

from typing import Iterable, Mapping

from .qualification import VerificationObservation


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
    return _collapse(observations)


def observations_from_browser_payload(payload: Mapping[str, object]) -> tuple[VerificationObservation, ...]:
    browser = str(payload.get("browser") or "chromium").lower()
    responsive = bool(payload.get("responsive_passed", False))
    runtime = bool(payload.get("runtime_passed", False))
    visual = bool(payload.get("visual_passed", False))
    evidence = tuple(str(item) for item in payload.get("evidence", ()))  # type: ignore[arg-type]
    observations = [
        VerificationObservation("responsive", responsive, f"{browser} responsive qualification", evidence),
        VerificationObservation(browser, responsive and runtime, f"{browser} compatibility qualification", evidence),
        VerificationObservation("runtime", runtime, f"{browser} console/network/runtime qualification", evidence),
        VerificationObservation("visual", visual, f"{browser} visual qualification", evidence),
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
            observations.append(VerificationObservation(gate, bool(payload.get(key)), label, evidence))
    return tuple(observations)


def _collapse(observations: Iterable[VerificationObservation]) -> tuple[VerificationObservation, ...]:
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
