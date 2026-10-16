from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "ui" / "ui_truth.json"
PAGE_SPEC = ROOT / "docs" / "ui" / "PAGE_SPECIFICATIONS.md"
ALLOWED_STATUS = {"complete", "partial", "experimental", "blocked", "missing", "orphaned", "disconnected", "placeholder", "internal"}
ALLOWED_PLATFORM = {"complete", "partial", "experimental", "blocked", "missing", "not_verified", "n/a"}
REQUIRED_FIELDS = {
    "id", "name", "domain", "required", "exists", "reachable", "backend_connected",
    "desktop", "pwa", "android", "ios", "visual_verified", "a11y_verified",
    "status", "priority",
}
CANONICAL_IDS = (
    "ONB-001","ONB-002","ONB-003","ONB-004","ONB-005","ONB-006","ONB-007","ONB-008",
    "AUTH-001","AUTH-002","AUTH-003","HOME-001","CHAT-001","CHAT-002","MEM-001","MEM-002",
    "KNW-001","KNW-002","ACT-001","ATT-001","ACT-002","WRK-001","WRK-002","WRK-003",
    "AUT-001","AUT-002","PRJ-001","PRJ-002","PRD-001","PRD-002","APP-001","APP-002",
    "CAP-001","CAP-002","CAP-003","DEV-001","DEV-002","DAT-001","DAT-002","MOD-001","MOD-002",
    "VOC-001","VOC-002","VOC-003","SEN-001","SEN-002","CTL-001","SEC-001","SEC-002","SEC-003",
    "APR-001","PRI-001","REC-001","NOT-001","SYS-001","SYS-002","SYS-003","SYS-004",
    "SET-001","SET-002","SET-003","SET-004","SET-005",
)


def main() -> int:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    screens = data.get("screens")
    if not isinstance(screens, list) or not screens:
        raise SystemExit("ui_truth.json must contain a non-empty screens list")

    ids: list[str] = []
    for index, screen in enumerate(screens):
        if not isinstance(screen, dict):
            raise SystemExit(f"screen {index} is not an object")
        missing = REQUIRED_FIELDS - set(screen)
        if missing:
            raise SystemExit(f"{screen.get('id', index)} missing fields: {sorted(missing)}")
        blank = [key for key in REQUIRED_FIELDS if screen[key] is None or screen[key] == ""]
        if blank:
            raise SystemExit(f"{screen['id']} contains blank required fields: {blank}")
        if screen["status"] not in ALLOWED_STATUS:
            raise SystemExit(f"{screen['id']} has invalid status {screen['status']!r}")
        for platform in ("desktop", "pwa", "android", "ios"):
            if screen[platform] not in ALLOWED_PLATFORM:
                raise SystemExit(f"{screen['id']} has invalid {platform} status {screen[platform]!r}")
        if screen["status"] == "missing" and screen["exists"]:
            raise SystemExit(f"{screen['id']} is missing but exists=true")
        if screen["status"] != "missing" and screen["required"] and not screen["exists"]:
            raise SystemExit(f"{screen['id']} is required/non-missing but exists=false")
        if screen["status"] == "complete" and not screen["visual_verified"]:
            raise SystemExit(f"{screen['id']} COMPLETE requires visual evidence")
        ids.append(screen["id"])

    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise SystemExit(f"duplicate screen IDs: {duplicates}")
    if tuple(ids) != CANONICAL_IDS:
        missing_ids = [item for item in CANONICAL_IDS if item not in ids]
        unexpected = [item for item in ids if item not in CANONICAL_IDS]
        raise SystemExit(f"canonical IDs drifted; missing={missing_ids}, unexpected={unexpected}, order_matches={tuple(ids) == CANONICAL_IDS}")

    page_spec_text = PAGE_SPEC.read_text(encoding="utf-8")
    specified = set(re.findall(r"^###\s+([A-Z]{3,4}-\d{3})\s+—", page_spec_text, flags=re.MULTILINE))
    absent_from_specs = [item for item in CANONICAL_IDS if item not in specified]
    if absent_from_specs:
        raise SystemExit(f"PAGE_SPECIFICATIONS.md missing canonical IDs: {absent_from_specs}")

    summary = data.get("summary") or {}
    expected = {
        "canonical_required": 63,
        "implemented_canonical": sum(bool(item["exists"]) for item in screens),
        "complete": sum(item["status"] == "complete" for item in screens),
        "partial": sum(item["status"] == "partial" for item in screens),
        "experimental": sum(item["status"] == "experimental" for item in screens),
        "missing": sum(item["status"] == "missing" for item in screens),
        "visual_verified": sum(bool(item["visual_verified"]) for item in screens),
        "platform_slots_classified": 252,
        "source_proven_platform_instances": sum(
            item[platform] in {"complete", "partial", "experimental", "blocked"}
            for item in screens for platform in ("desktop", "pwa", "android", "ios")
        ),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise SystemExit(f"summary.{key}={summary.get(key)!r}, expected {value!r}")

    print(
        f"UI truth valid: 63 canonical screens; exact ID set and page specifications covered; "
        f"{expected['source_proven_platform_instances']} source-proven platform implementations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
