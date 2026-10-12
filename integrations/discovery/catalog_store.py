"""Persistent discovery metadata; never installs or executes external APIs."""
import json
import sqlite3
from pathlib import Path
from integrations.discovery.public_apis import parse_public_apis
from integrations.discovery.openapi import parse_openapi
from integrations.discovery.mcp import normalize_mcp_tool

class CapabilityCatalogStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS capability_catalog (id TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS capability_connections (
                capability_id TEXT PRIMARY KEY, status TEXT NOT NULL, server_url TEXT NOT NULL,
                auth_type TEXT NOT NULL, credential_ref TEXT, approved_by TEXT NOT NULL,
                approved_at REAL NOT NULL, connector_id TEXT NOT NULL
            )""")

    def import_markdown(self, markdown: str) -> int:
        entries = parse_public_apis(markdown)
        with sqlite3.connect(self.path) as db:
            for entry in entries:
                db.execute("INSERT OR REPLACE INTO capability_catalog VALUES (?, ?, ?, ?)", (entry["id"], entry["category"], entry["name"], json.dumps(entry)))
        return len(entries)

    def import_openapi(self, document: dict, *, source_url: str | None = None) -> int:
        """Persist reviewed OpenAPI operations as inert metadata only."""
        entries = parse_openapi(document, source_url=source_url)
        with sqlite3.connect(self.path) as db:
            for entry in entries:
                db.execute("INSERT OR REPLACE INTO capability_catalog VALUES (?, ?, ?, ?)",
                           (entry["id"], "OpenAPI", entry["name"], json.dumps(entry)))
        return len(entries)

    def import_mcp_server(self, server: dict) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO capability_catalog VALUES (?, ?, ?, ?)",
                       (server["id"], "MCP", server["name"], json.dumps(server)))

    def import_mcp_tools(self, server_id: str, tools: list[dict], *, server_name: str = "", server_url: str = "") -> list[dict]:
        if not isinstance(tools, list) or len(tools) > 500:
            raise ValueError("invalid MCP tools list")
        entries = [normalize_mcp_tool(server_id, raw) for raw in tools]
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("MCP server returned duplicate tool names")
        for entry in entries:
            entry.update({"server_name": str(server_name)[:200], "server_url": server_url})
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT id,payload FROM capability_catalog WHERE category='MCP'").fetchall()
            old_ids = {row[0] for row in rows if json.loads(row[1]).get("type") == "mcp_tool" and json.loads(row[1]).get("server_id") == server_id}
            current_ids = {entry["id"] for entry in entries}
            for stale_id in old_ids - current_ids:
                db.execute("DELETE FROM capability_connections WHERE capability_id=?", (stale_id,))
                db.execute("DELETE FROM capability_catalog WHERE id=?", (stale_id,))
            for entry in entries:
                db.execute("INSERT OR REPLACE INTO capability_catalog VALUES (?, ?, ?, ?)",
                           (entry["id"], "MCP", entry["name"], json.dumps(entry)))
        return entries

    def update_payload(self, capability_id: str, payload: dict) -> None:
        with sqlite3.connect(self.path) as db:
            cur = db.execute("UPDATE capability_catalog SET category=?,name=?,payload=? WHERE id=?",
                             ("MCP", str(payload.get("name") or "Capability")[:200], json.dumps(payload), capability_id))
            if cur.rowcount != 1:
                raise KeyError(capability_id)

    def mcp_tools(self, server_id: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM capability_catalog WHERE category='MCP' ORDER BY name").fetchall()
        return [entry for (payload,) in rows if (entry := json.loads(payload)).get("type") == "mcp_tool" and entry.get("server_id") == server_id]

    def mcp_servers(self) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM capability_catalog WHERE category='MCP' ORDER BY name").fetchall()
        return [entry for (payload,) in rows if (entry := json.loads(payload)).get("type") == "mcp_server"]

    def get(self, capability_id: str) -> dict | None:
        if not isinstance(capability_id, str) or len(capability_id) > 200:
            raise ValueError("invalid capability id")
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload FROM capability_catalog WHERE id = ?", (capability_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def search(self, query: str = "", limit: int = 50) -> list[dict]:
        if len(query) > 200 or not 1 <= limit <= 100:
            raise ValueError("invalid search parameters")
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM capability_catalog WHERE lower(name) LIKE ? ORDER BY category, name LIMIT ?", ("%" + query.lower().replace("%", "") + "%", limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def all(self) -> list[dict]:
        """Return bounded catalog metadata for startup tool rehydration."""
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM capability_catalog ORDER BY category,name LIMIT 5000").fetchall()
        return [json.loads(row[0]) for row in rows]

    def connect(self, capability_id: str, *, server_url: str, auth_type: str,
                credential_ref: str | None, approved_by: str, approved_at: float,
                connector_id: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT OR REPLACE INTO capability_connections
                (capability_id,status,server_url,auth_type,credential_ref,approved_by,approved_at,connector_id)
                VALUES (?, 'connected', ?, ?, ?, ?, ?, ?)""",
                (capability_id, server_url, auth_type, credential_ref, approved_by, float(approved_at), connector_id))

    def connection(self, capability_id: str, *, include_credential_ref: bool = False) -> dict | None:
        with sqlite3.connect(self.path) as db:
            columns = "status,server_url,auth_type,approved_by,approved_at,connector_id"
            if include_credential_ref:
                columns += ",credential_ref"
            row = db.execute(f"SELECT {columns} FROM capability_connections WHERE capability_id=?", (capability_id,)).fetchone()
        if not row:
            return None
        keys = ("status", "server_url", "auth_type", "approved_by", "approved_at", "connector_id")
        if include_credential_ref:
            keys += ("credential_ref",)
        return dict(zip(keys, row))

    def revoke(self, capability_id: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT credential_ref FROM capability_connections WHERE capability_id=? AND status='connected'", (capability_id,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE capability_connections SET status='revoked',credential_ref=NULL WHERE capability_id=?", (capability_id,))
        return row[0]

    def update_connection_credentials(self, capability_id: str, *, auth_type: str,
                                      credential_ref: str | None) -> bool:
        if auth_type not in {"none", "bearer_token", "api_key_header"}:
            raise ValueError("unsupported credential type")
        with sqlite3.connect(self.path) as db:
            cur = db.execute(
                "UPDATE capability_connections SET auth_type=?,credential_ref=? "
                "WHERE capability_id=? AND status='connected'",
                (auth_type, credential_ref, capability_id),
            )
            return cur.rowcount == 1
