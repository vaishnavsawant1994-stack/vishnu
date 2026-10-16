from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "ui" / "ui_truth.json"
ALLOWED_STATUS = {"complete", "partial", "experimental", "blocked", "missing", "orphaned", "disconnected", "placeholder", "internal"}
ALLOWED_PLATFORM = {"complete", "partial", "experimental", "blocked", "missing", "not_verified", "n/a"}
REQUIRED_FIELDS = {
    "id", "name", "domain", "required", "exists", "reachable", "backend_connected",
    "desktop", "pwa", "android", "ios", "visual_verified", "a11y_verified",
    "status", "priority",
}


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

    summary = data.get("summary") or {}
    expected = {
        "canonical_required": len(screens),
        "implemented_canonical": sum(bool(item["exists"]) for item in screens),
        "complete": sum(item["status"] == "complete" for item in screens),
        "partial": sum(item["status"] == "partial" for item in screens),
        "experimental": sum(item["status"] == "experimental" for item in screens),
        "missing": sum(item["status"] == "missing" for item in screens),
        "visual_verified": sum(bool(item["visual_verified"]) for item in screens),
        "platform_slots_classified": len(screens) * 4,
        "source_proven_platform_instances": sum(
            item[platform] in {"complete", "partial", "experimental", "blocked"}
            for item in screens for platform in ("desktop", "pwa", "android", "ios")
        ),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise SystemExit(f"summary.{key}={summary.get(key)!r}, expected {value!r}")

    print(f"UI truth valid: {len(screens)} canonical screens; {expected['source_proven_platform_instances']} source-proven platform implementations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
