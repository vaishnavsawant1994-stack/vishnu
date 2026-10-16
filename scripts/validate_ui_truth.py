#!/usr/bin/env python3
"""Validate the canonical UI truth inventory without external dependencies."""
import json
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "docs/ui/ui_truth.json"
REQUIRED = {
    "id", "name", "domain", "purpose", "user_question", "required", "exists",
    "reachable", "backend_connected", "navigation", "content", "actions", "data",
    "backend", "security", "platforms", "states", "responsive", "accessibility",
    "tests", "evidence", "status", "missing", "visual_spec", "acceptance_criteria",
    "visual_verified", "a11y_verified", "visual_evidence_status", "a11y_evidence_status",
    "visual_capture_files", "visual_views_manually_inspected",
}


def main() -> None:
    data = json.loads(PATH.read_text())
    entries = data["screens"]
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids)), "duplicate screen IDs"
    for entry in entries:
        missing = REQUIRED - entry.keys()
        assert not missing, f"{entry.get('id')}: missing fields {sorted(missing)}"
        for key in REQUIRED - {"required", "exists", "reachable", "backend_connected", "visual_capture_files"}:
            value = entry[key]
            assert value not in (None, "", [], {}), f"{entry['id']}: blank {key}"
        if entry["status"] == "complete":
            assert entry["evidence"], f"{entry['id']}: complete status needs evidence"
        if entry["status"] == "blocked":
            assert any("block" in item.lower() for item in entry["missing"]), f"{entry['id']}: blocked without reason"
        if entry["status"] == "internal":
            assert entry["purpose"], f"{entry['id']}: internal justification required"
        if entry["status"] == "missing":
            assert entry["missing"], f"{entry['id']}: missing screen needs action item"
    print(f"validated {len(entries)} UI screen records; unique IDs and required fields present")


if __name__ == "__main__":
    main()
