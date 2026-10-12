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
