from __future__ import annotations

import argparse
import json
import os
import platform as host_platform
from pathlib import Path


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


def fail(message: str) -> None:
    raise SystemExit(f"Sensorium L4 qualification failed: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=sorted(REQUIRED), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if os.getenv("VISHNU_L4_SELF_HOSTED", "").lower() != "true":
        fail("L4 can run only on an explicitly configured self-hosted physical-device runner")
    if not args.evidence.exists():
        fail(f"real-device evidence file is missing: {args.evidence}")
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    if data.get("physical_device") is not True:
        fail("evidence does not assert a physical device")
    if str(data.get("platform") or "").lower() != args.platform:
        fail("evidence platform does not match the qualification job")
    device_class = str(data.get("device_class") or "").strip()
    if not device_class:
        fail("device_class is required")
    forbidden = {"emulator", "simulator", "virtual", "github-hosted", "qemu"}
    lowered = device_class.lower()
    if any(word in lowered for word in forbidden):
        fail("virtual/emulated device classification cannot satisfy L4")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        fail("scenario map is required")
    missing = sorted(name for name in REQUIRED[args.platform] if scenarios.get(name) is not True)
    if missing:
        fail("required physical scenarios did not pass: " + ", ".join(missing))

    normalized = {
        "platform": args.platform,
        "physical_device": True,
        "device_class": device_class[:160],
        "os_version": str(data.get("os_version") or "")[:160],
        "app_version": str(data.get("app_version") or "")[:160],
        "runner": {
            "self_hosted": True,
            "host_system": host_platform.system(),
            "host_machine": host_platform.machine(),
        },
        "scenarios": {name: True for name in sorted(REQUIRED[args.platform])},
        "qualified_level": "L4",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Sensorium L4 qualified for {args.platform}: {device_class}")


if __name__ == "__main__":
    main()
