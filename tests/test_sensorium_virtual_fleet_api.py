from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events import EventBus
from devices.registry import DeviceRegistry
from server.sensorium_api import sensorium_router


def _client(tmp_path, scopes: set[str]):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    device, token = registry.enroll("Virtual fleet owner", "pytest")
    registry.set_permissions(device["id"], scopes)
    runtime = {"events": EventBus(), "device_registry": registry}
    app = FastAPI()
    app.include_router(sensorium_router(runtime))
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "X-Device-ID": device["id"]}
    return client, registry, device, headers, runtime


def _provision(client: TestClient, headers: dict[str, str], device_id="virtual-android-1", platform="android"):
    return client.post(
        f"/sensorium/virtual-fleet/{device_id}",
        headers=headers,
        json={"platform": platform, "name": f"CI {platform}"},
    )


def test_virtual_fleet_api_provisions_android_ios_and_desktop_profiles(tmp_path):
    client, _registry, _device, headers, runtime = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )

    profiles = client.get("/sensorium/virtual-fleet/profiles", headers=headers)
    assert profiles.status_code == 200
    assert {item["platform"] for item in profiles.json()["profiles"]} == {
        "android",
        "ios",
        "windows",
        "macos",
        "linux",
    }
    assert profiles.json()["execution_authority"] is False

    for device_id, platform in (
        ("android-1", "android"),
        ("iphone-1", "ios"),
        ("windows-1", "windows"),
        ("mac-1", "macos"),
        ("linux-1", "linux"),
    ):
        created = _provision(client, headers, device_id, platform)
        assert created.status_code == 200
        assert created.json()["runtime"]["platform"] == platform
        assert created.json()["runtime"]["execution_authority"] is False

    listed = client.get("/sensorium/virtual-fleet", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["devices"]) == 5
    assert runtime["sensorium_virtual_fleet"] is not None


def test_virtual_fleet_api_simulates_runtime_state_and_transport_recovery(tmp_path):
    client, _registry, _device, headers, _runtime = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )
    assert _provision(client, headers).status_code == 200

    battery = client.post(
        "/sensorium/virtual-fleet/virtual-android-1/battery",
        headers=headers,
        json={"percent": 37, "charging": True},
    )
    assert battery.status_code == 200
    assert battery.json()["runtime"]["battery_percent"] == 37

    network = client.post(
        "/sensorium/virtual-fleet/virtual-android-1/network",
        headers=headers,
        json={"network_type": "cellular", "signal_percent": 53},
    )
    assert network.status_code == 200
    assert network.json()["runtime"]["network"]["type"] == "cellular"

    assert client.post(
        "/sensorium/virtual-fleet/virtual-android-1/lock",
        headers=headers,
        json={"locked": True},
    ).json()["runtime"]["locked"] is True

    disconnected = client.post(
        "/sensorium/virtual-fleet/virtual-android-1/disconnect", headers=headers
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["device"]["state"] == "offline"

    reconnected = client.post(
        "/sensorium/virtual-fleet/virtual-android-1/reconnect", headers=headers
    )
    assert reconnected.status_code == 200
    assert reconnected.json()["device_state"] == "online"


def test_sensitive_virtual_fixture_content_is_scope_gated_and_not_returned(tmp_path):
    client, _registry, _device, headers, _runtime = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )
    assert _provision(client, headers, "iphone-1", "ios").status_code == 200

    for permission in ("camera", "microphone", "notifications", "location"):
        response = client.post(
            f"/sensorium/virtual-fleet/iphone-1/permissions/{permission}",
            headers=headers,
            json={"state": "granted"},
        )
        assert response.status_code == 200

    camera = client.post(
        "/sensorium/virtual-fleet/iphone-1/camera-fixture",
        headers=headers,
        json={"fixture_ref": "SECRET CAMERA FIXTURE", "analysis": "SECRET CAMERA ANALYSIS"},
    )
    assert camera.status_code == 200
    assert "SECRET" not in repr(camera.json())

    microphone = client.post(
        "/sensorium/virtual-fleet/iphone-1/microphone-fixture",
        headers=headers,
        json={"fixture_ref": "SECRET AUDIO FIXTURE", "transcript": "SECRET TRANSCRIPT"},
    )
    assert microphone.status_code == 200
    assert "SECRET" not in repr(microphone.json())

    notification = client.post(
        "/sensorium/virtual-fleet/iphone-1/notification",
        headers=headers,
        json={"title": "SECRET TITLE", "body": "SECRET BODY", "app_id": "fixture.messages"},
    )
    assert notification.status_code == 200
    assert "SECRET" not in repr(notification.json())

    location = client.post(
        "/sensorium/virtual-fleet/iphone-1/location",
        headers=headers,
        json={"latitude": 50.1109, "longitude": 8.6821, "accuracy_meters": 5},
    )
    assert location.status_code == 200
    assert location.json()["runtime"]["location"]["available"] is True


def test_sensitive_virtual_fixtures_fail_without_sensitive_scope(tmp_path):
    client, _registry, _device, headers, _runtime = _client(
        tmp_path, {"device:read", "device:admin"}
    )
    assert _provision(client, headers, "iphone-1", "ios").status_code == 200
    assert client.post(
        "/sensorium/virtual-fleet/iphone-1/permissions/camera",
        headers=headers,
        json={"state": "granted"},
    ).status_code == 200

    response = client.post(
        "/sensorium/virtual-fleet/iphone-1/camera-fixture",
        headers=headers,
        json={"fixture_ref": "fixture-camera"},
    )
    assert response.status_code == 403


def test_read_only_controller_cannot_mutate_virtual_fleet(tmp_path):
    client, _registry, _device, headers, _runtime = _client(tmp_path, {"device:read"})
    assert client.get("/sensorium/virtual-fleet/profiles", headers=headers).status_code == 200
    assert _provision(client, headers).status_code == 403


def test_virtual_fault_endpoint_is_simulation_only(tmp_path):
    client, _registry, _device, headers, _runtime = _client(
        tmp_path, {"device:read", "device:admin"}
    )
    assert _provision(client, headers).status_code == 200
    response = client.post(
        "/sensorium/virtual-fleet/virtual-android-1/fault",
        headers=headers,
        json={"fault": "low_battery"},
    )
    assert response.status_code == 200
    assert response.json()["runtime"]["battery_percent"] == 5
    assert response.json()["execution_authority"] is False


def test_virtual_fleet_routes_do_not_add_physical_execution_authority(tmp_path):
    client, _registry, _device, _headers, _runtime = _client(
        tmp_path, {"device:read", "device:admin", "memory:sensitive"}
    )
    openapi = client.app.openapi()["paths"]
    fleet_paths = {path: methods for path, methods in openapi.items() if path.startswith("/sensorium/virtual-fleet")}
    assert fleet_paths
    forbidden = ("mouse", "keyboard", "click", "type-text", "open-url", "launch-app", "install-package")
    assert not any(fragment in path for fragment in forbidden for path in fleet_paths)
