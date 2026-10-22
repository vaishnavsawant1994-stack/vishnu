"""P2-06 canonical federated Search API integration/authorization tests."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from devices.continuity import ContinuityService
from projects.store import ProjectStore
from workspaces.store import WorkspaceStore
from knowledge.store import KnowledgeStore
from server.global_search_api import global_search_router


class Registry:
    def __init__(self):
        self.revoked = False
        self.scopes = {"ai:chat", "knowledge:read", "memory:read"}

    def authenticate(self, device, token):
        return not self.revoked and device == "device-one" and token == "token-one"

    def authorize(self, device, scope):
        return scope in self.scopes


class Memory:
    def preferences(self):
        return {"memory_enabled": True}

    def search(self, q, limit=20, active_only=True):
        return [
            {"id": "normal", "subject": "API memory", "content": "text", "sensitivity": "normal"},
            {"id": "secret", "subject": "API secret", "content": "credential", "sensitivity": "secret"},
        ]

    def get(self, memory_id):
        return next((x for x in self.search("") if x["id"] == memory_id), None)


class Agents:
    def catalog(self):
        return [{"id": "agent-1", "name": "API Research Agent", "description": "Trusted research template"}]


def setup(tmp_path):
    registry = Registry()
    projects = ProjectStore(tmp_path / "projects.sqlite3")
    workspace_store = WorkspaceStore(tmp_path / "workspaces.sqlite3")
    continuity = ContinuityService(tmp_path / "continuity.sqlite3")
    knowledge = KnowledgeStore(tmp_path / "knowledge.sqlite3", tmp_path / "objects")
    project = projects.create(name="API Development", goal="Integrate external services")
    projects.add_task(project["id"], title="API integration checklist", description="Test canonical API calls")
    projects.add_upload(project["id"], title="API blueprint.txt", media_type="text/plain",
                        content=b"API integration document with retry policy")
    workspace = workspace_store.create("owner", name="API Workspace", description="Related development")
    workspace_store.link_project("owner", workspace["id"], project["id"])
    continuity.create_thread("API integration plan", context={"conversation_kind": "project", "project_id": project["id"]})
    knowledge.create_note(title="API note", content="API integration notes")
    knowledge.ingest(filename="integration.txt", data=b"API integration testing manual",
                     title="API Integration Manual")
    runtime = {
        "device_registry": registry,
        "continuity": continuity,
        "base_project_store": projects,
        "workspace_store": workspace_store,
        "knowledge": knowledge,
        "memory": Memory(),
        "agent_workforce": Agents(),
    }
    app = FastAPI()
    app.include_router(global_search_router(runtime))
    client = TestClient(app)
    client.cookies.set("pa_device", "device-one")
    client.cookies.set("pa_token", "token-one")
    return client, registry, project, workspace, runtime


def test_real_sources_and_facets(tmp_path):
    client, _, project, workspace, _ = setup(tmp_path)
    r = client.get("/iphone/api/search", params={"q": "API"})
    assert r.status_code == 200, r.text
    data = r.json()
    available = set(x["type"] for x in data["results"])
    assert {"conversations", "projects", "work", "files", "agents", "knowledge", "memory"}.issubset(available)
    assert data["coverage"]["files"] == "available"
    assert data["counts"]["all"] >= 7
    assert all(x.get("id") and x.get("title") and x.get("source") for x in data["results"])
    assert "credential" not in r.text and "API secret" not in r.text
    narrowed = client.get("/iphone/api/search", params={
        "q": "API", "workspace_id": workspace["id"], "project_id": project["id"],
    })
    assert narrowed.status_code == 200, narrowed.text
    filtered = narrowed.json()["results"]
    assert filtered and all(x["type"] in ("conversations", "projects", "files", "work") for x in filtered)
    assert client.get("/iphone/api/search", params={
        "q": "API", "workspace_id": "forged",
    }).status_code == 404


def test_filters_ranking_pagination_and_detail(tmp_path):
    client, _, project, _, _ = setup(tmp_path)
    first = client.get("/iphone/api/search", params={
        "q": "API", "category": "work", "limit": 1,
    }).json()
    assert first["results"] and first["results"][0]["type"] == "work"
    assert first["results"][0]["project_id"] == project["id"]
    doc = client.get("/iphone/api/search", params={
        "q": "API", "category": "projects", "sort": "title",
    }).json()["results"][0]
    detail = client.get(f"/iphone/api/search/result/projects/{doc['id']}")
    assert detail.status_code == 200
    assert detail.json()["related"][0]["type"] == "work"
    task = first["results"][0]
    work = client.get(f"/iphone/api/search/result/work/{task['id']}",
                      params={"project_id": project["id"]})
    assert work.status_code == 200
    assert work.json()["result"]["title"] == task["title"]
    assert client.get("/iphone/api/search", params={
        "q": "API", "date_from": "2026-10-30", "date_to": "2026-10-01",
    }).status_code == 422
    assert client.get("/iphone/api/search", params={"q": ""}).status_code == 422


def test_auth_scope_denial_and_source_status(tmp_path):
    client, registry, _, _, _ = setup(tmp_path)
    client.cookies.clear()
    assert client.get("/iphone/api/search?q=API").status_code == 401
    client.cookies.update({"pa_device": "device-one", "pa_token": "token-one"})
    registry.scopes.remove("ai:chat")
    assert client.get("/iphone/api/search?q=API").status_code == 403
    registry.scopes.add("ai:chat")
    registry.scopes.remove("knowledge:read")
    registry.scopes.remove("memory:read")
    data = client.get("/iphone/api/search?q=API").json()
    assert data["coverage"]["knowledge"] == "restricted"
    assert data["coverage"]["files"] == "restricted"
    assert data["coverage"]["memory"] == "restricted"
    assert not any(x["type"] in {"knowledge", "files", "memory"} for x in data["results"])
    registry.revoked = True
    assert client.get("/iphone/api/search?q=API").status_code == 401


def test_failures_do_not_fabricate_zero_for_unavailable_sources(tmp_path):
    client, _, _, _, runtime = setup(tmp_path)
    class UnavailableAgents:
        def catalog(self):
            raise RuntimeError("agent unavailable")
    runtime["agent_workforce"] = UnavailableAgents()
    data = client.get("/iphone/api/search?q=API").json()
    assert data["coverage"]["agents"] == "unavailable"
    assert data["counts"]["projects"] >= 1
    assert client.get("/iphone/api/search/result/agents/missing").status_code == 503
