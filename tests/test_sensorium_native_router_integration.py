from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events import EventBus
from devices.registry import DeviceRegistry
from server.sensorium_physical_api import sensorium_physical_router


def test_physical_sensorium_router_composes_native_evidence_routes_with_full_runtime(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    device, token = registry.enroll("Native integration owner", "pytest")
    registry.set_permissions(device["id"], {"device:read", "device:admin"})
    runtime = {
        "device_registry": registry,
        "device_gateway": None,
        "events": EventBus(),
        "settings": SimpleNamespace(data_dir=tmp_path),
    }
    app = FastAPI()
    app.include_router(sensorium_physical_router(runtime), prefix="/owner/ai")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "X-Device-ID": device["id"]}

    schema = client.app.openapi()
    assert "/owner/ai/sensorium/physical/desktop/context" in schema["paths"]
    assert "/owner/ai/sensorium/native/providers" in schema["paths"]
    assert "/owner/ai/sensorium/native/evidence" in schema["paths"]

    response = client.get("/owner/ai/sensorium/native/providers", headers=headers)
    assert response.status_code == 200
    assert response.json()["execution_authority"] is False
    assert response.json()["physical_device"] is False

    native_lab = runtime.get("sensorium_native_lab")
    assert native_lab is not None
    native_lab.close()


def test_minimal_physical_sensorium_runtime_keeps_legacy_routes_without_native_storage(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.sqlite3")
    runtime = {"device_registry": registry, "device_gateway": None, "events": EventBus()}
    app = FastAPI()
    app.include_router(sensorium_physical_router(runtime), prefix="/owner/ai")
    schema = app.openapi()

    assert "/owner/ai/sensorium/physical/desktop/context" in schema["paths"]
    assert "/owner/ai/sensorium/native/providers" not in schema["paths"]
