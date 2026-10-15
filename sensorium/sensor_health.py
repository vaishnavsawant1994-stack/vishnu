from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HealthFinding:
    code: str
    severity: str
    message: str
    sensor: str

    def public(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "sensor": self.sensor,
        }


class SensorHealthMonitor:
    """Fail-closed health checks before observations are trusted by reasoning."""

    def __init__(self, *, events=None) -> None:
        self.events = events

    @staticmethod
    def _finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and math.isfinite(float(value))

    def evaluate(self, sensor: str, sample: dict[str, Any] | None) -> dict:
        kind = str(sensor or "").strip().lower()
        data = dict(sample or {})
        findings: list[HealthFinding] = []
        now = time.time()
        captured_at = data.get("captured_at")
        if self._finite(captured_at):
            skew = abs(now - float(captured_at))
            if skew > 300:
                findings.append(HealthFinding("clock_skew", "high", "Sensor timestamp differs from runtime time by more than five minutes.", kind))
            elif skew > 30:
                findings.append(HealthFinding("clock_skew", "medium", "Sensor timestamp appears stale or clock-skewed.", kind))

        if kind in {"camera", "screen"}:
            brightness = data.get("brightness")
            if self._finite(brightness) and float(brightness) < 0.05:
                findings.append(HealthFinding("too_dark", "medium", "Image is too dark for reliable visual reasoning.", kind))
            sharpness = data.get("sharpness")
            if self._finite(sharpness) and float(sharpness) < 0.08:
                findings.append(HealthFinding("blurred", "medium", "Image appears blurred or camera may be obstructed.", kind))
            if data.get("blocked") is True:
                findings.append(HealthFinding("blocked", "high", "Camera or screen source appears blocked.", kind))

        if kind in {"microphone", "audio"}:
            if data.get("muted") is True:
                findings.append(HealthFinding("muted", "high", "Microphone is muted.", kind))
            rms = data.get("rms")
            if self._finite(rms) and float(rms) <= 0.0001:
                findings.append(HealthFinding("silence_or_disconnected", "medium", "Microphone has no measurable signal.", kind))
            clipped = data.get("clipped_fraction")
            if self._finite(clipped) and float(clipped) > 0.1:
                findings.append(HealthFinding("clipping", "medium", "Audio is clipping and may be unreliable.", kind))

        if kind in {"motion", "orientation", "spatial"}:
            for name in ("x", "y", "z", "yaw", "pitch", "roll"):
                if name in data and not self._finite(data[name]):
                    findings.append(HealthFinding("invalid_numeric", "high", f"{name} is not a finite sensor value.", kind))
            accuracy = data.get("accuracy")
            if self._finite(accuracy) and float(accuracy) < 0:
                findings.append(HealthFinding("uncalibrated", "medium", "Sensor reports uncalibrated/unknown accuracy.", kind))

        if kind == "location":
            accuracy_m = data.get("accuracy_m")
            if self._finite(accuracy_m) and float(accuracy_m) > 250:
                findings.append(HealthFinding("location_low_accuracy", "medium", "Location accuracy is too coarse for precise context.", kind))

        if kind == "network" and data.get("connected") is False:
            findings.append(HealthFinding("offline", "low", "Network source is currently offline.", kind))

        high = any(item.severity == "high" for item in findings)
        result = {
            "sensor": kind,
            "healthy": not high,
            "findings": [item.public() for item in findings],
            "reasoning_allowed": not high,
            "execution_authority": False,
        }
        if self.events is not None and findings:
            self.events.emit(
                "sensorium.health.findings",
                sensor=kind,
                finding_codes=[item.code for item in findings],
                reasoning_allowed=not high,
                execution_authority=False,
            )
        return result
