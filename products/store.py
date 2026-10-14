from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from core.sqlite import connect_sqlite, run_script_migration

from .models import AI_MODES, PLATFORM_TARGETS, PRODUCT_STATUSES, PRODUCT_TYPES, ensure_choice


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


_SECRET_FIELD_NAMES = {
    "api_key", "apikey", "api-key", "token", "access_token", "refresh_token",
    "password", "secret", "client_secret", "private_key",
}


def _reject_embedded_secrets(value, path="config"):
    """Fail closed if a product definition attempts to persist raw credentials."""
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in _SECRET_FIELD_NAMES and item not in (None, ""):
                raise ValueError(f"Raw credentials are not allowed in product definitions ({path}.{key}); store a secret_ref instead")
            _reject_embedded_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_secrets(item, f"{path}[{index}]")


class ProductStore:
    """SQLite store for the single-owner Our Products workspace.

    Client is commercial metadata in this first release, not a tenant/security
    boundary. Product secrets are references only; raw credentials are rejected.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._init()

    def con(self):
        return connect_sqlite(self.path, timeout_seconds=10)

    def _init(self):
        with self.con() as con:
            run_script_migration(con, component="products.store", script="""
            CREATE TABLE IF NOT EXISTS products(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                product_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                client_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                version TEXT NOT NULL DEFAULT '0.1.0',
                source_project_id TEXT,
                ai_mode TEXT NOT NULL DEFAULT 'disabled',
                ai_policy_json TEXT NOT NULL DEFAULT '{}',
                branding_json TEXT NOT NULL DEFAULT '{}',
                licensing_json TEXT NOT NULL DEFAULT '{}',
                permissions_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_targets(
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                target TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                config_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(product_id,target)
            );
            CREATE TABLE IF NOT EXISTS product_components(
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                component_type TEXT NOT NULL,
                component_ref TEXT,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_versions(
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(product_id,version)
            );
            CREATE TABLE IF NOT EXISTS product_builds(
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_name TEXT,
                checksum TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS product_deployments(
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                target TEXT NOT NULL,
                environment TEXT NOT NULL DEFAULT 'production',
                status TEXT NOT NULL,
                url TEXT,
                version TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_activity(
                id TEXT PRIMARY KEY,
                product_id TEXT REFERENCES products(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_products_updated ON products(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_product_activity_created ON product_activity(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_product_builds_product ON product_builds(product_id,created_at DESC);
            """)

    def _activity(self, con, product_id, event_type, message, metadata=None):
        con.execute(
            "INSERT INTO product_activity VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), product_id, event_type, str(message)[:1000], _json(metadata or {}), _now()),
        )

    def _row(self, row):
        if not row:
            return None
        item = dict(row)
        item["ai_policy"] = _loads(item.pop("ai_policy_json", "{}"), {})
        item["branding"] = _loads(item.pop("branding_json", "{}"), {})
        item["licensing"] = _loads(item.pop("licensing_json", "{}"), {})
        item["permissions"] = _loads(item.pop("permissions_json", "{}"), {})
        item["targets"] = self.targets(item["id"])
        item["component_count"] = self.component_count(item["id"])
        return item

    def list(self, query="", *, product_type="all", status="all", sort="recent"):
        clauses = ["status!='archived'"]
        values = []
        query = str(query or "").strip()
        if query:
            clauses.append("(name LIKE ? OR description LIKE ? OR client_name LIKE ?)")
            wildcard = f"%{query}%"
            values.extend([wildcard, wildcard, wildcard])
        if product_type != "all":
            clauses.append("product_type=?")
            values.append(ensure_choice(product_type, PRODUCT_TYPES, "product type"))
        if status != "all":
            clauses.append("status=?")
            values.append(ensure_choice(status, PRODUCT_STATUSES, "product status"))
        order = {
            "recent": "updated_at DESC",
            "name": "name COLLATE NOCASE ASC",
            "created": "created_at DESC",
        }.get(sort, "updated_at DESC")
        with self.con() as con:
            rows = con.execute(f"SELECT * FROM products WHERE {' AND '.join(clauses)} ORDER BY {order}", values).fetchall()
        return [self._row(row) for row in rows]

    def get(self, product_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return self._row(row)

    def create(self, *, name, product_type="custom", description="", client_name="", status="development", version="0.1.0", source_project_id=None, ai_mode="disabled", targets=None):
        name = str(name or "").strip()
        if not name:
            raise ValueError("A product name is required")
        kind = ensure_choice(product_type, PRODUCT_TYPES, "product type")
        state = ensure_choice(status, PRODUCT_STATUSES, "product status")
        mode = ensure_choice(ai_mode, AI_MODES, "AI mode")
        target_values = []
        for target in targets or []:
            target_values.append(ensure_choice(target, PLATFORM_TARGETS, "platform target"))
        product_id, stamp = str(uuid.uuid4()), _now()
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO products(id,name,product_type,description,client_name,status,version,source_project_id,ai_mode,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (product_id, name, kind, str(description or "").strip(), str(client_name or "").strip(), state, str(version or "0.1.0").strip(), source_project_id, mode, stamp, stamp),
            )
            for target in dict.fromkeys(target_values):
                con.execute("INSERT INTO product_targets(product_id,target,enabled) VALUES(?,?,1)", (product_id, target))
            self._activity(con, product_id, "product.created", f"Created {name}")
        return self.get(product_id)

    def create_from_project(self, project: dict, *, product_type="custom", client_name=""):
        if not project or not project.get("id"):
            raise ValueError("Project not found")
        existing = self.find_by_source_project(project["id"])
        if existing:
            raise ValueError("This project has already been promoted to a product")
        description = project.get("description") or project.get("goal") or ""
        return self.create(
            name=project.get("name") or "Untitled product",
            product_type=product_type,
            description=description,
            client_name=client_name,
            source_project_id=project["id"],
            status="development",
        )

    def find_by_source_project(self, project_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM products WHERE source_project_id=? AND status!='archived' LIMIT 1", (project_id,)).fetchone()
        return self._row(row)

    def update(self, product_id: str, fields: dict):
        allowed = {"name", "description", "client_name", "version", "source_project_id"}
        values = {}
        for key, value in fields.items():
            if key in allowed:
                values[key] = str(value).strip() if value is not None else None
            elif key == "product_type":
                values[key] = ensure_choice(value, PRODUCT_TYPES, "product type")
            elif key == "status":
                values[key] = ensure_choice(value, PRODUCT_STATUSES, "product status")
            elif key in {"branding", "licensing", "permissions"}:
                _reject_embedded_secrets(value, key)
                values[f"{key}_json"] = _json(value or {})
        if "name" in values and not values["name"]:
            raise ValueError("A product name is required")
        if not values:
            return self.get(product_id)
        values["updated_at"] = _now()
        assignment = ",".join(f"{key}=?" for key in values)
        with self.lock, self.con() as con:
            cur = con.execute(f"UPDATE products SET {assignment} WHERE id=?", (*values.values(), product_id))
            if not cur.rowcount:
                return None
            self._activity(con, product_id, "product.updated", "Product settings updated", {"fields": list(fields)})
        return self.get(product_id)

    def archive(self, product_id: str) -> bool:
        with self.lock, self.con() as con:
            cur = con.execute("UPDATE products SET status='archived',updated_at=? WHERE id=?", (_now(), product_id))
            if cur.rowcount:
                self._activity(con, product_id, "product.archived", "Product archived")
            return bool(cur.rowcount)

    def set_ai_policy(self, product_id: str, policy: dict):
        _reject_embedded_secrets(policy, "ai_policy")
        mode = ensure_choice(policy.get("mode", "disabled"), AI_MODES, "AI mode")
        clean = dict(policy)
        clean["mode"] = mode
        # A secret_ref may identify an encrypted vault entry; it must never contain the credential itself.
        if clean.get("secret_ref") is not None:
            clean["secret_ref"] = str(clean["secret_ref"])[:300]
        with self.lock, self.con() as con:
            cur = con.execute("UPDATE products SET ai_mode=?,ai_policy_json=?,updated_at=? WHERE id=?", (mode, _json(clean), _now(), product_id))
            if not cur.rowcount:
                return None
            self._activity(con, product_id, "product.ai_policy_updated", f"AI mode set to {mode}")
        return self.get(product_id)

    def set_targets(self, product_id: str, targets: list[dict]):
        normalized = []
        for item in targets:
            target = ensure_choice(item.get("target"), PLATFORM_TARGETS, "platform target")
            config = item.get("config") or {}
            _reject_embedded_secrets(config, f"targets.{target}")
            normalized.append((target, bool(item.get("enabled", True)), config))
        if not self.get(product_id):
            return None
        with self.lock, self.con() as con:
            con.execute("DELETE FROM product_targets WHERE product_id=?", (product_id,))
            for target, enabled, config in normalized:
                con.execute(
                    "INSERT OR REPLACE INTO product_targets(product_id,target,enabled,config_json) VALUES(?,?,?,?)",
                    (product_id, target, int(enabled), _json(config)),
                )
            con.execute("UPDATE products SET updated_at=? WHERE id=?", (_now(), product_id))
            self._activity(con, product_id, "product.targets_updated", "Delivery targets updated", {"targets": [item[0] for item in normalized if item[1]]})
        return self.get(product_id)

    def targets(self, product_id: str):
        with self.con() as con:
            rows = con.execute("SELECT target,enabled,config_json FROM product_targets WHERE product_id=? ORDER BY target", (product_id,)).fetchall()
        return [{"target": row["target"], "enabled": bool(row["enabled"]), "config": _loads(row["config_json"], {})} for row in rows]

    def add_component(self, product_id: str, *, component_type, name, component_ref=None, config=None, sort_order=0):
        if not self.get(product_id):
            return None
        config = config or {}
        _reject_embedded_secrets(config, "component.config")
        component_id, stamp = str(uuid.uuid4()), _now()
        with self.lock, self.con() as con:
            con.execute(
                "INSERT INTO product_components VALUES(?,?,?,?,?,?,?,?)",
                (component_id, product_id, str(component_type).strip(), component_ref, str(name).strip(), _json(config), int(sort_order), stamp),
            )
            con.execute("UPDATE products SET updated_at=? WHERE id=?", (stamp, product_id))
            self._activity(con, product_id, "product.component_added", f"Added {name}", {"component_type": component_type})
        return self.component(component_id)

    def component(self, component_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_components WHERE id=?", (component_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["config"] = _loads(value.pop("config_json"), {})
        return value

    def components(self, product_id: str):
        with self.con() as con:
            rows = con.execute("SELECT * FROM product_components WHERE product_id=? ORDER BY sort_order,created_at", (product_id,)).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["config"] = _loads(value.pop("config_json"), {})
            result.append(value)
        return result

    def component_count(self, product_id: str) -> int:
        with self.con() as con:
            row = con.execute("SELECT count(*) count FROM product_components WHERE product_id=?", (product_id,)).fetchone()
        return int(row["count"] if row else 0)

    def remove_component(self, product_id: str, component_id: str) -> bool:
        with self.lock, self.con() as con:
            cur = con.execute("DELETE FROM product_components WHERE id=? AND product_id=?", (component_id, product_id))
            if cur.rowcount:
                con.execute("UPDATE products SET updated_at=? WHERE id=?", (_now(), product_id))
                self._activity(con, product_id, "product.component_removed", "Removed product component", {"component_id": component_id})
            return bool(cur.rowcount)

    def manifest(self, product_id: str):
        product = self.get(product_id)
        if not product:
            return None
        manifest = {
            "schema": "vishnu.product/v1",
            "product_id": product["id"],
            "name": product["name"],
            "product_type": product["product_type"],
            "version": product["version"],
            "description": product["description"],
            "client": {"display_name": product["client_name"]},
            "source_project_id": product["source_project_id"],
            "components": self.components(product_id),
            "ai_policy": product["ai_policy"],
            "permissions": product["permissions"],
            "targets": [item for item in product["targets"] if item["enabled"]],
            "branding": product["branding"],
            "licensing": product["licensing"],
        }
        _reject_embedded_secrets(manifest, "manifest")
        return manifest

    def create_version(self, product_id: str, *, version: str | None = None, notes=""):
        product = self.get(product_id)
        if not product:
            return None
        version = str(version or product["version"]).strip()
        manifest = self.manifest(product_id)
        version_id, stamp = str(uuid.uuid4()), _now()
        try:
            with self.lock, self.con() as con:
                con.execute("INSERT INTO product_versions VALUES(?,?,?,?,?,?)", (version_id, product_id, version, _json(manifest), str(notes or ""), stamp))
                con.execute("UPDATE products SET version=?,updated_at=? WHERE id=?", (version, stamp, product_id))
                self._activity(con, product_id, "product.version_created", f"Version {version} frozen")
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Version {version} already exists") from exc
        return {"id": version_id, "product_id": product_id, "version": version, "manifest": manifest, "notes": str(notes or ""), "created_at": stamp}

    def request_build(self, product_id: str, *, target: str, version: str | None = None):
        product = self.get(product_id)
        if not product:
            return None
        target = ensure_choice(target, PLATFORM_TARGETS, "platform target")
        enabled = {item["target"] for item in product["targets"] if item["enabled"]}
        if target not in enabled:
            raise ValueError(f"Target {target} is not enabled for this product")
        build_id, stamp = str(uuid.uuid4()), _now()
        version = str(version or product["version"])
        # This record is a governed request, not a claim that a native artifact exists.
        metadata = {"builder_state": "adapter_pending", "artifact_ready": False}
        with self.lock, self.con() as con:
            con.execute("INSERT INTO product_builds VALUES(?,?,?,?,?,?,?,?,?,?)", (build_id, product_id, version, target, "requested", None, None, _json(metadata), stamp, None))
            self._activity(con, product_id, "product.build_requested", f"Build requested for {target}", {"build_id": build_id, "version": version})
        return {"id": build_id, "product_id": product_id, "version": version, "target": target, "status": "requested", "artifact_name": None, "checksum": None, "metadata": metadata, "created_at": stamp, "completed_at": None}

    def builds(self, product_id: str, *, limit=100):
        with self.con() as con:
            rows = con.execute("SELECT * FROM product_builds WHERE product_id=? ORDER BY created_at DESC LIMIT ?", (product_id, max(1, min(int(limit), 500)))).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["metadata"] = _loads(value.pop("metadata_json"), {})
            result.append(value)
        return result

    def summary(self):
        with self.con() as con:
            counts = {row["status"]: row["count"] for row in con.execute("SELECT status,count(*) count FROM products WHERE status!='archived' GROUP BY status")}
            total = con.execute("SELECT count(*) count FROM products WHERE status!='archived'").fetchone()["count"]
            clients = con.execute("SELECT count(DISTINCT client_name) count FROM products WHERE status!='archived' AND trim(client_name)!=''").fetchone()["count"]
        return {
            "total": int(total),
            "development": int(counts.get("development", 0) + counts.get("draft", 0)),
            "ready": int(counts.get("ready", 0)),
            "live": int(counts.get("live", 0)),
            "clients": int(clients),
            "needs_attention": int(counts.get("needs_attention", 0)),
        }

    def activity(self, *, limit=50):
        with self.con() as con:
            rows = con.execute(
                """SELECT a.*,p.name product_name FROM product_activity a
                   LEFT JOIN products p ON p.id=a.product_id ORDER BY a.created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _loads(item.pop("metadata_json"), {})
            result.append(item)
        return result
