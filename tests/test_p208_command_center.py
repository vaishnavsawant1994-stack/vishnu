"""P2-08 device-bound command history never grants execution authority."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from security.request_context import TrustedRequestContext, set_trusted_request, reset_trusted_request

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

    def is_active(self, device):
        return not self.revoked and device in self.metadata_by_device

    def metadata(self, device):
        return self.metadata_by_device[device]

    def set_metadata(self, device, key, value):
        if self.revoked or device not in self.metadata_by_device:
            return False
        self.metadata_by_device[device][key] = value
        return True


class ContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled=True, bound_device='d1'):
        super().__init__(app)
        self.enabled=enabled
        self.bound_device=bound_device

    async def dispatch(self, request, call_next):
        if not self.enabled:
            return await call_next(request)
        token=set_trusted_request(TrustedRequestContext(self.bound_device, 'session1'))
        try:
            return await call_next(request)
        finally:
            reset_trusted_request(token)


def client(*, context=True, bound_device='d1'):
    registry = Devices()
    app = FastAPI()
    app.add_middleware(ContextMiddleware, enabled=context, bound_device=bound_device)
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
    assert c.post(api,json={"command_id":"home"}).status_code == 401
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


def test_mutations_require_active_bound_context_even_when_cookies_are_valid():
    c,_=client(context=False)
    c.cookies.set('pa_device','d1'); c.cookies.set('pa_token','first')
    path='/iphone/api/command-center/recent'
    assert c.get(path).status_code == 200
    assert c.post(path,json={'command_id':'home'}).status_code == 401
    assert c.delete(path).status_code == 401
    mismatch,_=client(bound_device='d2')
    mismatch.cookies.set('pa_device','d1');mismatch.cookies.set('pa_token','first')
    assert mismatch.post(path,json={'command_id':'home'}).status_code == 401
