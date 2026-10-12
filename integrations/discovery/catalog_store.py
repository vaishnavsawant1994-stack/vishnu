"""Persistent discovery metadata; never installs or executes external APIs."""
import json
import sqlite3
from pathlib import Path
from integrations.discovery.public_apis import parse_public_apis

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

    def search(self, query: str = "", limit: int = 50) -> list[dict]:
        if len(query) > 200 or not 1 <= limit <= 100:
            raise ValueError("invalid search parameters")
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM capability_catalog WHERE lower(name) LIKE ? ORDER BY category, name LIMIT ?", ("%" + query.lower().replace("%", "") + "%", limit)).fetchall()
        return [json.loads(row[0]) for row in rows]
