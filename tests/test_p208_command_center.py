"""P2-08 device-bound command history never grants execution authority."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.command_center_api import command_center_router


class Devices:
    def __init__(self):
        self.revoked = False
        self.allowed = True
        self.metadata_by_device = {"d1": {}, "d2": {}}

    def authenticate(self, device, token):
        return not self.revoked and (device, token) in {("d1", "first"), ("d2", "second")}

    def authorize(self, device, scope):
        return self.allowed and scope == "ai:chat"

    def metadata(self, device):
        return self.metadata_by_device[device]

    def set_metadata(self, device, key, value):
        if self.revoked or device not in self.metadata_by_device:
            return False
        self.metadata_by_device[device][key] = value
        return True


def client():
    registry = Devices()
    app = FastAPI()
    app.include_router(command_center_router({"device_registry": registry}))
    return TestClient(app), registry


def test_recent_requires_trusted_device_and_scopes():
    c, devices = client()
    assert c.get("/iphone/api/command-center/recent").status_code == 401
    c.cookies.set("pa_device", "d1")
    c.cookies.set("pa_token", "first")
    assert c.get("/iphone/api/command-center/recent").status_code == 200
    devices.allowed = False
    assert c.get("/iphone/api/command-center/recent").status_code == 403
    devices.allowed = True
    devices.revoked = True
    assert c.post("/iphone/api/command-center/recent", json={"command_id": "new-task"}).status_code == 401


def test_history_stable_ids_dedupe_persistence_and_device_separation():
    c, registry = client()
    c.cookies.set("pa_device", "d1")
    c.cookies.set("pa_token", "first")
    api = "/iphone/api/command-center/recent"
    assert c.post(api, json={"command_id": "new-project"}).status_code == 200
    assert c.post(api, json={"command_id": "new-workspace"}).status_code == 200
    assert c.post(api, json={"command_id": "new-project"}).status_code == 200
    data = c.get(api).json()
    assert [x["id"] for x in data["recent"]] == ["new-project", "new-workspace"]
    assert data["scope"] == "trusted_device"
    assert all(len(x["at"]) > 15 for x in data["recent"])
    assert c.post(api, json={"command_id": "__proto__"}).status_code == 422
    assert c.post(api, json={"command_id": "new-task", "secret": "do not keep"}).status_code == 422
    assert "do not keep" not in str(registry.metadata_by_device)
    c.cookies.set("pa_device", "d2")
    c.cookies.set("pa_token", "second")
    assert c.get(api).json()["recent"] == []
    c.cookies.set("pa_device", "d1")
    c.cookies.set("pa_token", "first")
    assert c.delete(api).json() == {"cleared": True}
    assert c.get(api).json()["recent"] == []


def test_history_does_not_expose_execution_mutations():
    c, _ = client()
    router = command_center_router({"device_registry": Devices()})
    definitions = {(route.path, frozenset(route.methods or [])) for route in router.routes}
    assert definitions == {
        ("/iphone/api/command-center/recent", frozenset({"GET"})),
        ("/iphone/api/command-center/recent", frozenset({"POST"})),
        ("/iphone/api/command-center/recent", frozenset({"DELETE"})),
    }
