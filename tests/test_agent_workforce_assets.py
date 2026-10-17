from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.agent_workforce_assets import agent_workforce_assets_router


def test_workforce_assets_are_explicitly_served_and_shell_gets_single_entry_script(tmp_path):
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("<html><body><main>Vishnu</main></body></html>", encoding="utf-8")
    (pwa / "agents.html").write_text("<html><body>Agents</body></html>", encoding="utf-8")
    (pwa / "capabilities.html").write_text("<html><body>Capability guide</body></html>", encoding="utf-8")
    (pwa / "agents-workforce.css").write_text(".aw-app{display:grid}", encoding="utf-8")
    (pwa / "agents-workforce.js").write_text("window.AGENTS=true", encoding="utf-8")
    (pwa / "agents-workforce-work-mode.js").write_text("window.WORK_MODE=true", encoding="utf-8")
    (pwa / "agent-workforce-entry.js").write_text("window.ENTRY=true", encoding="utf-8")

    app = FastAPI()
    app.include_router(agent_workforce_assets_router(SimpleNamespace(base_dir=tmp_path)))
    client = TestClient(app)

    root = client.get("/iphone/")
    assert root.status_code == 200
    assert root.headers["cache-control"] == "no-store"
    assert root.text.count('/iphone/agent-workforce-entry.js') == 1

    agents = client.get("/iphone/agents.html")
    assert agents.status_code == 200
    assert agents.headers["cache-control"] == "no-store"
    assert "Agents" in agents.text

    capabilities = client.get("/iphone/capabilities.html")
    assert capabilities.status_code == 200
    assert capabilities.headers["cache-control"] == "no-store"
    assert "Capability guide" in capabilities.text

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
        "capabilities.html": "Capability guide",
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
    assert client.get("/iphone/not-a-real-page.html").status_code == 404
