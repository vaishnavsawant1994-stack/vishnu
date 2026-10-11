from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


CAPABILITY_TYPES = (
    "agent", "agent_team", "workflow", "automation", "tool", "integration",
    "knowledge", "ocr", "browser", "api", "ui", "backend", "database",
    "document", "product_template", "saas_module", "business_logic", "custom",
)
COMMERCIAL_STATES = (
    "internal_only", "internal_reusable", "internal_sellable", "commercial",
    "client_specific", "template", "experimental",
)
QUALIFICATION_STATES = ("unknown", "available", "tested", "qualified", "deprecated")


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


def _text(value) -> str:
    return str(value or "").strip()


def _obj(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


class CapabilityCatalog:
    """Durable inventory of things Vishnu may safely reuse in Product Projects.

    Client-private capabilities remain scoped to that client. A capability becomes
    globally reusable only through the explicit Product Composer generalization
    path; generic classification edits cannot cross that privacy boundary.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._init()

    def con(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self.con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_capabilities(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    capability_type TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    client_scope TEXT NOT NULL DEFAULT 'shared',
                    commercial_state TEXT NOT NULL DEFAULT 'internal_reusable',
                    qualification_state TEXT NOT NULL DEFAULT 'available',
                    exportable INTEGER NOT NULL DEFAULT 1,
                    reusable INTEGER NOT NULL DEFAULT 1,
                    ai_required INTEGER NOT NULL DEFAULT 0,
                    ai_modes_json TEXT NOT NULL DEFAULT '[]',
                    platforms_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    inputs_json TEXT NOT NULL DEFAULT '[]',
                    outputs_json TEXT NOT NULL DEFAULT '[]',
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    permissions_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_kind,source_ref,client_scope)
                );
                CREATE INDEX IF NOT EXISTS idx_product_capabilities_search
                    ON product_capabilities(capability_type,commercial_state,qualification_state,updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_product_capabilities_scope
                    ON product_capabilities(client_scope,reusable,exportable);
                """
            )

    @staticmethod
    def _row(row):
        if not row:
            return None
        value = dict(row)
        for key, fallback in (
            ("ai_modes_json", []), ("platforms_json", []), ("tags_json", []),
            ("inputs_json", []), ("outputs_json", []), ("dependencies_json", []),
            ("permissions_json", {}), ("metadata_json", {}),
        ):
            value[key.removesuffix("_json")] = _loads(value.pop(key), fallback)
        value["exportable"] = bool(value["exportable"])
        value["reusable"] = bool(value["reusable"])
        value["ai_required"] = bool(value["ai_required"])
        return value

    def upsert(
        self,
        *,
        name: str,
        capability_type: str,
        source_kind: str,
        source_ref: str,
        description: str = "",
        client_scope: str = "shared",
        commercial_state: str = "internal_reusable",
        qualification_state: str = "available",
        exportable: bool = True,
        reusable: bool = True,
        ai_required: bool = False,
        ai_modes=None,
        platforms=None,
        tags=None,
        inputs=None,
        outputs=None,
        dependencies=None,
        permissions=None,
        metadata=None,
        preserve_owner_classification: bool = True,
    ):
        name = _text(name)
        source_kind = _text(source_kind)
        source_ref = _text(source_ref)
        client_scope = _text(client_scope) or "shared"
        if not name or not source_kind or not source_ref:
            raise ValueError("Capability name, source_kind and source_ref are required")
        capability_type = _text(capability_type).lower() or "custom"
        if capability_type not in CAPABILITY_TYPES:
            capability_type = "custom"
        if commercial_state not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        if qualification_state not in QUALIFICATION_STATES:
            raise ValueError("Unsupported qualification state")
        stamp = _now()
        with self.lock, self.con() as con:
            existing = con.execute(
                "SELECT id,commercial_state,reusable,exportable FROM product_capabilities WHERE source_kind=? AND source_ref=? AND client_scope=?",
                (source_kind, source_ref, client_scope),
            ).fetchone()
            if existing:
                capability_id = existing["id"]
                state = existing["commercial_state"] if preserve_owner_classification else commercial_state
                reusable_value = int(existing["reusable"]) if preserve_owner_classification else int(bool(reusable))
                exportable_value = int(existing["exportable"]) if preserve_owner_classification else int(bool(exportable))
                con.execute(
                    """UPDATE product_capabilities SET
                       name=?,capability_type=?,description=?,commercial_state=?,qualification_state=?,
                       exportable=?,reusable=?,ai_required=?,ai_modes_json=?,platforms_json=?,tags_json=?,
                       inputs_json=?,outputs_json=?,dependencies_json=?,permissions_json=?,metadata_json=?,updated_at=?
                       WHERE id=?""",
                    (
                        name, capability_type, _text(description), state, qualification_state,
                        exportable_value, reusable_value, int(bool(ai_required)), _json(ai_modes or []),
                        _json(platforms or []), _json(tags or []), _json(inputs or []), _json(outputs or []),
                        _json(dependencies or []), _json(permissions or {}), _json(metadata or {}), stamp, capability_id,
                    ),
                )
            else:
                capability_id = str(uuid.uuid4())
                con.execute(
                    """INSERT INTO product_capabilities(
                       id,name,capability_type,description,source_kind,source_ref,client_scope,commercial_state,
                       qualification_state,exportable,reusable,ai_required,ai_modes_json,platforms_json,tags_json,
                       inputs_json,outputs_json,dependencies_json,permissions_json,metadata_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        capability_id, name, capability_type, _text(description), source_kind, source_ref,
                        client_scope, commercial_state, qualification_state, int(bool(exportable)), int(bool(reusable)),
                        int(bool(ai_required)), _json(ai_modes or []), _json(platforms or []), _json(tags or []),
                        _json(inputs or []), _json(outputs or []), _json(dependencies or []), _json(permissions or {}),
                        _json(metadata or {}), stamp, stamp,
                    ),
                )
        return self.get(capability_id)

    def get(self, capability_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_capabilities WHERE id=?", (capability_id,)).fetchone()
        return self._row(row)

    def list(
        self,
        query: str = "",
        *,
        capability_type: str = "all",
        commercial_state: str = "all",
        client_scope: str | None = None,
        reusable_only: bool = False,
        exportable_only: bool = False,
        limit: int = 500,
    ):
        clauses = []
        values: list = []
        query = _text(query)
        if query:
            clauses.append("(name LIKE ? OR description LIKE ? OR tags_json LIKE ?)")
            wildcard = f"%{query}%"
            values.extend([wildcard, wildcard, wildcard])
        if capability_type != "all":
            clauses.append("capability_type=?")
            values.append(capability_type)
        if commercial_state != "all":
            clauses.append("commercial_state=?")
            values.append(commercial_state)
        if client_scope:
            clauses.append("client_scope IN ('shared',?)")
            values.append(client_scope)
        if reusable_only:
            clauses.append("reusable=1")
        if exportable_only:
            clauses.append("exportable=1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(int(limit), 1000)))
        with self.con() as con:
            rows = con.execute(
                f"SELECT * FROM product_capabilities{where} ORDER BY updated_at DESC,name COLLATE NOCASE LIMIT ?",
                values,
            ).fetchall()
        return [self._row(row) for row in rows]

    def update_classification(
        self,
        capability_id: str,
        *,
        commercial_state: str | None = None,
        reusable: bool | None = None,
        exportable: bool | None = None,
        qualification_state: str | None = None,
        client_scope: str | None = None,
    ):
        existing = self.get(capability_id)
        if not existing:
            return None
        values = {}
        if commercial_state is not None:
            if commercial_state not in COMMERCIAL_STATES:
                raise ValueError("Unsupported commercial state")
            values["commercial_state"] = commercial_state
        if qualification_state is not None:
            if qualification_state not in QUALIFICATION_STATES:
                raise ValueError("Unsupported qualification state")
            values["qualification_state"] = qualification_state
        if reusable is not None:
            values["reusable"] = int(bool(reusable))
        if exportable is not None:
            values["exportable"] = int(bool(exportable))
        if client_scope is not None:
            requested_scope = _text(client_scope) or "shared"
            if existing.get("client_scope") != "shared" and requested_scope == "shared":
                raise ValueError(
                    "Client-scoped capabilities can become shared only through explicit generalized product-component promotion"
                )
            values["client_scope"] = requested_scope
        if not values:
            return existing
        values["updated_at"] = _now()
        with self.lock, self.con() as con:
            cur = con.execute(
                "UPDATE product_capabilities SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?",
                (*values.values(), capability_id),
            )
            if not cur.rowcount:
                return None
        return self.get(capability_id)

    def summary(self):
        with self.con() as con:
            total = con.execute("SELECT count(*) c FROM product_capabilities").fetchone()["c"]
            reusable = con.execute("SELECT count(*) c FROM product_capabilities WHERE reusable=1").fetchone()["c"]
            sellable = con.execute(
                "SELECT count(*) c FROM product_capabilities WHERE commercial_state IN ('internal_sellable','commercial','template')"
            ).fetchone()["c"]
            qualified = con.execute("SELECT count(*) c FROM product_capabilities WHERE qualification_state='qualified'").fetchone()["c"]
        return {"total": int(total), "reusable": int(reusable), "sellable": int(sellable), "qualified": int(qualified)}

    def sync_from_runtime(self, runtime: dict, product_store) -> dict:
        """Refresh safe discoverable sources without promoting private data to shared reuse."""
        counts = {
            "agents": 0,
            "tools": 0,
            "automations": 0,
            "workflows": 0,
            "integrations": 0,
            "products": 0,
            "components": 0,
        }

        # The Project/P10 worker registry is Vishnu's qualified internal agent
        # workforce. Profiles are cataloged as reusable design/build capabilities;
        # this records descriptors only and never exports the master Vishnu runtime.
        autonomy = runtime.get("advanced_autonomy")
        worker_registry = getattr(autonomy, "_worker_registry", None) if autonomy is not None else None
        if worker_registry is not None and hasattr(worker_registry, "all"):
            try:
                for profile in worker_registry.all():
                    profile_id = _text(getattr(profile, "id", ""))
                    if not profile_id or profile_id == "tool":
                        continue
                    supported = [
                        _text(item)
                        for item in (getattr(profile, "supported_capabilities", ()) or ())
                        if _text(item)
                    ]
                    description = _text(getattr(profile, "description", "")) or (
                        "Vishnu worker profile for " + ", ".join(supported[:8])
                        if supported else "Vishnu qualified worker profile"
                    )
                    self.upsert(
                        name=_text(getattr(profile, "name", "")) or profile_id.replace("_", " ").title(),
                        capability_type="agent",
                        source_kind="worker_profile",
                        source_ref=profile_id,
                        description=description,
                        commercial_state="internal_reusable",
                        qualification_state="qualified",
                        exportable=True,
                        reusable=True,
                        tags=[profile_id, *supported],
                        metadata={
                            "worker_profile_id": profile_id,
                            "supported_capabilities": supported,
                            "master_runtime_bundled": False,
                        },
                    )
                    counts["agents"] += 1
            except Exception:
                pass

        tools = runtime.get("tools")
        if tools is not None and hasattr(tools, "all"):
            for tool in tools.all():
                prohibited = bool(getattr(tool, "prohibited", False))
                self.upsert(
                    name=getattr(tool, "name", "tool"), capability_type="tool", source_kind="tool",
                    source_ref=getattr(tool, "name", "tool"), description=getattr(tool, "description", ""),
                    commercial_state="internal_reusable", qualification_state="available",
                    exportable=not prohibited, reusable=not prohibited,
                    tags=[str(getattr(tool, "capability", "") or ""), str(getattr(tool, "connector_id", "") or "")],
                    permissions={"risk": getattr(getattr(tool, "risk", None), "name", str(getattr(tool, "risk", "")))},
                    metadata={"verification_required": bool(getattr(tool, "verification_required", False)), "prohibited": prohibited},
                )
                counts["tools"] += 1

        engine = runtime.get("automations")
        if engine is not None:
            try:
                for item in engine.list():
                    self.upsert(
                        name=item.get("title") or "Automation", capability_type="automation", source_kind="automation",
                        source_ref=str(item.get("id")), description=item.get("prompt") or "",
                        commercial_state="internal_reusable", qualification_state="available", metadata={"enabled": bool(item.get("enabled"))},
                    )
                    counts["automations"] += 1
            except Exception:
                pass
            try:
                for item in engine.workflows():
                    self.upsert(
                        name=item.get("title") or "Workflow", capability_type="workflow", source_kind="workflow",
                        source_ref=str(item.get("id")), description="Reusable Vishnu workflow",
                        commercial_state="internal_reusable", qualification_state="available",
                        metadata={"enabled": bool(item.get("enabled")), "paused": bool(item.get("paused")), "step_count": len(item.get("steps") or [])},
                    )
                    counts["workflows"] += 1
            except Exception:
                pass

        integrations = runtime.get("integrations")
        if integrations is not None and hasattr(integrations, "list"):
            try:
                for raw in integrations.list():
                    item = _obj(raw)
                    name = _text(item.get("name") or item.get("provider") or item.get("id"))
                    ref = _text(item.get("id") or item.get("provider") or name)
                    if not name or not ref:
                        continue
                    self.upsert(
                        name=name, capability_type="integration", source_kind="integration", source_ref=ref,
                        description=_text(item.get("description")), commercial_state="internal_reusable",
                        qualification_state="available", metadata={key: value for key, value in item.items() if key not in {"token", "secret", "api_key", "password"}},
                    )
                    counts["integrations"] += 1
            except Exception:
                pass

        for product in product_store.list():
            client = _text(product.get("client_name"))
            scope = client or "shared"
            product_state = "client_specific" if client else "internal_sellable"
            self.upsert(
                name=product.get("name") or "Product", capability_type="product_template", source_kind="product",
                source_ref=product["id"], description=product.get("description") or "",
                client_scope=scope, commercial_state=product_state,
                qualification_state="qualified" if product.get("status") in {"qualified", "released", "live"} else "available",
                exportable=True, reusable=True, ai_required=product.get("ai_mode") != "disabled",
                ai_modes=[product.get("ai_mode")],
                platforms=[row["target"] for row in product.get("targets") or [] if row.get("enabled")],
                tags=[product.get("product_type") or "custom", client],
                metadata={"product_status": product.get("status"), "version": product.get("version")},
            )
            counts["products"] += 1
            for component in product_store.components(product["id"]):
                source_ref = _text(component.get("component_ref")) or component["id"]
                self.upsert(
                    name=component.get("name") or "Component", capability_type=_text(component.get("component_type")) or "custom",
                    source_kind="product_component", source_ref=f"{product['id']}:{source_ref}",
                    description=f"Reusable component from {product.get('name')}", client_scope=scope,
                    commercial_state="client_specific" if client else "internal_reusable",
                    qualification_state="qualified" if product.get("status") in {"qualified", "released", "live"} else "available",
                    metadata={"product_id": product["id"], "component_id": component["id"], "component_ref": component.get("component_ref")},
                )
                counts["components"] += 1
        return counts
