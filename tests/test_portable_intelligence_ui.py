from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.portable_intelligence_ui import JS, PortableIntelligenceUiMiddleware, portable_intelligence_ui_router


def test_portable_intelligence_ui_exposes_real_owner_actions_and_responsive_layout():
    assert "ocPortableIntelligence" in JS
    assert "/owner/portable-intelligence/summary" in JS
    assert "/owner/portable-intelligence/publish" in JS
    assert "/owner/portable-intelligence/offline-pack" in JS
    assert "/owner/portable-intelligence/activation/preflight" in JS
    assert "/owner/portable-intelligence/activation" in JS
    assert "/owner/portable-intelligence/contributions" in JS
    assert "/owner/portable-intelligence/specialists" in JS
    assert "/owner/intelligence/training/models" in JS
    assert "@media(max-width:720px)" in JS
    assert "Private" in JS
    assert "credentials are never exposed" in JS
    assert "Backup/restore mutation stays owned" in JS


def test_portable_intelligence_script_route_is_no_cache():
    app = FastAPI()
    app.include_router(portable_intelligence_ui_router())
    client = TestClient(app)

    response = client.get("/iphone/portable-intelligence-ui.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "javascript" in response.headers["content-type"]
    assert "ocPortableIntelligence" in response.text


def test_middleware_injects_script_once_into_iphone_page():
    app = FastAPI()
    app.add_middleware(PortableIntelligenceUiMiddleware)

    @app.get("/iphone")
    def iphone():
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<html><body><main>Data & Backups</main></body></html>")

    client = TestClient(app)
    response = client.get("/iphone")
    assert response.status_code == 200
    assert response.text.count('/iphone/portable-intelligence-ui.js') == 1
