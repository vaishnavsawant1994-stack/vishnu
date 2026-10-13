from __future__ import annotations

import asyncio

import pytest

from core.events import EventBus
from desktop.input_clipboard import MemoryClipboardAdapter
from devices.registry import DeviceRegistry
from sensorium.physical import DesktopPhysicalSensorAdapter, MobilePhysicalSensorAdapter


class _ApplicationObserver:
    def capture(self):
        return {
            "captured_at": 1.0,
            "platform": "windows",
            "available": True,
            "application": "editor",
            "executable": "editor.exe",
            "process_id": 7,
            "window_id": "hwnd:7",
            "window_title": "PRIVATE WINDOW TITLE",
            "window_title_sha256": "abc123",
            "identity_digest": "identity",
            "source": "test",
        }


class _Computer:
    def __init__(self):
        self.calls = []

    def observe(self, question, monitor=1):
        self.calls.append((question, monitor))
        return {
            "analysis": "PRIVATE SCREEN CONTENT",
            "screenshot_evidence_ref": "evidence/private-screen.png",
            "screen_fingerprint": "screen-fingerprint",
            "raw_bytes": b"never return this",
        }


class _Gateway:
    def __init__(self):
        self.actions = []

    async def request(self, device_id, command, timeout=15):
        self.actions.append((device_id, command.action, command.parameters, timeout))
        if command.action == "device_info":
            result = {"manufacturer": "Example", "model": "Phone", "sdk": 35, "ignored": "drop-me"}
        elif command.action == "battery":
            result = {"percent": 73, "state": "charging", "ignored": "drop-me"}
        else:
            raise AssertionError(f"side-effecting action reached fake gateway: {command.action}")
        return {
            "device_id": device_id,
            "type": "result",
            "request_id": command.request_id,
            "ok": True,
            "result": result,
        }


def _device(registry: DeviceRegistry, name: str, scopes: set[str]):
    device, _token = registry.enroll(name, "pytest")
    registry.set_permissions(device["id"], scopes)
    return device


def test_desktop_system_context_strips_raw_window_title(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read"})
    adapter = DesktopPhysicalSensorAdapter(
        registry,
        clipboard_adapter=MemoryClipboardAdapter("secret"),
        application_observer=_ApplicationObserver(),
    )

    result = adapter.observe_system(controller["id"])

    assert result["execution_authority"] is False
    assert result["instruction_trust"] == "untrusted"
    assert "window_title" not in result["system"]["application"]
    assert result["system"]["application"]["window_title_sha256"] == "abc123"


def test_desktop_clipboard_is_metadata_only_without_sensitive_scope(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "reader", {"device:read"})
    adapter = DesktopPhysicalSensorAdapter(
        registry,
        clipboard_adapter=MemoryClipboardAdapter("TOP SECRET CLIPBOARD"),
        application_observer=_ApplicationObserver(),
    )

    result = adapter.observe_clipboard(controller["id"])

    assert "text" not in result["clipboard"]
    assert result["clipboard"]["size"] > 0
    with pytest.raises(PermissionError):
        adapter.observe_clipboard(controller["id"], include_content=True)


def test_sensitive_scope_may_read_clipboard_but_event_bus_never_receives_content(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read", "memory:sensitive"})
    events = EventBus()
    observed_events = []
    events.subscribe("sensorium.physical.observed", observed_events.append)
    adapter = DesktopPhysicalSensorAdapter(
        registry,
        clipboard_adapter=MemoryClipboardAdapter("TOP SECRET CLIPBOARD"),
        application_observer=_ApplicationObserver(),
        event_bus=events,
    )

    result = adapter.observe_clipboard(controller["id"], include_content=True)

    assert result["clipboard"]["text"] == "TOP SECRET CLIPBOARD"
    assert "TOP SECRET CLIPBOARD" not in repr(observed_events)


def test_desktop_screen_uses_existing_observer_and_never_returns_evidence_path(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read", "memory:sensitive"})
    events = EventBus()
    observed_events = []
    events.subscribe("sensorium.physical.observed", observed_events.append)
    computer = _Computer()
    adapter = DesktopPhysicalSensorAdapter(
        registry,
        computer=computer,
        clipboard_adapter=MemoryClipboardAdapter(),
        application_observer=_ApplicationObserver(),
        event_bus=events,
    )

    result = adapter.observe_screen(controller["id"], question="What is visible?", monitor=1)

    assert computer.calls == [("What is visible?", 1)]
    assert result["screen"]["analysis"] == "PRIVATE SCREEN CONTENT"
    assert result["screen"]["evidence_available"] is True
    assert "screenshot_evidence_ref" not in repr(result)
    assert "private-screen.png" not in repr(result)
    assert "PRIVATE SCREEN CONTENT" not in repr(observed_events)
    assert not hasattr(adapter, "click")
    assert not hasattr(adapter, "type_text")


def test_desktop_screen_requires_sensitive_scope(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "reader", {"device:read"})
    adapter = DesktopPhysicalSensorAdapter(
        registry,
        computer=_Computer(),
        clipboard_adapter=MemoryClipboardAdapter(),
        application_observer=_ApplicationObserver(),
    )

    with pytest.raises(PermissionError):
        adapter.observe_screen(controller["id"])


def test_mobile_observation_allows_only_device_info_and_battery(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read", "device:admin"})
    target = _device(registry, "phone", {"device:read"})
    gateway = _Gateway()
    events = EventBus()
    observed_events = []
    events.subscribe("sensorium.physical.observed", observed_events.append)
    adapter = MobilePhysicalSensorAdapter(registry, gateway, event_bus=events)

    result = asyncio.run(adapter.observe(controller["id"], target["id"]))

    assert [row[1] for row in gateway.actions] == ["device_info", "battery"]
    assert all(row[2] == {} for row in gateway.actions)
    assert result["device_info"] == {"manufacturer": "Example", "model": "Phone", "sdk": 35}
    assert result["battery"] == {"percent": 73, "state": "charging"}
    assert result["execution_authority"] is False
    assert "drop-me" not in repr(result)
    assert "Example" not in repr(observed_events)


def test_cross_device_mobile_observation_requires_device_admin(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "reader", {"device:read"})
    target = _device(registry, "phone", {"device:read"})
    adapter = MobilePhysicalSensorAdapter(registry, _Gateway())

    with pytest.raises(PermissionError):
        asyncio.run(adapter.observe(controller["id"], target["id"]))


def test_revoked_mobile_target_fails_closed(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read", "device:admin"})
    target = _device(registry, "phone", {"device:read"})
    registry.revoke(target["id"])
    adapter = MobilePhysicalSensorAdapter(registry, _Gateway())

    with pytest.raises(PermissionError):
        asyncio.run(adapter.observe(controller["id"], target["id"]))


def test_mobile_adapter_rejects_side_effecting_gateway_actions(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller = _device(registry, "owner", {"device:read", "device:admin"})
    adapter = MobilePhysicalSensorAdapter(registry, _Gateway())

    with pytest.raises(PermissionError):
        asyncio.run(adapter._request(controller["id"], "open_url", 5))
    with pytest.raises(PermissionError):
        asyncio.run(adapter._request(controller["id"], "flashlight", 5))
    with pytest.raises(PermissionError):
        asyncio.run(adapter._request(controller["id"], "launch_app", 5))
