from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events import EventBus
from devices.registry import DeviceRegistry
from server.sensorium_api import sensorium_router


def _client(tmp_path, scopes: set[str]):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    device, token = registry.enroll("Test owner", "pytest")
    registry.set_permissions(device["id"], scopes)
    runtime = {"events": EventBus(), "device_registry": registry}
    app = FastAPI()
    app.include_router(sensorium_router(runtime))
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Device-ID": device["id"],
    }
    return client, registry, device, headers


def _create_virtual(client: TestClient, headers: dict[str, str], capabilities=None):
    return client.post(
        "/sensorium/virtual-devices",
        headers=headers,
        json={
            "device_id": "virtual-desktop-1",
            "name": "CI desktop",
            "platform": "virtual-windows",
            "capabilities": capabilities or ["screen", "clipboard", "system"],
        },
    )


def test_sensorium_api_virtual_flow_and_planner_boundary(tmp_path):
    client, _registry, _device, headers = _client(
        tmp_path,
        {"device:read", "device:admin", "memory:sensitive"},
    )

    created = _create_virtual(client, headers)
    assert created.status_code == 200

    screen = client.post(
        "/sensorium/virtual-devices/virtual-desktop-1/screen",
        headers=headers,
        json={"analysis": "Settings page with Save button", "width": 1440, "height": 900},
    )
    assert screen.status_code == 200
    assert "payload" not in screen.json()["event"]

    clipboard = client.post(
        "/sensorium/virtual-devices/virtual-desktop-1/clipboard",
        headers=headers,
        json={"text": "sensitive value"},
    )
    assert clipboard.status_code == 200
    assert "sensitive value" not in repr(clipboard.json())

    system = client.post(
        "/sensorium/virtual-devices/virtual-desktop-1/system",
        headers=headers,
        json={"metrics": {"battery_percent": 80, "network_online": True}},
    )
    assert system.status_code == 200

    context = client.get(
        "/sensorium/virtual-devices/virtual-desktop-1/context",
        headers=headers,
    )
    assert context.status_code == 200
    assert context.json()["execution_authority"] is False
    assert "text" not in context.json()["clipboard"]

    planner = client.get(
        "/sensorium/virtual-devices/virtual-desktop-1/planner-observation",
        headers=headers,
    )
    assert planner.status_code == 200
    assert planner.json()["sensorium_virtual"] is True
    assert planner.json()["screenshot_evidence_ref"] is None
    assert planner.json()["sensorium_context"]["execution_authority"] is False


def test_raw_clipboard_context_requires_sensitive_scope(tmp_path):
    client, _registry, _device, headers = _client(tmp_path, {"device:read", "device:admin"})
    assert _create_virtual(client, headers, ["clipboard"]).status_code == 200
    assert client.post(
        "/sensorium/virtual-devices/virtual-desktop-1/clipboard",
        headers=headers,
        json={"text": "secret"},
    ).status_code == 200

    response = client.get(
        "/sensorium/virtual-devices/virtual-desktop-1/context?include_clipboard_content=true",
        headers=headers,
    )
    assert response.status_code == 403


def test_read_only_device_cannot_create_or_inject_virtual_sensor_data(tmp_path):
    client, _registry, _device, headers = _client(tmp_path, {"device:read"})
    response = _create_virtual(client, headers)
    assert response.status_code == 403


def test_revoked_device_loses_sensorium_access(tmp_path):
    client, registry, device, headers = _client(tmp_path, {"device:read", "device:admin"})
    assert _create_virtual(client, headers).status_code == 200
    assert registry.revoke(device["id"]) is True

    response = client.get("/sensorium/virtual-devices", headers=headers)
    assert response.status_code == 401


def test_sensorium_api_has_no_physical_capture_or_input_routes(tmp_path):
    client, _registry, _device, _headers = _client(
        tmp_path,
        {"device:read", "device:admin", "memory:sensitive"},
    )
    paths = {route.path for route in client.app.routes}
    forbidden_fragments = {
        "camera-capture",
        "microphone-capture",
        "screen-capture",
        "keyboard",
        "mouse",
        "desktop-execute",
    }
    assert not any(fragment in path for fragment in forbidden_fragments for path in paths)
