from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.agent_workforce_assets import agent_workforce_assets_router
from server.iphone_pwa import iphone_pwa_router
from server.web_path_compat import CanonicalWebPathMiddleware


def test_workforce_assets_are_explicitly_served_without_owning_home(tmp_path):
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("<html><body><main>Vishnu</main></body></html>", encoding="utf-8")
    (pwa / "agents.html").write_text("<html><body>Agents</body></html>", encoding="utf-8")
    (pwa / "agents-workforce.css").write_text(".aw-app{display:grid}", encoding="utf-8")
    (pwa / "agents-workforce.js").write_text("window.AGENTS=true", encoding="utf-8")
    (pwa / "agents-workforce-work-mode.js").write_text("window.WORK_MODE=true", encoding="utf-8")
    (pwa / "agent-workforce-entry.js").write_text("window.ENTRY=true", encoding="utf-8")

    app = FastAPI()
    app.include_router(agent_workforce_assets_router(SimpleNamespace(base_dir=tmp_path)))
    client = TestClient(app)

    assert client.get("/iphone/").status_code == 404

    agents = client.get("/iphone/agents.html")
    assert agents.status_code == 200
    assert agents.headers["cache-control"] == "no-store"
    assert "Agents" in agents.text

    css = client.get("/iphone/agents-workforce.css")
    js = client.get("/iphone/agents-workforce.js")
    work_mode = client.get("/iphone/agents-workforce-work-mode.js")
    entry = client.get("/iphone/agent-workforce-entry.js")
    assert css.headers["content-type"].startswith("text/css")
    assert js.headers["content-type"].startswith("application/javascript")
    assert work_mode.headers["content-type"].startswith("application/javascript")
    assert entry.headers["content-type"].startswith("application/javascript")


def test_asset_router_does_not_expose_generic_pwa_files(tmp_path):
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    for name, content in {
        "index.html": "<body></body>",
        "agents.html": "Agents",
        "agents-workforce.css": "x{}",
        "agents-workforce.js": "x=1",
        "agents-workforce-work-mode.js": "z=1",
        "agent-workforce-entry.js": "y=1",
        "private.txt": "must not be served",
    }.items():
        (pwa / name).write_text(content, encoding="utf-8")
    app = FastAPI()
    app.include_router(agent_workforce_assets_router(SimpleNamespace(base_dir=tmp_path)))
    client = TestClient(app)
    assert client.get("/iphone/private.txt").status_code == 404


def test_assembled_cloud_router_order_uses_one_home_shell_with_p2_and_workforce_assets(tmp_path):
    """Exercise the same router order as cloud_app, including /web rewriting."""
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parents[1],
        iphone_pwa_allow_insecure=True,
        iphone_owner_enrollment_code="test-owner-code",
        owner_bootstrap_secret="",
        google_signin_client_id="",
    )
    runtime = {
        "device_registry": object(),
        "executor": object(),
        "owner_access": object(),
    }
    app = FastAPI()
    # This ordering mirrors server/cloud_app.py. The workforce router should
    # provide its assets but never claim either Home path.
    workforce_router = agent_workforce_assets_router(settings)
    pwa_router = iphone_pwa_router(runtime, settings, include_legacy_runtime_routes=False)
    app.include_router(workforce_router)
    app.include_router(pwa_router)
    app.add_middleware(CanonicalWebPathMiddleware)
    client = TestClient(app)

    for route in ("/iphone/", "/web/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        page = response.text
        external_scripts = re.findall(r'<script\b([^>]*\bsrc\s*=\s*["\'][^"\']+["\'][^>]*)>', page, re.IGNORECASE)
        assert all(re.search(r'\b(?:async|defer)\b', attrs, re.IGNORECASE) for attrs in external_scripts), (
            f"{route} must not load the shared script bundle as a parser-blocking waterfall"
        )
        for asset in (
            "p2-home.css", "p2-home.js", "agent-workforce-entry.js",
            "our-products-entry.js", "vishnu-os-workspaces.css",
            "vishnu-os-workspaces.js", "neural-sphere.js", "first-run.js",
        ):
            assert page.count(asset) == 1, f"{route} must inject {asset} exactly once"

    # Each screen controller referenced by index.html must remain reachable
    # through both the compatibility and canonical browser paths.
    for asset in (
        "p202-personal-chat.js", "p202b-work-conversation.js",
        "p202c-project-conversation.js", "p202d-workspace-conversation.js",
        "p203-today.js", "p204-live-voice.js",
        "p205-conversation-history.js", "global-search.js",
        "p207-notifications.js", "command-center.js",
    ):
        for prefix in ("/iphone", "/web"):
            response = client.get(f"{prefix}/{asset}")
            assert response.status_code == 200, f"{prefix}/{asset}"
            assert response.content, f"{prefix}/{asset} must not be empty"
    assert not any(
        route.path in ("", "/") and "GET" in getattr(route, "methods", set())
        for route in workforce_router.routes
    ), "the asset router must not register a competing Home handler"
    assert sum(
        route.path in ("/iphone", "/iphone/") and "GET" in getattr(route, "methods", set())
        for route in pwa_router.routes
    ) == 2, "the canonical PWA router owns the two legacy Home path variants"
