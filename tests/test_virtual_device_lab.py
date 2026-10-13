from devices.runtime import DeviceCommand, QualificationLevel, RuntimeMode, RuntimeState
from devices.simulator import SimulatedDeviceRuntime, VirtualDeviceProfile
from devices.virtual_lab import VirtualDeviceLab


def test_simulated_runtime_reports_explicit_mode_and_qualification():
    runtime = SimulatedDeviceRuntime(VirtualDeviceProfile("virtual-1", "Test Phone", "android-emulator"))

    status = runtime.status()

    assert status.mode == RuntimeMode.SIMULATED
    assert status.state == RuntimeState.READY
    assert status.qualification == QualificationLevel.SIMULATED
    assert status.as_dict()["qualification"] == "simulated"


def test_virtual_lab_executes_and_verifies_without_physical_device():
    lab = VirtualDeviceLab()
    device = lab.create_device("Android Test", "android-emulator", installed_apps={"example.app"})

    result = lab.execute(device.device_id, "app.open", {"app": "example.app"}, request_id="req-1")
    verified = lab.verify(device.device_id, "req-1")

    assert result["success"] is True
    assert result["simulated"] is True
    assert result["output"] == {"opened": True, "app": "example.app"}
    assert verified is not None
    assert verified.verified is True


def test_virtual_lab_models_offline_locked_and_low_battery_states():
    lab = VirtualDeviceLab()
    device = lab.create_device("iPhone Test", "ios-simulator")

    status = lab.set_scenario(device.device_id, battery_percent=4, network="offline", locked=True)
    blocked = lab.execute(device.device_id, "notification.emit", {"title": "Hello"})

    assert status["metadata"]["battery_percent"] == 4
    assert status["metadata"]["network"] == "offline"
    assert status["state"] == "locked"
    assert blocked["success"] is False
    assert blocked["code"] == "device_locked"


def test_failure_injection_handles_disconnect_and_permission_revocation():
    lab = VirtualDeviceLab()
    device = lab.create_device("Failure Test", "android-emulator")

    lab.inject_failure(device.device_id, "disconnect")
    disconnected = lab.execute(device.device_id, "device.status", request_id="disconnect-1")
    assert disconnected["code"] == "device_disconnected"
    assert lab.status(device.device_id)["state"] == "offline"

    lab.set_scenario(device.device_id, online=True)
    lab.inject_failure(device.device_id, "permission_revoked")
    revoked = lab.execute(device.device_id, "telemetry.read", request_id="permission-1")
    assert revoked["code"] == "permission_revoked"
    denied = lab.execute(device.device_id, "telemetry.read", request_id="permission-2")
    assert denied["code"] == "permission_denied"


def test_cancelled_request_cannot_execute():
    runtime = SimulatedDeviceRuntime(VirtualDeviceProfile("virtual-2", "Desktop Test", "desktop"))
    runtime.cancel("cancel-me")

    result = runtime.execute(DeviceCommand("device.status", request_id="cancel-me"))

    assert result.success is False
    assert result.code == "cancelled"


def test_lab_rejects_unknown_platforms():
    lab = VirtualDeviceLab()

    try:
        lab.create_device("Unknown", "physical-magic-device")
    except ValueError as exc:
        assert "unsupported virtual device platform" in str(exc)
    else:
        raise AssertionError("unsupported virtual platform must fail closed")
