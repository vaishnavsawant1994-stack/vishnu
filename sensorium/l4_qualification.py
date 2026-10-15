from __future__ import annotations

import json
import os
import time
from pathlib import Path


class PhysicalDeviceQualification:
    """Evidence authority for real-hardware Sensorium L4 qualification.

    Emulator/simulator/hosted-VM results never satisfy this authority. Evidence
    must explicitly identify a physical device and pass the required hardware
    scenarios. Until then the platform remains ``not_qualified``.
    """

    PLATFORMS = frozenset({"android", "ios", "windows", "macos", "linux"})
    REQUIRED = {
        "android": {
            "camera_privacy_indicator", "microphone_privacy_indicator", "os_permission_ui",
            "camera_switching", "battery_drain", "thermal_behavior", "background_behavior",
        },
        "ios": {
            "camera_privacy_indicator", "microphone_privacy_indicator", "os_permission_ui",
            "camera_switching", "battery_drain", "thermal_behavior", "background_behavior",
        },
        "windows": {"camera_privacy_indicator", "microphone_privacy_indicator", "usb_camera", "battery_drain"},
        "macos": {"camera_privacy_indicator", "microphone_privacy_indicator", "usb_camera", "battery_drain"},
        "linux": {"camera_access", "microphone_access", "usb_camera", "battery_drain"},
    }

    def __init__(self, data_dir: Path, *, events=None) -> None:
        self.dir = Path(data_dir) / "sensorium-l4-evidence"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events = events

    @staticmethod
    def _platform(value: str) -> str:
        platform = str(value or "").strip().lower()
        if platform not in PhysicalDeviceQualification.PLATFORMS:
            raise ValueError("unsupported L4 platform")
        return platform

    def _path(self, platform: str) -> Path:
        return self.dir / f"{platform}.json"

    def record(self, platform: str, evidence: dict) -> dict:
        kind = self._platform(platform)
        row = dict(evidence or {})
        if row.get("physical_device") is not True:
            raise PermissionError("L4 evidence must come from a real physical device")
        device_class = str(row.get("device_class") or "").strip()[:120]
        if not device_class:
            raise ValueError("L4 evidence requires a device_class")
        scenarios = row.get("scenarios")
        if not isinstance(scenarios, dict):
            raise ValueError("L4 evidence requires scenario results")
        normalized: dict[str, bool] = {}
        for key, value in scenarios.items():
            name = str(key).strip()[:120]
            if name:
                normalized[name] = value is True
        payload = {
            "platform": kind,
            "physical_device": True,
            "device_class": device_class,
            "os_version": str(row.get("os_version") or "")[:120],
            "app_version": str(row.get("app_version") or "")[:120],
            "runner_identity": str(row.get("runner_identity") or "manual-physical-lab")[:160],
            "scenarios": normalized,
            "recorded_at": time.time(),
        }
        path = self._path(kind)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if self.events is not None:
            self.events.emit(
                "sensorium.l4.evidence_recorded",
                platform=kind,
                device_class=device_class,
                qualified=self.status(kind)["qualified"],
            )
        return self.status(kind)

    def evidence(self, platform: str) -> dict | None:
        kind = self._platform(platform)
        path = self._path(kind)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("physical_device") is not True or payload.get("platform") != kind:
            raise RuntimeError("invalid L4 physical-device evidence")
        return payload

    def status(self, platform: str) -> dict:
        kind = self._platform(platform)
        evidence = self.evidence(kind)
        required = sorted(self.REQUIRED[kind])
        passed = [] if evidence is None else sorted(
            name for name in required if evidence.get("scenarios", {}).get(name) is True
        )
        missing = sorted(set(required) - set(passed))
        return {
            "platform": kind,
            "level": "L4" if not missing and evidence is not None else "L3_or_lower",
            "qualified": evidence is not None and not missing,
            "physical_device_evidence": evidence is not None,
            "required_scenarios": required,
            "passed_scenarios": passed,
            "missing_scenarios": missing,
            "device_class": evidence.get("device_class") if evidence else None,
            "recorded_at": evidence.get("recorded_at") if evidence else None,
        }

    def all_status(self) -> dict:
        statuses = {platform: self.status(platform) for platform in sorted(self.PLATFORMS)}
        return {
            "platforms": statuses,
            "all_platforms_l4": all(value["qualified"] for value in statuses.values()),
        }
