"""P2-06 authenticated federated search over canonical Vishnu stores.

No parallel search database. Each adapter exposes bounded, permission-checked
metadata and honest coverage. Never copy credentials or sensitive memory into
a search index.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException, Query

KINDS = ("conversations", "workspaces", "projects", "files", "work", "agents", "knowledge", "memory")
SOURCE_LIMIT = 100


def global_search_router(runtime: dict) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/search", tags=["global-search"])
    registry = runtime["device_registry"]

    def session(device: str | None, token: str | None):
        if not device or not token or not registry.authenticate(device, token):
            raise HTTPException(401, "Trusted owner session required")
        if hasattr(registry, "authorize") and not registry.authorize(device, "ai:chat"):
            raise HTTPException(403, "Device cannot search owner resources")
        return device

    def permitted(device: str, scope: str):
        return not hasattr(registry, "authorize") or registry.authorize(device, scope)

    def memory_enabled(store):
        """Respect the owner toggle on both listing and direct previews; fail closed."""
        if store is None:
            return False
        try:
            return bool(store.preferences().get("memory_enabled", True))
        except (OSError, RuntimeError, ValueError, AttributeError, TypeError):
            return False

    def stores():
        return {
            "conversations": runtime.get("continuity"),
            "projects": runtime.get("base_project_store") or runtime.get("project_store"),
            "workspaces": runtime.get("workspace_store"),
            "files": runtime.get("knowledge"),
            "knowledge": runtime.get("knowledge"),
            "memory": runtime.get("memory"),
            "work": runtime.get("base_project_store") or runtime.get("project_store"),
            "agents": runtime.get("agent_workforce"),
        }

    def authorise_target(project_id: str, workspace_id: str):
        s = stores()
        project = None
        workspace = None
        if project_id:
            project = s["projects"].get(project_id) if s["projects"] else None
            if not project:
                raise HTTPException(404, "Project not found")
        if workspace_id:
            workspace = s["workspaces"].get("owner", workspace_id) if s["workspaces"] else None
            if not workspace or workspace.get("status") == "archived":
                raise HTTPException(404, "Workspace not found")
            if project_id:
                linked = {item["resource_id"] for item in s["workspaces"].linked_projects("owner", workspace_id)}
                if project_id not in linked:
                    raise HTTPException(404, "Project is not linked to this Workspace")
        return project, workspace

    def allowed_projects(workspace_id: str, project_id: str = ""):
        s = stores()
        if not s["projects"]:
            return [], False
        if project_id:
            project = s["projects"].get(project_id)
            if not project:
                return [], False
            if workspace_id:
                linked = {x["resource_id"] for x in s["workspaces"].linked_projects("owner", workspace_id)}
                if project_id not in linked:
                    return [], False
            return [project], False
        rows = list(s["projects"].list(query="", status="all", sort="recent"))
        if workspace_id:
            links = {x["resource_id"] for x in s["workspaces"].linked_projects("owner", workspace_id)}
            rows = [x for x in rows if x["id"] in links]
        return rows[:SOURCE_LIMIT], len(rows) > SOURCE_LIMIT

    def knowledge_classes(device: str) -> set[str]:
        classes = {"owner", "trusted-devices"}
        if permitted(device, "knowledge:private"):
            classes.add("private")
        return classes

    def row(kind, ident, title, excerpt="", *, updated="", project_id="", workspace_id="",
            status="", tags=None, source="", **extra):
        return {
            "type": kind, "id": str(ident), "title": str(title or "Untitled")[:180],
            "excerpt": str(excerpt or "")[:420], "updated_at": str(updated or ""),
            "project_id": str(project_id or ""), "workspace_id": str(workspace_id or ""),
            "status": str(status or ""), "tags": list(tags or [])[:12],
            "source": str(source or kind), **extra,
        }

    def search_source(kind: str, q: str, device: str, *, project_id="", workspace_id=""):
        s = stores()
        store = s[kind]
        if store is None:
            return None, "unavailable"
        if kind in {"files", "knowledge"} and not permitted(device, "knowledge:read"):
            return [], "restricted"
        if kind == "memory" and not permitted(device, "memory:read"):
            return [], "restricted"
        result = []
        needle = q.casefold()

        if kind == "conversations":
            page = store.history_page(
                query=q, status="active", limit=SOURCE_LIMIT,
                project_id=project_id, workspace_id=workspace_id)
            for it in page["conversations"]:
                ctx = it.get("context") or {}
                result.append(row(kind, it["id"], it["title"], it.get("preview", ""),
                                  updated=it.get("updated_at", ""),
                                  project_id=ctx.get("project_id") or ctx.get("work_project_id"),
                                  workspace_id=ctx.get("workspace_id"),
                                  tags=ctx.get("history_tags") or [], source="continuity",
                                  context_kind=ctx.get("conversation_kind") or "personal"))
            return result, "partial" if page.get("has_more") else "available"

        if kind == "workspaces":
            source_rows = store.list("owner", query=q, status="active", sort="recent")
            for it in source_rows[:SOURCE_LIMIT]:
                result.append(row(kind, it["id"], it["name"], it.get("description"),
                                  updated=it.get("updated_at"), status=it.get("status"),
                                  workspace_id=it["id"], source="canonical_workspace"))
            return result, "partial" if len(source_rows) > SOURCE_LIMIT else "available"

        if kind == "projects":
            projects, project_truncated = allowed_projects(workspace_id, project_id)
            for it in projects:
                if project_id and it["id"] != project_id:
                    continue
                if needle not in " ".join(str(it.get(k) or "") for k in ("name", "goal", "description")).casefold():
                    continue
                result.append(row(kind, it["id"], it["name"], it.get("goal") or it.get("description"),
                                  updated=it.get("updated_at"), status=it.get("status"),
                                  project_id=it["id"], source="canonical_project"))
            return result, "partial" if project_truncated else "available"

        if kind == "work":
            projects, project_truncated = allowed_projects(workspace_id, project_id)
            for project in projects:
                if project_id and project["id"] != project_id:
                    continue
                detail = store.get(project["id"])
                if not detail:
                    continue
                for task in detail.get("tasks", []):
                    if needle not in (str(task.get("title") or "") + " " + str(task.get("description") or "")).casefold():
                        continue
                    result.append(row(kind, task["id"], task["title"], task.get("description"),
                                      updated=task.get("updated_at"), status=task.get("status"),
                                      project_id=project["id"], source="canonical_project_task"))
                    if len(result) >= SOURCE_LIMIT:
                        return result, "partial"
            return result, "partial" if project_truncated else "available"

        if kind == "files":
            project_truncated = False
            if s["projects"] is not None:
                projects, project_truncated = allowed_projects(workspace_id, project_id)
                for project in projects:
                    if project_id and project["id"] != project_id:
                        continue
                    for f in s["projects"].search_files(project["id"], q, limit=25):
                        result.append(row(kind, f["id"], f["title"],
                                          "Indexed Project file" if f.get("indexing_state") == "indexed" else "Project file metadata",
                                          updated=f.get("created_at"), project_id=project["id"],
                                          status=f.get("indexing_state"), source="project_file"))
                        if len(result) >= SOURCE_LIMIT:
                            return result, "partial"
            # Only properly authorized Knowledge documents; no raw blob retrieval.
            documents = store.list(q, limit=SOURCE_LIMIT + 1, access_classes=knowledge_classes(device))
            for doc in documents[:SOURCE_LIMIT]:
                if doc.get("source") == "owner-note":
                    continue
                result.append(row(kind, doc["id"], doc["title"], doc.get("filename") or doc.get("source"),
                                  updated=doc.get("updated_at"), status="indexed" if doc.get("indexed_chunk_count") else "metadata only",
                                  source="knowledge_document"))
                if len(result) >= SOURCE_LIMIT:
                    return result, "partial"
            return result, "partial" if project_truncated or len(documents) > SOURCE_LIMIT else "available"

        if kind == "knowledge":
            documents = store.list(q, limit=SOURCE_LIMIT + 1, access_classes=knowledge_classes(device))
            for doc in documents[:SOURCE_LIMIT]:
                result.append(row(kind, doc["id"], doc.get("title"), doc.get("filename") or doc.get("source"),
                                  updated=doc.get("updated_at"), source="knowledge_document"))
            return result, "partial" if len(documents) > SOURCE_LIMIT else "available"

        if kind == "memory":
            if not memory_enabled(store):
                return [], "disabled"
            # Normal-sensitivity owner memories only. No sensitive/secret contents
            # or extracted plaintext stored in this read projection.
            memories = store.search(q, limit=SOURCE_LIMIT + 1, active_only=True)
            for mem in memories[:SOURCE_LIMIT]:
                if str(mem.get("sensitivity") or "normal").lower() != "normal":
                    continue
                result.append(row(kind, mem["id"], mem.get("subject") or "Saved memory",
                                  "Owner memory · content hidden in search results",
                                  updated=mem.get("updated_at"), source="normal_owner_memory"))
            return result, "partial" if len(memories) > SOURCE_LIMIT else "available"

        if kind == "agents":
            catalog = store.catalog()
            for agent in catalog[:SOURCE_LIMIT]:
                title = agent.get("name") or agent.get("display_name") or agent.get("id", "")
                desc = agent.get("description") or agent.get("purpose") or ""
                if needle not in (str(title) + " " + str(desc)).casefold():
                    continue
                result.append(row(kind, agent.get("id") or agent.get("template_id"),
                                  title, desc, updated=agent.get("updated_at"),
                                  status=agent.get("state") or "", source="agent_workforce"))
            return result, "partial" if len(catalog) > SOURCE_LIMIT else "available"

        return [], "unavailable"

    def relevance(item, q):
        title = item["title"].casefold()
        excerpt = item["excerpt"].casefold()
        needle = q.casefold()
        if title == needle:
            return 100
        if title.startswith(needle):
            return 70
        if needle in title:
            return 50
        if needle in excerpt:
            return 20
        return 1

    @router.get("")
    def search(
        q: str = Query(min_length=1, max_length=160),
        category: Literal["all", "conversations", "workspaces", "projects", "files", "work", "agents", "knowledge", "memory"] = "all",
        project_id: str = Query(default="", max_length=80),
        workspace_id: str = Query(default="", max_length=80),
        tag: str = Query(default="", max_length=32),
        date_from: date | None = None,
        date_to: date | None = None,
        sort: Literal["relevance", "recent", "oldest", "title"] = "relevance",
        offset: int = Query(default=0, ge=0, le=500),
        limit: int = Query(default=30, ge=1, le=60),
        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None),
    ):
        device = session(pa_device, pa_token)
        if not q.strip():
            raise HTTPException(422, "Search query cannot be blank")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "Invalid date range")
        authorise_target(project_id, workspace_id)
        requested = KINDS  # Always derive real category counts for visible tabs.
        rows, coverage = [], {}
        for kind in requested:
            if workspace_id and kind in ("workspaces", "knowledge", "memory", "agents"):
                coverage[kind] = "not_scoped"
                continue
            if project_id and kind in ("workspaces", "knowledge", "memory", "agents"):
                coverage[kind] = "not_scoped"
                continue
            try:
                items, state = search_source(kind, q.strip(), device, project_id=project_id,
                                             workspace_id=workspace_id)
                coverage[kind] = state
                rows.extend(items or [])
            except (OSError, ValueError, RuntimeError, KeyError, AttributeError) as error:
                coverage[kind] = "unavailable"
        if tag:
            rows = [r for r in rows if tag.casefold() in {str(t).casefold() for t in r["tags"]}]
        if date_from:
            rows = [r for r in rows if r["updated_at"][:10] >= str(date_from)]
        if date_to:
            rows = [r for r in rows if r["updated_at"][:10] <= str(date_to)]
        counts = dict(Counter(r["type"] for r in rows))
        for kind in KINDS:
            counts.setdefault(kind, 0)
        selected = rows if category == "all" else [r for r in rows if r["type"] == category]
        if sort == "title":
            selected.sort(key=lambda r: (r["title"].casefold(), r["id"], r["type"]))
        elif sort == "oldest":
            selected.sort(key=lambda r: (r["updated_at"], r["type"], r["id"]))
        elif sort == "recent":
            selected.sort(key=lambda r: (r["updated_at"], r["type"], r["id"]), reverse=True)
        else:
            selected.sort(key=lambda r: (relevance(r, q.strip()), r["updated_at"], r["type"], r["id"]), reverse=True)
        page = selected[offset:offset + limit]
        truncated = any(v == "partial" for v in coverage.values())
        return {
            "query": q.strip(), "category": category, "results": page,
            "counts": {"all": len(rows), **counts},
            "next_offset": offset + limit if len(selected) > offset + limit else None,
            "count_is_lower_bound": truncated,
            "coverage": coverage,
        }

    @router.get("/result/{kind}/{result_id}")
    def result_detail(
        kind: Literal["conversations", "workspaces", "projects", "files", "work", "agents", "knowledge", "memory"],
        result_id: str,
        project_id: str = "",
        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None),
    ):
        device = session(pa_device, pa_token)
        s = stores()
        resource = None
        preview = []
        related = []
        if kind == "conversations":
            thread = s["conversations"].thread(result_id) if s["conversations"] else None
            if thread and not thread.get("closed_at"):
                ctx = thread.get("context") or {}
                resource = row(kind, result_id, thread.get("title"), updated=thread.get("updated_at"),
                               project_id=ctx.get("project_id"), workspace_id=ctx.get("workspace_id"),
                               context_kind=ctx.get("conversation_kind") or "personal")
                evs = s["conversations"].events_for_thread(result_id, limit=30)
                preview = [{"role": e["kind"], "text": str((e.get("payload") or {}).get("text") or "")[:800]}
                           for e in evs if e.get("kind") in {"user_message", "assistant_message"}][-12:]
                if resource["project_id"]:
                    p = s["projects"].get(resource["project_id"]) if s["projects"] else None
                    if p:
                        related.append({"type": "projects", "id": p["id"], "title": p["name"]})
        elif kind == "projects":
            p = s["projects"].get(result_id) if s["projects"] else None
            if p:
                resource = row(kind, p["id"], p["name"], p.get("goal") or p.get("description"),
                               updated=p.get("updated_at"), project_id=p["id"], status=p.get("status"))
                related = [{"type": "work", "id": t["id"], "title": t["title"], "project_id": p["id"]}
                           for t in p.get("tasks", [])[:8]]
        elif kind == "workspaces":
            w = s["workspaces"].get("owner", result_id) if s["workspaces"] else None
            if w and w.get("status") != "archived":
                resource = row(kind, w["id"], w["name"], w.get("description"),
                               updated=w.get("updated_at"), workspace_id=w["id"])
                related = [{"type": "projects", "id": link["resource_id"], "title": s["projects"].get(link["resource_id"])["name"]}
                           for link in s["workspaces"].linked_projects("owner", w["id"])[:8]
                           if s["projects"] and s["projects"].get(link["resource_id"])]
        elif kind == "work":
            p = s["projects"].get(project_id) if s["projects"] and project_id else None
            if p:
                task = next((t for t in p.get("tasks", []) if t["id"] == result_id), None)
                if task:
                    resource = row(kind, task["id"], task["title"], task.get("description"),
                                   updated=task.get("updated_at"), project_id=p["id"],
                                   status=task.get("status"))
        elif kind in {"files", "knowledge"}:
            if not permitted(device, "knowledge:read"):
                raise HTTPException(403, "Knowledge access not authorized")
            doc = s["knowledge"].detail(result_id) if s["knowledge"] else None
            if doc and doc.get("access_class") in knowledge_classes(device) and doc.get("current", True):
                resource = row(kind, doc["id"], doc.get("title"),
                               doc.get("filename") or doc.get("source"), updated=doc.get("updated_at"))
            elif kind == "files" and project_id and s["projects"]:
                p = s["projects"].get(project_id)
                file = next((f for f in (p or {}).get("files", []) if f["id"] == result_id), None)
                if file:
                    resource = row(kind, file["id"], file["title"], project_id=p["id"],
                                   updated=file.get("created_at"), status=file.get("indexing_state"))
        elif kind == "memory":
            if not permitted(device, "memory:read"):
                raise HTTPException(403, "Memory access not authorized")
            if not memory_enabled(s["memory"]):
                raise HTTPException(404, "Memory search is disabled or unavailable")
            mem = s["memory"].get(result_id) if s["memory"] else None
            if mem and mem.get("sensitivity", "normal") == "normal" and not mem.get("removed_at"):
                resource = row(kind, mem["id"], mem.get("subject"), "Owner memory · preview withheld",
                               updated=mem.get("updated_at"))
        elif kind == "agents":
            if s["agents"]:
                try:
                    catalog = s["agents"].catalog()
                except (OSError, ValueError, RuntimeError) as exc:
                    raise HTTPException(503, "Agent search source is temporarily unavailable") from exc
                agent = next((a for a in catalog
                              if str(a.get("id") or a.get("template_id")) == result_id), None)
                if agent:
                    resource = row(kind, result_id, agent.get("name") or agent.get("display_name"),
                                   agent.get("description") or agent.get("purpose"))
        if not resource:
            raise HTTPException(404, "Search result unavailable or not authorized")
        return {"result": resource, "preview": preview, "related": related}

    @router.get("/status")
    def status(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device = session(pa_device, pa_token)
        return {"source_availability": {name: bool(value) and (
            name not in ("knowledge", "files", "memory") or
            permitted(device, "memory:read" if name == "memory" else "knowledge:read")) and (
            name != "memory" or memory_enabled(value))
            for name, value in stores().items()}, "indexing": "canonical live reads; no copied search index"}

    return router
