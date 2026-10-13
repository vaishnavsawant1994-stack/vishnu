from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from devices.registry import DeviceRegistry
from sensorium.physical import MobilePhysicalSensorAdapter
from server.sensorium_physical_api import sensorium_physical_router


class _Desktop:
    def __init__(self):
        self.calls = []

    def context_snapshot(
        self,
        device_id,
        *,
        include_clipboard_content=False,
        include_screen_analysis=False,
        monitor=1,
    ):
        self.calls.append(
            (device_id, include_clipboard_content, include_screen_analysis, monitor)
        )
        return {
            "physical": True,
            "platform": "desktop",
            "clipboard": {"text": "SECRET"} if include_clipboard_content else {"size": 6},
            "screen": {"analysis": "VISIBLE"} if include_screen_analysis else None,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }


class _Gateway:
    def __init__(self):
        self.actions = []

    async def request(self, device_id, command, timeout=15):
        self.actions.append(command.action)
        result = (
            {"name": "Phone", "system": "iOS", "version": "27.0"}
            if command.action == "device_info"
            else {"percent": 91, "state": 2}
        )
        return {
            "device_id": device_id,
            "type": "result",
            "request_id": command.request_id,
            "ok": True,
            "result": result,
        }


def _enroll(registry, name, scopes):
    device, token = registry.enroll(name, "pytest")
    registry.set_permissions(device["id"], set(scopes))
    return device, token


def _client(tmp_path, scopes):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    controller, token = _enroll(registry, "controller", scopes)
    desktop = _Desktop()
    gateway = _Gateway()
    mobile = MobilePhysicalSensorAdapter(registry, gateway)
    runtime = {
        "device_registry": registry,
        "device_gateway": gateway,
        "sensorium_desktop": desktop,
        "sensorium_mobile": mobile,
    }
    app = FastAPI()
    app.include_router(sensorium_physical_router(runtime))
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Device-ID": controller["id"],
    }
    return client, registry, controller, desktop, gateway, headers


def test_desktop_physical_api_requires_admin_scope(tmp_path):
    client, _registry, _controller, desktop, _gateway, headers = _client(
        tmp_path, {"device:read"}
    )

    response = client.get("/sensorium/physical/desktop/context", headers=headers)

    assert response.status_code == 403
    assert desktop.calls == []


def test_desktop_sensitive_observation_requires_sensitive_scope(tmp_path):
    client, _registry, _controller, desktop, _gateway, headers = _client(
        tmp_path, {"device:read", "device:admin"}
    )

    response = client.get(
        "/sensorium/physical/desktop/context?include_screen_analysis=true",
        headers=headers,
    )

    assert response.status_code == 403
    assert desktop.calls == []


def test_desktop_physical_api_passes_only_read_options(tmp_path):
    client, _registry, controller, desktop, _gateway, headers = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )

    response = client.get(
        "/sensorium/physical/desktop/context?include_clipboard_content=true&include_screen_analysis=true&monitor=2",
        headers=headers,
    )

    assert response.status_code == 200
    assert desktop.calls == [(controller["id"], True, True, 2)]
    assert response.json()["execution_authority"] is False


def test_mobile_cross_device_api_requires_admin_and_uses_only_read_actions(tmp_path):
    client, registry, controller, _desktop, gateway, headers = _client(
        tmp_path, {"device:read"}
    )
    target, _target_token = _enroll(registry, "phone", {"device:read"})

    denied = client.get(
        f"/sensorium/physical/mobile/{target['id']}/context",
        headers=headers,
    )
    assert denied.status_code == 403
    assert gateway.actions == []

    registry.set_permissions(controller["id"], {"device:read", "device:admin"})
    allowed = client.get(
        f"/sensorium/physical/mobile/{target['id']}/context",
        headers=headers,
    )
    assert allowed.status_code == 200
    assert gateway.actions == ["device_info", "battery"]
    assert allowed.json()["execution_authority"] is False


def test_revoked_mobile_target_is_not_observable(tmp_path):
    client, registry, controller, _desktop, gateway, headers = _client(
        tmp_path, {"device:read", "device:admin"}
    )
    target, _target_token = _enroll(registry, "phone", {"device:read"})
    registry.revoke(target["id"])

    response = client.get(
        f"/sensorium/physical/mobile/{target['id']}/context",
        headers=headers,
    )

    assert response.status_code == 403
    assert gateway.actions == []


def test_physical_sensorium_surface_has_no_side_effect_routes(tmp_path):
    client, _registry, _controller, _desktop, _gateway, _headers = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )
    routes = {
        path: set(operation.keys())
        for path, operation in client.app.openapi().get("paths", {}).items()
        if path.startswith("/sensorium/physical")
    }

    assert routes
    assert all(methods <= {"get"} for methods in routes.values())
    forbidden = {
        "click",
        "keyboard",
        "mouse",
        "type",
        "open_url",
        "launch_app",
        "flashlight",
        "notification",
    }
    assert not any(fragment in path for path in routes for fragment in forbidden)
