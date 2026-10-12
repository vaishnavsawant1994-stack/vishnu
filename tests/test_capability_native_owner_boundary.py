"""Fail-closed API contract for native clients before owner-session integration.

Native companions must not reuse device-pairing bearer credentials as an
owner-session substitute. These checks intentionally provide no trusted request
context, even if a caller supplies plausible HTTP authorization headers.
"""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations.registry import IntegrationRegistry
from server.apps_tools_api import apps_tools_router
from tools.registry import ToolRegistry


class Devices:
    def is_active(self, device_id):
        return True

    def authorize(self, device_id, scope):
        return True


def test_capability_routes_reject_untrusted_native_bearer_headers(tmp_path):
    integrations = IntegrationRegistry()
    runtime = {
        "device_registry": Devices(),
        "tools": ToolRegistry(SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path)),
        "integrations": integrations,
        "memory": None,
    }
    app = FastAPI()
    app.include_router(apps_tools_router(runtime))
    client = TestClient(app)
    headers = {"Authorization": "Bearer device-pairing-token", "X-Device-ID": "owner-device"}
    checks = [
        ("GET", "/iphone/api/apps-tools/capabilities", None),
        ("GET", "/iphone/api/apps-tools/capabilities/unknown", None),
        ("GET", "/iphone/api/apps-tools/mcp/servers", None),
        ("POST", "/iphone/api/apps-tools/capabilities/openapi", {"document": {}}),
        ("POST", "/iphone/api/apps-tools/mcp/servers", {"name": "test", "url": "https://example.org/mcp"}),
    ]
    for method, path, payload in checks:
        response = client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 401, (method, path, response.status_code, response.text)
