#!/usr/bin/env python3
"""Validate the stable fields in docs/audit/product_truth.json."""

import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "docs/audit/product_truth.json"
data = json.loads(path.read_text())
rows = data["features"]
allowed = {"COMPLETE", "PARTIAL", "INTERNAL", "EXPERIMENTAL", "BLOCKED", "MISSING", "LEGACY"}
required = {
    "id",
    "domain",
    "name",
    "backend",
    "api",
    "storage",
    "security",
    "desktop_ui",
    "pwa_ui",
    "android_ui",
    "ios_ui",
    "navigation",
    "e2e",
    "tests",
    "status",
    "blockers",
    "evidence",
    "gap",
}
errors = []
ids = [row.get("id") for row in rows]
if len(ids) != len(set(ids)):
    errors.append("feature IDs must be unique")
for row in rows:
    missing = sorted(required - row.keys())
    if missing:
        errors.append(f"{row.get('id')}: missing fields {missing}")
    blanks = [k for k in required if k in row and row[k] in (None, "", []) and k not in {"blockers", "evidence"}]
    if blanks:
        errors.append(f"{row.get('id')}: blank fields {sorted(blanks)}")
    if row.get("status") not in allowed:
        errors.append(f"{row.get('id')}: invalid status")
    if row.get("status") == "COMPLETE" and not row.get("evidence"):
        errors.append(f"{row.get('id')}: COMPLETE needs evidence")
    if row.get("status") == "BLOCKED" and not row.get("blockers"):
        errors.append(f"{row.get('id')}: BLOCKED needs a reason")
    if row.get("status") == "INTERNAL" and not row.get("justification"):
        errors.append(f"{row.get('id')}: INTERNAL needs justification")
    if row.get("status") == "MISSING" and not row.get("gap"):
        errors.append(f"{row.get('id')}: MISSING needs an action")
if errors:
    raise SystemExit("\n".join(errors))
counts = {s: sum(row["status"] == s for row in rows) for s in sorted(allowed)}
print(json.dumps({"features": len(rows), "status_counts": counts, "validation": "passed"}, indent=2))
