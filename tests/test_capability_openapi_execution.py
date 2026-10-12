from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from integrations.registry import IntegrationRegistry
from integrations.discovery.execution import _resolve_public_addresses
from integrations.state import ConnectorStateStore
from memory.store import MemoryStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from security.approvals import ApprovalManager
from security.vault import SecretVault
from server import apps_tools_api
from server.apps_tools_api import apps_tools_router
from tools.registry import ToolRegistry


class Devices:
    def is_active(self, device_id):
        return device_id == "owner-device"

    def authorize(self, device_id, scope):
        return device_id == "owner-device" and scope in {"device:read", "device:admin"}


def test_dns_resolution_rejects_mixed_public_and_private_answers(monkeypatch):
    public = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    private = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
    monkeypatch.setattr("integrations.discovery.execution.socket.getaddrinfo", lambda *args, **kwargs: [public, private])
    try:
        _resolve_public_addresses("provider.example")
    except ValueError as exc:
        assert "public IP" in str(exc)
    else:
        raise AssertionError("mixed DNS answers must fail closed")


class State:
    def __init__(self, path):
        self.path = path
        self.events = []
        self.lifecycle = self

    def audit(self, event_type, **kwargs):
        self.events.append((event_type, kwargs))

    def set_health(self, *args, **kwargs):
        pass

    def entries(self, limit=200):
        return [{"id": str(index), "action": event, "created_at": index,
                 "payload": {**kwargs.get("payload", {}), "device_id": kwargs.get("device_id")},
                 "entry_hash": "test-redacted-hash"}
                for index, (event, kwargs) in enumerate(reversed(self.events[-limit:]), start=1)]


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
    monkeypatch.setattr("integrations.discovery.execution._resolve_public_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr("integrations.discovery.execution.requests.Session", Session)

    tools = ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path))
    integrations = IntegrationRegistry()
    state = State(tmp_path / "integrations.sqlite3")
    integrations.state_store = state
    vault = SecretVault(tmp_path / "vault.json", password="test-only-password")
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
        "capability.discovered", "capability.approved", "capability.execution.started", "capability.execution.accepted",
    }
    history = client.get(f"/iphone/api/apps-tools/capabilities/{capability_id}/history")
    assert history.status_code == 200
    assert any(item["action"] == "capability.execution.accepted" for item in history.json()["entries"])
    assert "secret-test-token" not in history.text

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
    assert _validate_parameters(capability, {"region": "north", "units": "metric"}) == ("/forecast/north", {"units": "metric"}, None)
    for parameters in ({}, {"region": "north", "extra": "value"}, {"region": "north", "units": "other"}):
        try:
            _validate_parameters(capability, parameters)
        except ValueError:
            continue
        raise AssertionError("invalid OpenAPI parameters should be rejected")


def test_execution_parameter_validator_blocks_path_traversal():
    from integrations.discovery.execution import _validate_parameters

    capability = {"path": "/api/%2e%2e/admin", "parameters": []}
    try:
        _validate_parameters(capability, {})
    except ValueError:
        return
    raise AssertionError("encoded path traversal should be rejected")


def test_openapi_write_requires_exact_durable_owner_approval_and_is_one_shot(tmp_path, monkeypatch):
    calls = []

    class Session:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse({"id": "created-1"})

    monkeypatch.setattr(apps_tools_api, "_public_https_url", lambda url: url.rstrip("/"))
    monkeypatch.setattr("integrations.discovery.execution._public_https_url", lambda url: url.rstrip("/"))
    monkeypatch.setattr("integrations.discovery.execution._resolve_public_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr("integrations.discovery.execution.requests.Session", Session)
    tools = ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path))
    integrations = IntegrationRegistry()
    vault = SecretVault(tmp_path / "vault.json", password="test-only-password")
    state = ConnectorStateStore(tmp_path / "connectors.sqlite3", vault=vault)
    integrations.state_store = state
    runtime = {"device_registry": Devices(), "tools": tools, "integrations": integrations,
               "memory": MemoryStore(tmp_path / "memory.sqlite3"), "vault": vault}
    app = FastAPI()
    app.add_middleware(OwnerContextMiddleware)
    app.include_router(apps_tools_router(runtime))
    client = TestClient(app)
    spec = {"openapi": "3.1.0", "info": {"title": "Items", "version": "1"},
            "servers": [{"url": "https://items.example/api"}],
            "paths": {"/items": {"post": {"requestBody": {"required": True,
                "content": {"application/json": {"schema": {"type": "object", "required": ["name"],
                    "properties": {"name": {"type": "string", "maxLength": 40}}}}}}}}}}
    assert client.post("/iphone/api/apps-tools/capabilities/openapi", json={"document": spec}).status_code == 200
    capability = client.get("/iphone/api/apps-tools/capabilities?query=POST").json()["capabilities"][0]
    cap_id = capability["id"]
    assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/connect", json={"auth_type": "none"}).status_code == 200
    parameters = {"body": {"name": "Test"}}
    assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={"parameters": parameters}).status_code == 409
    ticket = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execution-approvals", json={"parameters": parameters})
    assert ticket.status_code == 200, ticket.text
    approval_id = ticket.json()["approval_id"]
    assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execution-approvals/{approval_id}/approve",
                       json={"parameters": {"body": {"name": "Different"}}}).status_code == 409
    assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execution-approvals/{approval_id}/approve",
                       json={"parameters": parameters}).status_code == 200
    done = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={
        "parameters": parameters, "approval_id": approval_id,
    })
    assert done.status_code == 200, done.text
    assert done.json()["verified"] is False
    assert len(calls) == 1 and calls[0][0] == "POST"
    replay = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={
        "parameters": parameters, "approval_id": approval_id,
    })
    assert replay.status_code == 409
    assert len(calls) == 1


def test_openapi_write_body_is_strictly_bounded():
    from integrations.discovery.execution import _validate_parameters

    cap = {"path": "/items", "parameters": [], "request_body": {
        "required": ["name"], "max_bytes": 80,
        "properties": {"name": {"type": "string", "max_length": 12},
                       "quantity": {"type": "integer", "enum": [1, 2]}},
    }}
    assert _validate_parameters(cap, {"body": {"name": "ok", "quantity": 2}})[2] == {"name": "ok", "quantity": 2}
    for value in ({"body": {"name": "too long name value"}}, {"body": {"name": "ok", "extra": 1}}, {"body": {"name": "ok", "quantity": 3}}, {}):
        try:
            _validate_parameters(cap, value)
        except ValueError:
            continue
        raise AssertionError("invalid OpenAPI JSON body should be rejected")


def test_capability_write_approval_expiry_and_restart_recovery_are_durable(tmp_path):
    path = tmp_path / "trusted-actions.sqlite3"
    manager = ApprovalManager(path=path, ttl_seconds=60)
    parameters = {"body": {"name": "approved"}}
    expired = manager.create("capability:items", "openapi_items_post", parameters,
                             destination="https://items.example/api")
    with pytest.raises(PermissionError, match="expired"):
        manager.approve(expired.id, expired.execution_id, expired.tool_name, parameters,
                        owner_id="owner", security_epoch=0, destination="https://items.example/api",
                        data_classification="internal", now=expired.expires_at + 1)
    assert manager.record(expired.id)["status"] == "expired"

    ticket = manager.create("capability:items", "openapi_items_post", parameters,
                            destination="https://items.example/api")
    manager.approve(ticket.id, ticket.execution_id, ticket.tool_name, parameters,
                    owner_id="owner", security_epoch=0, destination="https://items.example/api",
                    data_classification="internal")
    with ThreadPoolExecutor(max_workers=2) as pool:
        dispatches = list(pool.map(lambda worker: manager.begin_dispatch(ticket.id, worker_id=worker),
                                   ("worker-a", "worker-b")))
    assert sum(bool(result["dispatch"]) for result in dispatches) == 1
    assert sorted(result["status"] for result in dispatches) == ["dispatching", "dispatching"]

    # A process loss after dispatch cannot make the one-use approval reusable.
    assert manager.mark_recovery_required(ticket.id, "simulated_process_loss")
    restarted = ApprovalManager(path=path)
    record = restarted.record(ticket.id)
    assert record["status"] == "recovery_required"
    assert restarted.begin_dispatch(ticket.id, worker_id="after-restart")["dispatch"] is False
