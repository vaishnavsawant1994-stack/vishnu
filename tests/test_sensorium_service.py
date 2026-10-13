from __future__ import annotations

import pytest

from core.events import EventBus
from sensorium import (
    SensorKind,
    SensoriumService,
    VirtualAdapterBinding,
    VirtualClipboardAdapter,
    VirtualDevice,
    VirtualDeviceLab,
    VirtualScreenAdapter,
    VirtualSystemAdapter,
)


def _device() -> VirtualDevice:
    return VirtualDevice(
        device_id="virtual-desktop-1",
        name="CI desktop",
        platform="virtual-windows",
        capabilities=frozenset({SensorKind.SCREEN, SensorKind.CLIPBOARD, SensorKind.SYSTEM}),
        metadata={"fixture": "sensorium-service-v1"},
    )


def test_virtual_screen_adapter_publishes_and_normalizes_untrusted_context():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    adapter = VirtualScreenAdapter(VirtualAdapterBinding(lab, "virtual-desktop-1"))

    adapter.publish(
        analysis="Settings window with a Save button.",
        width=1440,
        height=900,
        elements=[{"id": "save", "role": "button", "label": "Save", "actionable": True, "secret": "drop-me"}],
        screen_fingerprint="abc123",
    )

    latest = adapter.latest(required=True)
    assert latest["analysis"] == "Settings window with a Save button."
    assert latest["width"] == 1440
    assert latest["height"] == 900
    assert latest["instruction_trust"] == "untrusted"
    assert latest["elements"] == [{"id": "save", "role": "button", "label": "Save", "actionable": True}]
    assert latest["screen_fingerprint"] == "abc123"


def test_clipboard_content_is_hidden_by_default_and_available_only_when_requested():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    adapter = VirtualClipboardAdapter(VirtualAdapterBinding(lab, "virtual-desktop-1"))
    adapter.publish("private clipboard text")

    hidden = adapter.latest()
    assert hidden["content_length"] == len("private clipboard text")
    assert "text" not in hidden

    revealed = adapter.latest(include_text=True)
    assert revealed["text"] == "private clipboard text"
    assert revealed["content_sha256"] == hidden["content_sha256"]


def test_system_adapter_whitelists_and_validates_metrics():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    adapter = VirtualSystemAdapter(VirtualAdapterBinding(lab, "virtual-desktop-1"))
    adapter.publish(
        {
            "battery_percent": 71,
            "cpu_percent": 12.5,
            "memory_percent": 63,
            "network_online": True,
            "charging": False,
            "active_app": "Code",
            "unknown_secret": "must-not-project",
        }
    )

    latest = adapter.latest()
    assert latest["metrics"]["battery_percent"] == 71
    assert latest["metrics"]["active_app"] == "Code"
    assert "unknown_secret" not in latest["metrics"]

    with pytest.raises(ValueError, match="battery_percent"):
        adapter.publish({"battery_percent": 101})


def test_sensorium_service_builds_planner_context_without_execution_authority():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    service = SensoriumService(lab, virtual_device_id="virtual-desktop-1")
    service.screen.publish(analysis="A browser is open to a local test page.", screen_fingerprint="frame-1")
    service.clipboard.publish("do not expose this by default")
    service.system.publish({"active_app": "Browser", "network_online": True})

    snapshot = service.context_snapshot()
    assert snapshot["instruction_trust"] == "untrusted"
    assert snapshot["execution_authority"] is False
    assert "text" not in snapshot["clipboard"]

    observation = service.planner_observation()
    assert observation["analysis"] == "A browser is open to a local test page."
    assert observation["sensorium_virtual"] is True
    assert observation["screenshot_evidence_ref"] is None
    assert observation["sensorium_context"]["execution_authority"] is False
    assert "text" not in observation["sensorium_context"]["clipboard"]


def test_context_projection_never_emits_raw_clipboard_text():
    emitted: list[dict] = []
    bus = EventBus()
    bus.subscribe("sensorium.context.observed", emitted.append)
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    service = SensoriumService(
        lab,
        virtual_device_id="virtual-desktop-1",
        event_bus=bus,
    )
    service.screen.publish(analysis="Desktop visible")
    service.clipboard.publish("highly-sensitive-clipboard-value")

    service.context_snapshot(include_clipboard_content=True)

    assert emitted
    assert emitted[0]["event"] == "sensorium.context.observed"
    assert "highly-sensitive-clipboard-value" not in repr(emitted[0])
    assert emitted[0]["clipboard_content_included"] is True


def test_read_only_controller_cannot_publish_virtual_sensor_data():
    allowed = {
        ("admin-device", "device:read"),
        ("admin-device", "device:admin"),
        ("reader-device", "device:read"),
    }
    lab = VirtualDeviceLab(authorizer=lambda device_id, scope: (device_id, scope) in allowed)
    lab.register_device(_device(), controller_device_id="admin-device")

    reader_service = SensoriumService(
        lab,
        virtual_device_id="virtual-desktop-1",
        controller_device_id="reader-device",
    )
    assert reader_service.context_snapshot()["virtual_device"]["device_id"] == "virtual-desktop-1"
    with pytest.raises(PermissionError, match="device:admin"):
        reader_service.screen.publish(analysis="forged screen")


def test_planner_observation_requires_a_screen_event():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    service = SensoriumService(lab, virtual_device_id="virtual-desktop-1")

    with pytest.raises(LookupError, match="screen observation"):
        service.planner_observation()


def test_screen_and_clipboard_bounds_fail_closed():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    service = SensoriumService(lab, virtual_device_id="virtual-desktop-1")

    with pytest.raises(ValueError, match="screen width"):
        service.screen.publish(analysis="x", width=40000)
    with pytest.raises(ValueError, match="clipboard text"):
        service.clipboard.publish("x" * (VirtualClipboardAdapter.MAX_TEXT_CHARS + 1))
