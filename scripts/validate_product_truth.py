#!/usr/bin/env python3
"""CI-safe validator for the canonical Vishnu product-truth map."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = {
    "id", "domain", "name", "backend", "api", "storage", "security",
    "desktop", "pwa", "android", "ios", "navigation", "e2e", "tests",
    "status", "gap", "evidence",
}
STATUSES = {
    "complete", "partial", "internal", "experimental", "blocked",
    "missing_broken", "legacy", "not_verified",
}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read valid JSON: {exc}"]
    features = data.get("features")
    if not isinstance(features, list) or not features:
        return ["features must be a non-empty list"]
    seen: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            errors.append(f"feature[{index}] must be an object")
            continue
        missing = REQUIRED - set(feature)
        if missing:
            errors.append(f"feature[{index}] missing fields: {sorted(missing)}")
            continue
        fid = feature["id"]
        if not isinstance(fid, str) or not fid.strip():
            errors.append(f"feature[{index}] has blank id")
        elif fid in seen:
            errors.append(f"duplicate feature id: {fid}")
        else:
            seen.add(fid)
        for field in REQUIRED - {"evidence"}:
            value = feature[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{fid or index}: blank {field}")
        status = feature["status"]
        if status not in STATUSES:
            errors.append(f"{fid}: invalid status {status!r}")
        evidence = feature["evidence"]
        if not isinstance(evidence, list):
            errors.append(f"{fid}: evidence must be a list")
        elif status == "complete" and not evidence:
            errors.append(f"{fid}: complete feature requires evidence")
        if status == "blocked" and feature["gap"] in {"N/A", "None", ""}:
            errors.append(f"{fid}: blocked feature requires blocker/gap")
        if status == "internal" and feature["navigation"] == "No":
            errors.append(f"{fid}: internal feature needs an intentional exposure classification, not bare No")
        if status == "missing_broken" and feature["gap"] in {"N/A", "None", ""}:
            errors.append(f"{fid}: missing/broken feature requires an action/gap")
    return errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/audit/product_truth.json")
    errors = validate(path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {path} product-truth map is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
