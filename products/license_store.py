from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from .licensing import build_license_document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductLicenseStore:
    """Persistent commercial license registry stored beside product metadata."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._init()

    def con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self.con() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS product_licenses(
                license_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                client_name TEXT NOT NULL,
                license_type TEXT NOT NULL,
                version_constraint TEXT NOT NULL,
                starts_at TEXT,
                expires_at TEXT,
                max_users INTEGER,
                max_devices INTEGER,
                managed_ai INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_product_licenses_product
                ON product_licenses(product_id,created_at DESC);
            """)

    def issue(
        self,
        *,
        product: dict,
        client_name: str,
        license_type: str = "organization",
        version_constraint: str | None = None,
        starts_at: str | None = None,
        expires_at: str | None = None,
        max_users: int | None = None,
        max_devices: int | None = None,
        managed_ai: bool = False,
        metadata: dict | None = None,
    ) -> dict:
        document = build_license_document(
            product_id=product["id"],
            product_name=product["name"],
            version_constraint=version_constraint or product.get("version") or "*",
            client_name=client_name,
            license_type=license_type,
            starts_at=starts_at,
            expires_at=expires_at,
            max_users=max_users,
            max_devices=max_devices,
            managed_ai=managed_ai,
            metadata=metadata,
            require_signature=True,
        )
        payload = document["payload"]
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO product_licenses(
                    license_id,product_id,client_name,license_type,version_constraint,
                    starts_at,expires_at,max_users,max_devices,managed_ai,status,
                    document_json,created_at,revoked_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?, 'active', ?,?,NULL)""",
                (
                    payload["license_id"], product["id"], payload["client_name"],
                    payload["license_type"], payload["version_constraint"],
                    payload["starts_at"], payload["expires_at"], payload["max_users"],
                    payload["max_devices"], int(payload["managed_ai"]),
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    payload["issued_at"],
                ),
            )
        return self.get(payload["license_id"])

    def get(self, license_id: str) -> dict | None:
        with self.con() as con:
            row = con.execute("SELECT * FROM product_licenses WHERE license_id=?", (license_id,)).fetchone()
        return self._row(row)

    def list_for_product(self, product_id: str, *, limit: int = 100) -> list[dict]:
        with self.con() as con:
            rows = con.execute(
                "SELECT * FROM product_licenses WHERE product_id=? ORDER BY created_at DESC LIMIT ?",
                (product_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def revoke(self, product_id: str, license_id: str) -> dict | None:
        stamp = _now()
        with self.lock, self.con() as con:
            cur = con.execute(
                "UPDATE product_licenses SET status='revoked',revoked_at=? WHERE product_id=? AND license_id=? AND status!='revoked'",
                (stamp, product_id, license_id),
            )
            if not cur.rowcount:
                row = con.execute(
                    "SELECT license_id FROM product_licenses WHERE product_id=? AND license_id=?",
                    (product_id, license_id),
                ).fetchone()
                if not row:
                    return None
        return self.get(license_id)

    @staticmethod
    def _row(row) -> dict | None:
        if not row:
            return None
        value = dict(row)
        value["managed_ai"] = bool(value["managed_ai"])
        value["document"] = json.loads(value.pop("document_json"))
        return value
