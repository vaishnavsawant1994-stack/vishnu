from __future__ import annotations

import pytest

from core.events import EventBus
from sensorium.models import DeviceState
from sensorium.virtual_device_lab import VirtualDeviceLab
from sensorium.virtual_fleet import (
    NetworkType,
    PermissionState,
    VirtualDeviceFleet,
    VirtualFault,
    VirtualPlatform,
)


def _fleet(*, event_bus=None):
    lab = VirtualDeviceLab(trusted_local=True, event_bus=event_bus)
    return lab, VirtualDeviceFleet(lab)


def test_profiles_cover_android_ios_and_desktop_operating_systems():
    profiles = {item["platform"]: item for item in VirtualDeviceFleet.profiles()}
    assert set(profiles) == {"android", "ios", "windows", "macos", "linux"}
    for profile in profiles.values():
        assert profile["simulated"] is True
        assert profile["execution_authority"] is False
        assert "system" in profile["capabilities"]
        assert "network" in profile["capabilities"]
        assert "camera" in profile["permissions"]
        assert "microphone" in profile["permissions"]


@pytest.mark.parametrize(
    ("platform", "expected_class"),
    [
        (VirtualPlatform.ANDROID, "phone"),
        (VirtualPlatform.IOS, "phone"),
        (VirtualPlatform.WINDOWS, "desktop"),
        (VirtualPlatform.MACOS, "desktop"),
        (VirtualPlatform.LINUX, "desktop"),
    ],
)
def test_full_virtual_platforms_can_be_provisioned(platform, expected_class):
    _lab, fleet = _fleet()
    created = fleet.provision(device_id=f"fixture-{platform.value}", platform=platform)
    assert created["device"]["platform"] == f"virtual-{platform.value}"
    assert created["device"]["metadata"]["device_class"] == expected_class
    assert created["runtime"]["simulated"] is True
    assert created["runtime"]["execution_authority"] is False


def test_battery_network_lock_and_foreground_app_are_simulated_observations():
    lab, fleet = _fleet()
    fleet.provision(device_id="android-1", platform="android")

    battery = fleet.set_battery("android-1", 42, charging=True)
    assert battery["runtime"]["battery_percent"] == 42
    assert battery["runtime"]["charging"] is True

    network = fleet.set_network("android-1", NetworkType.CELLULAR, signal_percent=61)
    assert network["runtime"]["network"]["type"] == "cellular"
    assert network["runtime"]["network"]["signal_percent"] == 61

    assert fleet.set_locked("android-1", True)["runtime"]["locked"] is True
    assert fleet.set_foreground_app("android-1", "com.example.app", title="Private title")["runtime"][
        "foreground_app"
    ] == "com.example.app"

    kinds = [item["kind"] for item in lab.read_events("android-1")]
    assert kinds == ["system", "network", "system", "window"]


def test_location_camera_microphone_and_notifications_require_explicit_virtual_permission():
    _lab, fleet = _fleet()
    fleet.provision(device_id="iphone-1", platform="ios")

    with pytest.raises(PermissionError, match="location"):
        fleet.set_location("iphone-1", 50.1109, 8.6821)
    with pytest.raises(PermissionError, match="camera"):
        fleet.publish_camera_fixture("iphone-1", fixture_ref="fixtures/camera/front.jpg")
    with pytest.raises(PermissionError, match="microphone"):
        fleet.publish_microphone_fixture("iphone-1", fixture_ref="fixtures/audio/voice.wav")
    with pytest.raises(PermissionError, match="notification"):
        fleet.push_notification("iphone-1", title="Hello")

    fleet.set_permission("iphone-1", "location", PermissionState.GRANTED)
    fleet.set_permission("iphone-1", "camera", PermissionState.GRANTED)
    fleet.set_permission("iphone-1", "microphone", PermissionState.GRANTED)
    fleet.set_permission("iphone-1", "notifications", PermissionState.GRANTED)

    location = fleet.set_location("iphone-1", 50.1109, 8.6821, accuracy_meters=5)
    assert location["runtime"]["location"]["available"] is True

    camera = fleet.publish_camera_fixture(
        "iphone-1",
        fixture_ref="fixtures/camera/front.jpg",
        analysis="A synthetic desk scene",
    )
    assert camera["kind"] == "camera"
    assert camera["payload"]["raw_bytes"] is False

    microphone = fleet.publish_microphone_fixture(
        "iphone-1",
        fixture_ref="fixtures/audio/voice.wav",
        transcript="synthetic speech",
        duration_ms=1200,
    )
    assert microphone["kind"] == "microphone"
    assert microphone["payload"]["raw_audio"] is False

    notification = fleet.push_notification(
        "iphone-1",
        app_id="com.example.messages",
        title="Private notification",
        body="Sensitive body",
    )
    assert notification["runtime"]["runtime"]["notification_count"] == 1


def test_raw_virtual_camera_microphone_notification_and_window_content_never_reaches_shared_event_bus():
    emitted: list[dict] = []
    bus = EventBus()
    bus.subscribe("sensorium.sensor_event.injected", emitted.append)
    _lab, fleet = _fleet(event_bus=bus)
    fleet.provision(device_id="desktop-1", platform="windows")
    fleet.set_permission("desktop-1", "camera", "granted")
    fleet.set_permission("desktop-1", "microphone", "granted")
    fleet.set_permission("desktop-1", "notifications", "granted")

    fleet.set_foreground_app("desktop-1", "browser", title="SECRET WINDOW TITLE")
    fleet.publish_camera_fixture(
        "desktop-1", fixture_ref="SECRET CAMERA REF", analysis="SECRET CAMERA ANALYSIS"
    )
    fleet.publish_microphone_fixture(
        "desktop-1", fixture_ref="SECRET AUDIO REF", transcript="SECRET TRANSCRIPT"
    )
    fleet.push_notification("desktop-1", title="SECRET TITLE", body="SECRET BODY")

    serialized = repr(emitted)
    for secret in (
        "SECRET WINDOW TITLE",
        "SECRET CAMERA REF",
        "SECRET CAMERA ANALYSIS",
        "SECRET AUDIO REF",
        "SECRET TRANSCRIPT",
        "SECRET TITLE",
        "SECRET BODY",
    ):
        assert secret not in serialized
    assert emitted
    assert all(item["sensor_event"]["payload_projected"] is False for item in emitted)


def test_disconnect_reconnect_exercises_offline_boundary_without_physical_side_effects():
    lab, fleet = _fleet()
    fleet.provision(device_id="mac-1", platform="macos")

    disconnected = fleet.disconnect("mac-1")
    assert disconnected["device"]["state"] == DeviceState.OFFLINE.value
    with pytest.raises(RuntimeError, match="online"):
        fleet.set_battery("mac-1", 50)

    reconnected = fleet.reconnect("mac-1")
    assert reconnected["device_state"] == DeviceState.ONLINE.value
    assert lab.get_device("mac-1")["state"] == DeviceState.ONLINE.value


def test_fault_scenarios_cover_network_battery_permission_and_transport_recovery():
    _lab, fleet = _fleet()
    fleet.provision(device_id="android-faults", platform="android")
    fleet.set_permission("android-faults", "camera", "granted")

    fleet.simulate_fault("android-faults", VirtualFault.NETWORK_DROP)
    assert fleet.snapshot("android-faults")["runtime"]["network"]["online"] is False

    fleet.simulate_fault("android-faults", VirtualFault.LOW_BATTERY)
    assert fleet.snapshot("android-faults")["runtime"]["battery_percent"] == 5

    fleet.simulate_fault("android-faults", VirtualFault.PERMISSION_REVOCATION, permission="camera")
    assert fleet.snapshot("android-faults")["runtime"]["permissions"]["camera"] == "denied"

    fleet.simulate_fault("android-faults", VirtualFault.DISCONNECT_RECONNECT)
    assert fleet.snapshot("android-faults")["device_state"] == "online"


def test_virtual_fleet_does_not_expose_host_execution_controls():
    _lab, fleet = _fleet()
    forbidden = {
        "click",
        "type_text",
        "press_key",
        "move_mouse",
        "open_url",
        "launch_app",
        "install_package",
        "send_notification",
        "execute",
    }
    assert not any(hasattr(fleet, method) for method in forbidden)


def test_invalid_bounds_fail_closed():
    _lab, fleet = _fleet()
    fleet.provision(device_id="linux-1", platform="linux")
    with pytest.raises(ValueError, match="battery"):
        fleet.set_battery("linux-1", 101)
    with pytest.raises(ValueError, match="signal"):
        fleet.set_network("linux-1", "wifi", signal_percent=-1)
    fleet.set_permission("linux-1", "location", "granted")
    with pytest.raises(ValueError, match="coordinates"):
        fleet.set_location("linux-1", 120, 0)
    with pytest.raises(ValueError, match="unsupported"):
        fleet.set_permission("linux-1", "contacts", "granted")
