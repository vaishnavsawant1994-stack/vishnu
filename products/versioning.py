from __future__ import annotations

import json


def frozen_version(store, product_id: str, version: str) -> dict | None:
    """Return an immutable product-version snapshot from the authoritative product DB."""
    with store.con() as con:
        row = con.execute(
            "SELECT id,product_id,version,manifest_json,notes,created_at FROM product_versions WHERE product_id=? AND version=? LIMIT 1",
            (product_id, version),
        ).fetchone()
    if not row:
        return None
    value = dict(row)
    value["manifest"] = json.loads(value.pop("manifest_json"))
    return value


def list_frozen_versions(store, product_id: str, *, limit: int = 100) -> list[dict]:
    with store.con() as con:
        rows = con.execute(
            "SELECT id,product_id,version,manifest_json,notes,created_at FROM product_versions WHERE product_id=? ORDER BY created_at DESC LIMIT ?",
            (product_id, max(1, min(int(limit), 500))),
        ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        value["manifest"] = json.loads(value.pop("manifest_json"))
        result.append(value)
    return result
