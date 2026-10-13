from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events import EventBus
from devices.registry import DeviceRegistry
from sensorium.native_lab import NativeDeviceLab
from server.sensorium_native_api import sensorium_native_router


def _client(tmp_path, scopes: set[str]):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    device, token = registry.enroll("Native qualification owner", "pytest")
    registry.set_permissions(device["id"], scopes)
    native = NativeDeviceLab(tmp_path / "native.sqlite3", event_bus=EventBus())
    runtime = {"device_registry": registry, "sensorium_native_lab": native}
    app = FastAPI()
    app.include_router(sensorium_native_router(runtime), prefix="/owner/ai")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "X-Device-ID": device["id"]}
    return client, registry, native, device, headers


def _payload(**overrides):
    value = {
        "schema_version": 1,
        "provider": "android_emulator",
        "platform": "android",
        "target_id": "emulator-5554",
        "status": "ready",
        "os_version": "Android 15 (API 35)",
        "architecture": "x86_64",
        "capabilities": ["battery", "instrumentation"],
        "metadata": {"environment_kind": "vendor_emulator", "model": "sdk_gphone64_x86_64"},
        "observed_at": datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc).isoformat(),
        "source": "android-emulator-probe",
        "physical_device": False,
        "execution_authority": False,
    }
    value.update(overrides)
    return value


def test_native_api_lists_providers_and_records_read_only_evidence(tmp_path):
    client, _registry, native, _device, headers = _client(tmp_path, {"device:read", "device:admin"})
    try:
        providers = client.get("/owner/ai/sensorium/native/providers", headers=headers)
        assert providers.status_code == 200
        body = providers.json()
        assert {item["provider"] for item in body["providers"]} == {
            "android_emulator",
            "ios_simulator",
            "desktop_vm",
        }
        assert body["physical_device"] is False
        assert body["execution_authority"] is False

        recorded = client.post("/owner/ai/sensorium/native/evidence", headers=headers, json=_payload())
        assert recorded.status_code == 200
        assert recorded.json()["evidence"]["target_id"] == "emulator-5554"
        assert recorded.json()["evidence"]["execution_authority"] is False

        listed = client.get("/owner/ai/sensorium/native/evidence?provider=android_emulator", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()["evidence"]) == 1
        assert listed.json()["evidence"][0]["provider"] == "android_emulator"
    finally:
        native.close()


def test_native_api_requires_admin_to_record_evidence(tmp_path):
    client, _registry, native, _device, headers = _client(tmp_path, {"device:read"})
    try:
        assert client.get("/owner/ai/sensorium/native/providers", headers=headers).status_code == 200
        response = client.post("/owner/ai/sensorium/native/evidence", headers=headers, json=_payload())
        assert response.status_code == 403
    finally:
        native.close()


def test_native_api_revocation_fails_closed(tmp_path):
    client, registry, native, device, headers = _client(tmp_path, {"device:read", "device:admin"})
    try:
        assert registry.revoke(device["id"]) is True
        assert client.get("/owner/ai/sensorium/native/providers", headers=headers).status_code == 401
    finally:
        native.close()


def test_native_api_rejects_secret_metadata_and_false_physical_claims(tmp_path):
    client, _registry, native, _device, headers = _client(tmp_path, {"device:read", "device:admin"})
    try:
        secret = client.post(
            "/owner/ai/sensorium/native/evidence",
            headers=headers,
            json=_payload(metadata={"api_key": "must-not-persist"}),
        )
        assert secret.status_code == 422

        physical = client.post(
            "/owner/ai/sensorium/native/evidence",
            headers=headers,
            json=_payload(physical_device=True),
        )
        assert physical.status_code == 422

        authority = client.post(
            "/owner/ai/sensorium/native/evidence",
            headers=headers,
            json=_payload(execution_authority=True),
        )
        assert authority.status_code == 422
    finally:
        native.close()


def test_native_api_exposes_evidence_only_not_native_command_execution(tmp_path):
    client, _registry, native, _device, _headers = _client(tmp_path, {"device:read", "device:admin"})
    try:
        schema = client.app.openapi()
        paths = {
            path: set(methods)
            for path, methods in schema["paths"].items()
            if path.startswith("/owner/ai/sensorium/native")
        }
        assert paths
        assert paths["/owner/ai/sensorium/native/providers"] <= {"get"}
        assert paths["/owner/ai/sensorium/native/evidence"] <= {"get", "post"}
        forbidden = {
            "probe",
            "adb",
            "simctl",
            "shell",
            "execute",
            "subprocess",
            "keyboard",
            "mouse",
            "open_url",
            "launch_app",
            "vm-control",
        }
        assert not any(fragment in path.lower() for path in paths for fragment in forbidden)
    finally:
        native.close()
