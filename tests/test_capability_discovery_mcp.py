from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.mcp import normalize_mcp_server, normalize_mcp_tool
from integrations.registry import IntegrationRegistry
from memory.store import MemoryStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from security.vault import SecretVault
from server import apps_tools_api
from server.apps_tools_api import apps_tools_router
from tools.registry import ToolRegistry


def test_mcp_descriptors_are_inert_and_server_scoped():
    first = normalize_mcp_server({"name": "Weather", "url": "https://mcp.example/weather"})
    second = normalize_mcp_server({"name": "Calendar", "url": "https://mcp.example/calendar"})
    assert first["id"] != second["id"]
    tool_a = normalize_mcp_tool(first["id"], {"name": "list", "inputSchema": {"type": "object"}})
    tool_b = normalize_mcp_tool(second["id"], {"name": "list", "inputSchema": {"type": "object"}})
    assert tool_a["id"] != tool_b["id"]
    assert tool_a["executable"] is False
    assert tool_a["risk"] == "write"
    assert normalize_mcp_tool(first["id"], {"name": "safe", "annotations": {"readOnlyHint": True}})["risk"] == "read"
    assert normalize_mcp_tool(first["id"], {"name": "delete", "annotations": {"destructiveHint": True}})["risk"] == "destructive"
    with pytest.raises(ValueError):
        normalize_mcp_server({"name": "Bad", "url": "https://mcp.example", "command": "sh"})
    with pytest.raises(ValueError):
        normalize_mcp_tool(first["id"], {"name": "unsafe", "inputSchema": {"$ref": "#/secret"}})


def test_mcp_catalog_rejects_duplicate_tool_names(tmp_path):
    catalog = CapabilityCatalogStore(tmp_path / "catalog.sqlite3")
    with pytest.raises(ValueError, match="duplicate"):
        catalog.import_mcp_tools("mcp_server:abc", [{"name": "same"}, {"name": "same"}])


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


def test_owner_discovers_attests_executes_and_disconnects_mcp(tmp_path, monkeypatch):
    server_tools = [{
        "name": "lookup_weather", "description": "Read a current forecast",
        "inputSchema": {"type": "object", "properties": {"city": {"type": "string", "maxLength": 80}},
                        "required": ["city"], "additionalProperties": False},
    }]

    class FakeMCPClient:
        def __init__(self, endpoint, token=None):
            assert endpoint == "https://mcp.example/weather"
            self.token = token

        def list_tools(self):
            return server_tools

        def call_tool(self, name, arguments):
            assert name == "lookup_weather"
            assert arguments == {"city": "Oslo"}
            assert self.token == "mcp-secret-token"
            return {"content": [{"type": "text", "text": "sunny"}], "isError": False}

    monkeypatch.setattr(apps_tools_api, "_public_https_url", lambda url: url.rstrip("/"))
    monkeypatch.setattr(apps_tools_api, "MCPHTTPClient", FakeMCPClient)
    monkeypatch.setattr("integrations.discovery.mcp_runtime.MCPHTTPClient", FakeMCPClient)

    tools = ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path))
    integrations = IntegrationRegistry()
    state = State(tmp_path / "integrations.sqlite3")
    integrations.state_store = state
    vault = SecretVault(tmp_path / "vault.json", password="test-only-password")
    runtime = {"device_registry": Devices(), "tools": tools, "integrations": integrations,
               "memory": MemoryStore(tmp_path / "memory.sqlite3"), "vault": vault}
    app = FastAPI()
    app.add_middleware(OwnerContextMiddleware)
    app.include_router(apps_tools_router(runtime))
    client = TestClient(app)

    added = client.post("/iphone/api/apps-tools/mcp/servers", json={
        "name": "Weather MCP", "url": "https://mcp.example/weather",
    })
    assert added.status_code == 200, added.text
    server = added.json()["server"]
    server_id = server["id"]
    discovered = client.post(f"/iphone/api/apps-tools/mcp/servers/{server_id}/discover", json={
        "auth_type": "bearer_token", "api_key": "mcp-secret-token",
    })
    assert discovered.status_code == 200, discovered.text
    assert "mcp-secret-token" not in discovered.text
    capability = discovered.json()["tools"][0]
    assert capability["executable"] is False
    capability_id = capability["id"]

    denied = client.post(f"/iphone/api/apps-tools/mcp/capabilities/{capability_id}/approve", json={})
    assert denied.status_code == 422
    approved = client.post(f"/iphone/api/apps-tools/mcp/capabilities/{capability_id}/approve",
                           json={"read_only_attested": True})
    assert approved.status_code == 200, approved.text
    assert "mcp-secret-token" not in approved.text
    assert approved.json()["approved"] is True

    executed = client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/execute",
                           json={"parameters": {"city": "Oslo"}})
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"]["content"][0]["text"] == "sunny"
    assert executed.json()["verified"] is True
    assert {event for event, _ in state.events} >= {
        "mcp.server.discovered", "mcp.server.connected", "mcp.capability.approved",
        "mcp.execution.started", "mcp.execution.succeeded",
    }
    assert "mcp-secret-token" not in json.dumps(state.events)

    disconnected = client.post(f"/iphone/api/apps-tools/mcp/servers/{server_id}/disconnect")
    assert disconnected.status_code == 200
    assert not vault.names()
    denied_after_revoke = client.post(f"/iphone/api/apps-tools/capabilities/{capability_id}/execute",
                                      json={"parameters": {"city": "Oslo"}})
    assert denied_after_revoke.status_code == 409
    assert any(event == "mcp.server.revoked" for event, _ in state.events)


class MCPResponse:
    def __init__(self, status, payload=None, *, headers=None, content=None):
        self.status_code = status
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.content = content if content is not None else (json.dumps(payload).encode() if payload is not None else b"")

    def json(self):
        return json.loads(self.content)


def test_mcp_streamable_http_initialize_session_and_call(monkeypatch):
    requests = []

    class Session:
        def __init__(self, endpoint):
            self.endpoint = endpoint

        def request(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            body = kwargs["json"]
            if body["method"] == "initialize":
                return MCPResponse(200, {"jsonrpc": "2.0", "id": body["id"], "result": {
                    "protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }}, headers={"MCP-Session-Id": "session-123"})
            if body["method"] == "notifications/initialized":
                return MCPResponse(202)
            assert body["method"] == "tools/call"
            return MCPResponse(200, {"jsonrpc": "2.0", "id": body["id"], "result": {"content": []}})

    monkeypatch.setattr("integrations.discovery.mcp_runtime._BoundedHTTPSession", Session)
    from integrations.discovery.mcp_runtime import MCPHTTPClient

    result = MCPHTTPClient("https://mcp.example/tools", "fixture-token").call_tool("read", {"key": "value"})
    assert result == {"content": []}
    assert [item[2]["json"].get("method") for item in requests] == [
        "initialize", "notifications/initialized", "tools/call",
    ]
    assert requests[1][2]["headers"]["MCP-Session-Id"] == "session-123"
    assert requests[2][2]["headers"]["MCP-Protocol-Version"] == "2025-11-25"
    assert requests[2][2]["headers"]["Authorization"] == "Bearer fixture-token"


def test_live_https_bridges_approve_execute_audit_and_revoke(tmp_path, monkeypatch):
    """Run both actual bridges over TLS sockets against the isolated local fixture."""
    if not shutil.which("openssl"):
        pytest.skip("openssl is required for isolated HTTPS bridge qualification")
    cert, key = tmp_path / "fixture-cert.pem", tmp_path / "fixture-key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
        "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost",
    ], check=True, capture_output=True, timeout=20)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([
        sys.executable, "scripts/capability_live_fixture.py", "--cert", str(cert),
        "--key", str(key), "--port", str(port),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base_url = f"https://localhost:{port}"
    tls_context = ssl.create_default_context(cafile=str(cert))
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(cert))
    monkeypatch.setenv("NO_PROXY", f"localhost,127.0.0.1,{os.environ.get('NO_PROXY', '')}")

    def allow_local_test_origin(value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "localhost" or parsed.port != port:
            raise ValueError("test bridge may access only its local TLS fixture")
        return value.rstrip("/")

    monkeypatch.setattr(apps_tools_api, "_public_https_url", allow_local_test_origin)
    monkeypatch.setattr("integrations.discovery.execution._public_https_url", allow_local_test_origin)
    try:
        for _ in range(50):
            try:
                with urlopen(base_url + "/openapi.json", context=tls_context, timeout=2) as response:
                    spec = json.load(response)
                break
            except (OSError, URLError):
                time.sleep(0.1)
        else:
            pytest.fail("isolated HTTPS fixture did not start")

        tools = ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path))
        integrations = IntegrationRegistry()
        state = State(tmp_path / "integrations.sqlite3")
        integrations.state_store = state
        vault = SecretVault(tmp_path / "vault.json", password="fixture-only-password")
        runtime = {"device_registry": Devices(), "tools": tools, "integrations": integrations,
                   "memory": MemoryStore(tmp_path / "memory.sqlite3"), "vault": vault}
        app = FastAPI()
        app.add_middleware(OwnerContextMiddleware)
        app.include_router(apps_tools_router(runtime))
        client = TestClient(app)

        # The OpenAPI path crosses real TLS, then the bridge performs actual HTTPS
        # execution with credential rejection, secret redaction and owner revocation.
        imported = client.post("/iphone/api/apps-tools/capabilities/openapi", json={"document": spec})
        assert imported.status_code == 200, imported.text
        capabilities = client.get("/iphone/api/apps-tools/capabilities?query=forecast").json()["capabilities"]
        forecast = next(item for item in capabilities if item["path"] == "/forecast")
        cap_id = forecast["id"]

        connected = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/connect", json={
            "server_url": base_url, "auth_type": "bearer_token", "api_key": "wrong-fixture-token",
        })
        assert connected.status_code == 200, connected.text
        rejected = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={
            "parameters": {"city": "Oslo"},
        })
        assert rejected.status_code == 401, rejected.text
        assert "wrong-fixture-token" not in rejected.text
        client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/disconnect")

        connected = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/connect", json={
            "server_url": base_url, "auth_type": "bearer_token", "api_key": "qualification-only-token",
        })
        assert connected.status_code == 200, connected.text
        assert "qualification-only-token" not in connected.text
        executed = client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={
            "parameters": {"city": "Oslo"},
        })
        assert executed.status_code == 200, executed.text
        assert executed.json()["result"]["forecast"] == "sunny"
        assert any(event == "capability.execution.succeeded" for event, _ in state.events)
        assert "qualification-only-token" not in json.dumps(state.events)
        assert "qualification-only-token" not in (tmp_path / "vault.json").read_text()
        assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/disconnect").status_code == 200
        assert client.post(f"/iphone/api/apps-tools/capabilities/{cap_id}/execute", json={
            "parameters": {"city": "Oslo"},
        }).status_code == 409

        # Exercise the failure endpoints through the same registered, governed
        # OpenAPI bridge. Each capability is disconnected after its assertion.
        for path, expected_status in (("/redirect", 502), ("/oversized", 413), ("/timeout", 504)):
            item = next(value for value in client.get("/iphone/api/apps-tools/capabilities?limit=100").json()["capabilities"]
                        if value["path"] == path)
            connect = client.post(f"/iphone/api/apps-tools/capabilities/{item['id']}/connect", json={
                "server_url": base_url, "auth_type": "none",
            })
            assert connect.status_code == 200, connect.text
            response = client.post(f"/iphone/api/apps-tools/capabilities/{item['id']}/execute", json={"parameters": {}})
            assert response.status_code == expected_status, (path, response.status_code, response.text)
            client.post(f"/iphone/api/apps-tools/capabilities/{item['id']}/disconnect")

        # MCP discovery, approval, argument validation, actual HTTPS call, audit,
        # secret redaction, and server revocation use the production route handlers.
        added = client.post("/iphone/api/apps-tools/mcp/servers", json={"name": "Fixture MCP", "url": base_url + "/mcp"})
        assert added.status_code == 200, added.text
        server_id = added.json()["server"]["id"]
        bad_auth = client.post(f"/iphone/api/apps-tools/mcp/servers/{server_id}/discover", json={
            "auth_type": "bearer_token", "api_key": "bad-mcp-fixture-token",
        })
        assert bad_auth.status_code == 502, bad_auth.text
        assert "bad-mcp-fixture-token" not in bad_auth.text
        discovered = client.post(f"/iphone/api/apps-tools/mcp/servers/{server_id}/discover", json={
            "auth_type": "bearer_token", "api_key": "qualification-only-token",
        })
        assert discovered.status_code == 200, discovered.text
        tool = discovered.json()["tools"][0]
        tool_id = tool["id"]
        approved = client.post(f"/iphone/api/apps-tools/mcp/capabilities/{tool_id}/approve", json={
            "read_only_attested": True,
        })
        assert approved.status_code == 200, approved.text
        assert "qualification-only-token" not in approved.text
        invalid = client.post(f"/iphone/api/apps-tools/capabilities/{tool_id}/execute", json={
            "parameters": {"city": "x" * 81},
        })
        assert invalid.status_code == 422, invalid.text
        mcp_result = client.post(f"/iphone/api/apps-tools/capabilities/{tool_id}/execute", json={
            "parameters": {"city": "Oslo"},
        })
        assert mcp_result.status_code == 200, mcp_result.text
        assert json.loads(mcp_result.json()["result"]["content"][0]["text"]) == {"city": "Oslo", "forecast": "sunny"}
        assert any(event == "mcp.execution.succeeded" for event, _ in state.events)
        assert "qualification-only-token" not in json.dumps(state.events)
        assert client.post(f"/iphone/api/apps-tools/mcp/servers/{server_id}/disconnect").status_code == 200
        assert client.post(f"/iphone/api/apps-tools/capabilities/{tool_id}/execute", json={
            "parameters": {"city": "Oslo"},
        }).status_code == 409
        assert "qualification-only-token" not in (tmp_path / "vault.json").read_text()
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
