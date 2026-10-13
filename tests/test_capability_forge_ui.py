from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from server.capability_forge_ui import CapabilityForgeUiMiddleware, JS, capability_forge_ui_router


def test_forge_ui_script_uses_only_governed_owner_endpoints_and_keeps_approval_separate():
    assert "/owner/forge/summary" in JS
    assert "/proposals" in JS
    assert "/activation/request" in JS
    assert "/activation/commit" in JS
    assert "/disable/request" in JS
    assert "/rollback/request" in JS
    assert "Approvals Center" in JS
    assert "self-approve" not in JS.lower()
    assert "queue_draft_work" in JS
    assert "production_activation" in JS


def test_forge_ui_middleware_injects_console_into_iphone_and_capability_console_only():
    app = FastAPI()
    app.add_middleware(CapabilityForgeUiMiddleware)
    app.include_router(capability_forge_ui_router())

    @app.get("/iphone")
    def iphone():
        return HTMLResponse("<html><body>Vishnu</body></html>")

    @app.get("/capabilities")
    def capabilities():
        return HTMLResponse("<html><body>Capabilities</body></html>")

    @app.get("/other")
    def other():
        return HTMLResponse("<html><body>Other</body></html>")

    client = TestClient(app)
    iphone = client.get("/iphone")
    assert iphone.status_code == 200
    assert '<script src="/iphone/capability-forge-ui.js"></script>' in iphone.text

    capabilities = client.get("/capabilities")
    assert '<script src="/iphone/capability-forge-ui.js"></script>' in capabilities.text

    other = client.get("/other")
    assert "capability-forge-ui.js" not in other.text

    script = client.get("/iphone/capability-forge-ui.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")

    page = client.get("/capabilities/forge")
    assert page.status_code == 200
    assert "Capability Forge" in page.text
