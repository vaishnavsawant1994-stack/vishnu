"""Persistent discovery metadata; never installs or executes external APIs."""
import json
import sqlite3
from pathlib import Path
from integrations.discovery.public_apis import parse_public_apis
from integrations.discovery.openapi import parse_openapi

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
