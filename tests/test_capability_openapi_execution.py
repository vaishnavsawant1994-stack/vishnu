from __future__ import annotations

import json
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from integrations.registry import IntegrationRegistry
from memory.store import MemoryStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from security.vault import SecretVault
from server import apps_tools_api
from server.apps_tools_api import apps_tools_router
from tools.registry import ToolRegistry


class Devices:
    def is_active(self, device_id):
        return device_id == "owner-device"

    def authorize(self, device_id, scope):
        return device_id == "owner-device" and scope in {"device:read", "device:admin"}


class State:
    def __init__(self, path):
        self.path = path
        self.events = []

    def audit(self, event_type, **kwargs):
        self.events.append((event_type, kwargs))

    def set_health(self, *args, **kwargs):
        pass


class OwnerContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = set_trusted_request(TrustedRequestContext("owner-device", "owner-session", time.time()))
        try:
            return await call_next(request)
        finally:
            reset_trusted_request(token)


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload):
        self._body = json.dumps(payload).encode()
        self.content = self._body

    def iter_content(self, size):
        yield self._body

    def json(self):
        return json.loads(self._body)

    def close(self):
        pass


def test_owner_discovers_approves_connects_executes_and_revokes_get(tmp_path, monkeypatch):
    calls = []

    class Session:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse({"forecast": "sunny"})

    monkeypatch.setattr(apps_tools_api, "_public_https_url", lambda url: url.rstrip("/"))
    monkeypatch.setattr("integrations.discovery.execution._public_https_url", lambda url: url.rstrip("/"))
    monkeypatch.setattr("integrations.discovery.execution.requests.Session", Session)

    tools = ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path))
    integrations = IntegrationRegistry()
    state = State(tmp_path / "integrations.sqlite3")
    integrations.state_store = state
    vault = SecretVault(tmp_path / "vault.json")
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    runtime = {
        "device_registry": Devices(), "tools": tools, "integrations": integrations,
        "memory": memory, "vault": vault,
    }
    app = FastAPI()
    app.add_middleware(OwnerContextMiddleware)
    app.include_router(apps_tools_router(runtime))
    client = TestClient(app)

    spec = {
        "openapi": "3.1.0", "info": {"title": "Weather", "version": "1"},
        "servers": [{"url": "https://weather.example/api"}],
        "paths": {"/forecast": {"get": {
            "summary": "Read forecast",
            "parameters": [{"name": "city", "in": "query", "required": True, "schema": {"type": "string", "maxLength": 80}}],
        }}},
    }
    discovered = client.post("/iphone/api/apps-tools/capabilities/openapi", json={"document": spec})
    assert discovered.status_code == 200
    assert discovered.json() == {"discovered": 1, "executable": False}
    capability = client.get("/iphone/api/apps-tools/capabilities?query=forecast").json()["capabilities"][0]
    capability_id = capability["id"]

    connected = client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/connect", json={
        "auth_type": "bearer_token", "api_key": "secret-test-token",
    })
    assert connected.status_code == 200, connected.text
    assert "secret-test-token" not in connected.text
    assert "credential_ref" not in connected.text
    assert vault.names()

    executed = client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/execute", json={
        "parameters": {"city": "Oslo"},
    })
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"] == {"forecast": "sunny"}
    assert executed.json()["verified"] is True
    assert calls[0][0] == "GET"
    assert calls[0][1] == "https://weather.example/api/forecast"
    assert calls[0][2]["params"] == {"city": "Oslo"}
    assert calls[0][2]["headers"]["Authorization"] == "Bearer secret-test-token"
    assert {event for event, _ in state.events} >= {
        "capability.discovered", "capability.approved", "capability.execution.started", "capability.execution.succeeded",
    }

    detail = client.get(f"/iphone/api/apps-tools/capabilities/{capability_id}").json()["capability"]
    assert detail["connection"]["status"] == "connected"
    assert "credential_ref" not in detail["connection"]
    revoked = client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/disconnect")
    assert revoked.status_code == 200
    assert not vault.names()
    assert client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/execute", json={"parameters": {"city": "Oslo"}}).status_code == 409


def test_execution_parameter_validator_rejects_undeclared_and_missing_values():
    from integrations.discovery.execution import _validate_parameters

    capability = {
        "path": "/forecast/{region}",
        "parameters": [
            {"name": "region", "in": "path", "type": "string", "required": True, "max_length": 20},
            {"name": "units", "in": "query", "type": "string", "required": False, "enum": ["metric", "imperial"]},
        ],
    }
    assert _validate_parameters(capability, {"region": "north", "units": "metric"}) == ("/forecast/north", {"units": "metric"})
    for parameters in ({}, {"region": "north", "extra": "value"}, {"region": "north", "units": "other"}):
        try:
            _validate_parameters(capability, parameters)
        except ValueError:
            continue
        raise AssertionError("invalid OpenAPI parameters should be rejected")
