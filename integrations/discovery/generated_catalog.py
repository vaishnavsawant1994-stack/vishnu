from __future__ import annotations

import json
import sqlite3
from typing import Any


def register_generated_capability(catalog, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a generated capability in the existing Universal Capability Catalog."""
    if not isinstance(payload, dict):
        raise TypeError("generated capability payload must be an object")
    capability_id = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not capability_id or len(capability_id) > 200 or not name:
        raise ValueError("generated capability id and name are required")
    if payload.get("type") != "generated_capability" or payload.get("category") != "Generated":
        raise ValueError("invalid generated capability catalog type")
    if payload.get("state") not in {"active", "disabled"}:
        raise ValueError("generated capability state must be active or disabled")
    if not getattr(catalog, "path", None):
        raise RuntimeError("capability catalog path is unavailable")
    with sqlite3.connect(catalog.path) as db:
        db.execute(
            "INSERT OR REPLACE INTO capability_catalog(id,category,name,payload) VALUES(?,?,?,?)",
            (capability_id, "Generated", name[:200], json.dumps(payload, sort_keys=True)),
        )
    return payload


def set_generated_capability_state(catalog, capability_id: str, state: str) -> dict[str, Any]:
    if state not in {"active", "disabled"}:
        raise ValueError("generated capability state must be active or disabled")
    current = catalog.get(str(capability_id))
    if current is None or current.get("type") != "generated_capability":
        raise KeyError(capability_id)
    updated = {**current, "state": state}
    return register_generated_capability(catalog, updated)


def generated_capabilities(catalog, *, state: str | None = None) -> list[dict[str, Any]]:
    rows = [
        item for item in catalog.all()
        if isinstance(item, dict) and item.get("type") == "generated_capability"
    ]
    if state is not None:
        rows = [item for item in rows if item.get("state") == state]
    return rows
