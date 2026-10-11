from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class CommercialProductStore:
    """Owner-side commercial metadata stored beside the ProductStore database.

    This is not a tenant boundary. Client IDs are commercial references for the
    single-owner control plane. Each deployed client runtime still receives an
    isolated data/secrets boundary.
    """

    def __init__(self, path: str | Path):
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
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_clients(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    contact_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commercial_product_licenses(
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    client_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    signed_document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_commercial_licenses_product
                    ON commercial_product_licenses(product_id,created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_commercial_licenses_client
                    ON commercial_product_licenses(client_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS product_installations(
                    id TEXT PRIMARY KEY,
                    license_id TEXT NOT NULL REFERENCES commercial_product_licenses(id) ON DELETE CASCADE,
                    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    device_fingerprint TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    activated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(license_id,device_fingerprint)
                );
                CREATE INDEX IF NOT EXISTS idx_product_installations_product
                    ON product_installations(product_id,last_seen_at DESC);
                CREATE TABLE IF NOT EXISTS product_usage_events(
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    client_id TEXT,
                    license_id TEXT,
                    event_type TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 1,
                    unit TEXT NOT NULL DEFAULT 'event',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_product_usage_product
                    ON product_usage_events(product_id,created_at DESC);
                """
            )

    def upsert_client(self, *, client_id: str | None = None, name: str, contact: dict | None = None, status="active"):
        client_id = str(client_id or uuid.uuid4())
        name = str(name or "").strip()
        if not name:
            raise ValueError("Client name is required")
        if status not in {"active", "paused", "archived"}:
            raise ValueError("Unsupported client status")
        stamp = _now()
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO product_clients(id,name,contact_json,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,contact_json=excluded.contact_json,
                     status=excluded.status,updated_at=excluded.updated_at""",
                (client_id, name, _json(contact or {}), status, stamp, stamp),
            )
        return self.client(client_id)

    def client(self, client_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_clients WHERE id=?", (client_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["contact"] = _loads(value.pop("contact_json"), {})
        return value

    def clients(self, *, include_archived=False):
        query = "SELECT * FROM product_clients"
        if not include_archived:
            query += " WHERE status!='archived'"
        query += " ORDER BY name COLLATE NOCASE"
        with self.con() as con:
            rows = con.execute(query).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["contact"] = _loads(value.pop("contact_json"), {})
            result.append(value)
        return result

    def save_license(self, *, product_id: str, client_id: str, document: dict):
        payload = document.get("payload") if isinstance(document, dict) else None
        if not isinstance(payload, dict) or payload.get("schema") != "vishnu.license/v1":
            raise ValueError("A signed Vishnu license document is required")
        if payload.get("product_id") != product_id or payload.get("client_id") != client_id:
            raise ValueError("License product/client binding does not match")
        license_id = str(payload.get("license_id") or "").strip()
        if not license_id:
            raise ValueError("License document is missing license_id")
        stamp = _now()
        with self.lock, self.con() as con:
            if not con.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
                raise ValueError("Product not found")
            con.execute(
                """INSERT INTO commercial_product_licenses(id,product_id,client_id,status,signed_document_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     signed_document_json=excluded.signed_document_json,
                     updated_at=excluded.updated_at""",
                (license_id, product_id, client_id, "active", _json(document), stamp, stamp),
            )
        return self.license(license_id)

    def license(self, license_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM commercial_product_licenses WHERE id=?", (license_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["document"] = _loads(value.pop("signed_document_json"), {})
        return value

    def licenses(self, product_id: str):
        with self.con() as con:
            rows = con.execute(
                "SELECT * FROM commercial_product_licenses WHERE product_id=? ORDER BY created_at DESC",
                (product_id,),
            ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["document"] = _loads(value.pop("signed_document_json"), {})
            result.append(value)
        return result

    def revoke_license(self, license_id: str) -> bool:
        with self.lock, self.con() as con:
            stamp = _now()
            cur = con.execute(
                "UPDATE commercial_product_licenses SET status='revoked',updated_at=? WHERE id=? AND status!='revoked'",
                (stamp, license_id),
            )
            if cur.rowcount:
                con.execute(
                    "UPDATE product_installations SET status='revoked',last_seen_at=? WHERE license_id=?",
                    (stamp, license_id),
                )
            return bool(cur.rowcount)

    def activate_installation(self, *, license_id: str, device_fingerprint: str, platform: str, version: str, verifier):
        license_row = self.license(license_id)
        if not license_row or license_row["status"] != "active":
            raise ValueError("License is not active")
        payload = verifier.verify(license_row["document"], product_id=license_row["product_id"])
        fingerprint = str(device_fingerprint or "").strip()
        if not fingerprint:
            raise ValueError("device_fingerprint is required")
        limit = payload.get("device_limit")
        stamp = _now()
        with self.lock, self.con() as con:
            existing = con.execute(
                "SELECT * FROM product_installations WHERE license_id=? AND device_fingerprint=?",
                (license_id, fingerprint),
            ).fetchone()
            if not existing and limit is not None:
                active = con.execute(
                    "SELECT count(*) count FROM product_installations WHERE license_id=? AND status='active'",
                    (license_id,),
                ).fetchone()["count"]
                if int(active) >= int(limit):
                    raise ValueError("License device limit reached")
            if existing:
                con.execute(
                    """UPDATE product_installations SET platform=?,version=?,status='active',last_seen_at=?
                       WHERE license_id=? AND device_fingerprint=?""",
                    (str(platform), str(version), stamp, license_id, fingerprint),
                )
                installation_id = existing["id"]
            else:
                installation_id = str(uuid.uuid4())
                con.execute(
                    "INSERT INTO product_installations VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        installation_id,
                        license_id,
                        license_row["product_id"],
                        fingerprint,
                        str(platform),
                        str(version),
                        "active",
                        stamp,
                        stamp,
                    ),
                )
        return self.installation(installation_id)

    def installation(self, installation_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_installations WHERE id=?", (installation_id,)).fetchone()
        return dict(row) if row else None

    def installations(self, product_id: str):
        with self.con() as con:
            rows = con.execute(
                "SELECT * FROM product_installations WHERE product_id=? ORDER BY last_seen_at DESC",
                (product_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_usage(self, *, product_id: str, event_type: str, quantity=1, unit="event", client_id=None, license_id=None, metadata=None):
        quantity = float(quantity)
        if quantity < 0:
            raise ValueError("Usage quantity cannot be negative")
        stamp, event_id = _now(), str(uuid.uuid4())
        with self.lock, self.con() as con:
            if not con.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
                raise ValueError("Product not found")
            con.execute(
                "INSERT INTO product_usage_events VALUES(?,?,?,?,?,?,?,?,?)",
                (event_id, product_id, client_id, license_id, str(event_type)[:160], quantity, str(unit)[:80], _json(metadata or {}), stamp),
            )
        return event_id

    def usage_summary(self, product_id: str):
        with self.con() as con:
            rows = con.execute(
                """SELECT event_type,unit,count(*) events,sum(quantity) quantity
                   FROM product_usage_events WHERE product_id=? GROUP BY event_type,unit ORDER BY event_type,unit""",
                (product_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_deployment(self, *, product_id: str, target: str, version: str, status: str, environment="production", url=None, metadata=None, deployment_id=None):
        deployment_id = str(deployment_id or uuid.uuid4())
        stamp = _now()
        with self.lock, self.con() as con:
            if not con.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
                raise ValueError("Product not found")
            con.execute(
                """INSERT INTO product_deployments(id,product_id,target,environment,status,url,version,metadata_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     target=excluded.target,environment=excluded.environment,status=excluded.status,
                     url=excluded.url,version=excluded.version,metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (deployment_id, product_id, str(target), str(environment), str(status), url, str(version), _json(metadata or {}), stamp, stamp),
            )
        return self.deployment(deployment_id)

    def deployment(self, deployment_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_deployments WHERE id=?", (deployment_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["metadata"] = _loads(value.pop("metadata_json"), {})
        return value

    def deployments(self, product_id: str):
        with self.con() as con:
            rows = con.execute(
                "SELECT * FROM product_deployments WHERE product_id=? ORDER BY updated_at DESC",
                (product_id,),
            ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["metadata"] = _loads(value.pop("metadata_json"), {})
            result.append(value)
        return result
