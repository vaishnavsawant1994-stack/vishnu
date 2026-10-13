from __future__ import annotations

import json

import pytest

from sensorium.native_lab import (
    AndroidEmulatorProbe,
    CommandResult,
    DesktopVMProbe,
    IOSSimulatorProbe,
    NativeDeviceEvidence,
    NativeDeviceLab,
    NativePlatform,
    NativeProvider,
    NativeStatus,
)


def _runner(mapping):
    def run(args: tuple[str, ...], timeout: int) -> CommandResult:
        assert timeout > 0
        key = tuple(args)
        if key not in mapping:
            return CommandResult(1, "", "unexpected command")
        value = mapping[key]
        if isinstance(value, CommandResult):
            return value
        return CommandResult(0, str(value), "")

    return run


def test_android_probe_accepts_emulator_only_and_collects_bounded_read_only_evidence():
    serial = "emulator-5554"
    runner = _runner(
        {
            ("adb", "devices"): f"List of devices attached\n{serial}\tdevice\nphysical-1\tdevice\n",
            ("adb", "-s", serial, "shell", "getprop", "ro.boot.qemu"): "1\n",
            ("adb", "-s", serial, "shell", "getprop", "ro.build.version.release"): "16\n",
            ("adb", "-s", serial, "shell", "getprop", "ro.build.version.sdk"): "36\n",
            ("adb", "-s", serial, "shell", "getprop", "ro.product.model"): "sdk_gphone64_x86_64\n",
            ("adb", "-s", serial, "shell", "getprop", "ro.product.cpu.abi"): "x86_64\n",
            ("adb", "-s", serial, "shell", "getprop", "sys.boot_completed"): "1\n",
            ("adb", "-s", serial, "shell", "dumpsys", "battery"): "level: 83\n",
        }
    )
    evidence = AndroidEmulatorProbe(runner).probe(serial)
    assert evidence.provider == NativeProvider.ANDROID_EMULATOR
    assert evidence.platform == NativePlatform.ANDROID
    assert evidence.status == NativeStatus.READY
    assert evidence.target_id == serial
    assert evidence.metadata["qemu"] is True
    assert evidence.metadata["battery_percent"] == 83
    assert evidence.physical_device is False
    assert evidence.execution_authority is False


def test_android_probe_rejects_physical_adb_serials():
    runner = _runner({("adb", "devices"): "List of devices attached\nR58M1234\tdevice\n"})
    with pytest.raises(RuntimeError, match="Android Emulator"):
        AndroidEmulatorProbe(runner).probe("R58M1234")


def test_ios_probe_allows_xcode_core_simulator_inventory_to_finish():
    udid = "A1B2C3D4-E5F6-47A8-9B10-111213141516"
    payload = {"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
        {"name": "iPhone 17 Pro", "udid": udid, "state": "Booted", "isAvailable": True}
    ]}}
    observed_timeouts = []

    def runner(args: tuple[str, ...], timeout: int) -> CommandResult:
        observed_timeouts.append(timeout)
        return CommandResult(0, json.dumps(payload), "")

    IOSSimulatorProbe(runner).probe(udid)
    assert observed_timeouts == [60]


def test_desktop_vm_probe_respects_explicit_empty_environment(monkeypatch):
    monkeypatch.setattr("sensorium.native_lab.os.environ", {
        "GITHUB_ACTIONS": "true",
        "VISHNU_DESKTOP_VM": "true",
    })
    with pytest.raises(RuntimeError, match="declared VM"):
        DesktopVMProbe({}).probe()


def test_ios_probe_reads_core_simulator_inventory_without_execution_authority():
    udid = "A1B2C3D4-E5F6-47A8-9B10-111213141516"
    payload = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
                {"name": "iPhone 17 Pro", "udid": udid, "state": "Booted", "isAvailable": True}
            ]
        }
    }
    runner = _runner({("xcrun", "simctl", "list", "devices", "available", "--json"): json.dumps(payload)})
    evidence = IOSSimulatorProbe(runner).probe(udid)
    assert evidence.provider == NativeProvider.IOS_SIMULATOR
    assert evidence.platform == NativePlatform.IOS
    assert evidence.status == NativeStatus.READY
    assert evidence.target_id == udid
    assert evidence.metadata["state"] == "Booted"
    assert evidence.physical_device is False
    assert evidence.execution_authority is False


def test_desktop_vm_probe_fails_closed_outside_declared_vm(monkeypatch):
    monkeypatch.setattr("sensorium.native_lab.host_platform.system", lambda: "Linux")
    monkeypatch.setattr("sensorium.native_lab.host_platform.release", lambda: "6.0")
    monkeypatch.setattr("sensorium.native_lab.host_platform.machine", lambda: "x86_64")
    non_vm_environment = {"GITHUB_ACTIONS": "", "VISHNU_DESKTOP_VM": ""}
    with pytest.raises(RuntimeError, match="declared VM"):
        DesktopVMProbe(non_vm_environment).probe()


def test_desktop_vm_probe_supports_linux_windows_and_macos_hosted_runners(monkeypatch):
    for system, expected in (("Linux", "linux"), ("Windows", "windows"), ("Darwin", "macos")):
        monkeypatch.setattr("sensorium.native_lab.host_platform.system", lambda value=system: value)
        monkeypatch.setattr("sensorium.native_lab.host_platform.release", lambda: "test-release")
        monkeypatch.setattr("sensorium.native_lab.host_platform.machine", lambda: "x86_64")
        evidence = DesktopVMProbe(
            {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "12345", "RUNNER_OS": system}
        ).probe()
        assert evidence.platform.value == expected
        assert evidence.provider == NativeProvider.DESKTOP_VM
        assert evidence.status == NativeStatus.READY
        assert evidence.metadata["environment_kind"] == "github_actions_hosted_runner"
        assert evidence.execution_authority is False


def test_native_evidence_store_persists_safe_snapshots_and_emits_metadata_only(tmp_path):
    emitted = []

    class Bus:
        def emit(self, name, **payload):
            emitted.append((name, payload))

    lab = NativeDeviceLab(tmp_path / "native.sqlite3", event_bus=Bus())
    evidence = NativeDeviceEvidence(
        provider="desktop_vm",
        platform="linux",
        target_id="desktop-linux-ci-1",
        status="ready",
        os_version="Linux test",
        architecture="x86_64",
        capabilities=("package_smoke", "python_runtime"),
        metadata={"runner_os": "Linux", "environment_kind": "github_actions_hosted_runner"},
    )
    recorded = lab.record(evidence)
    rows = lab.list()
    assert recorded["evidence_id"] == 1
    assert rows[0]["target_id"] == "desktop-linux-ci-1"
    assert rows[0]["physical_device"] is False
    assert rows[0]["execution_authority"] is False
    assert emitted == [
        (
            "sensorium.native_device.evidence_recorded",
            {
                "evidence_id": 1,
                "provider": "desktop_vm",
                "platform": "linux",
                "target_id": "desktop-linux-ci-1",
                "status": "ready",
                "physical_device": False,
                "execution_authority": False,
            },
        )
    ]
    lab.close()


def test_native_evidence_rejects_secret_bearing_metadata_and_authority_escalation():
    with pytest.raises(ValueError, match="secret-bearing"):
        NativeDeviceEvidence(
            provider="desktop_vm",
            platform="linux",
            target_id="desktop-linux-ci-1",
            status="ready",
            os_version="Linux test",
            architecture="x86_64",
            metadata={"api_key": "do-not-store"},
        )

    with pytest.raises(ValueError, match="physical device"):
        NativeDeviceEvidence(
            provider="desktop_vm",
            platform="linux",
            target_id="desktop-linux-ci-1",
            status="ready",
            os_version="Linux test",
            architecture="x86_64",
            physical_device=True,
        )

    with pytest.raises(ValueError, match="execution authority"):
        NativeDeviceEvidence(
            provider="desktop_vm",
            platform="linux",
            target_id="desktop-linux-ci-1",
            status="ready",
            os_version="Linux test",
            architecture="x86_64",
            execution_authority=True,
        )


def test_native_device_lab_exposes_no_generic_command_execution_surface(tmp_path):
    lab = NativeDeviceLab(tmp_path / "native.sqlite3")
    forbidden = {"execute", "shell", "adb", "simctl", "click", "type_text", "launch_app", "open_url"}
    assert not any(hasattr(lab, name) for name in forbidden)
    lab.close()
