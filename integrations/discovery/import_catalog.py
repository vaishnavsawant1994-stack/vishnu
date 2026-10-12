"""Offline catalog ingestion command.

Usage: python -m integrations.discovery.import_catalog path/to/README.md --db data/capability-catalog.sqlite3
The operator supplies a reviewed local snapshot. No remote fetching or API execution occurs.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from integrations.discovery.catalog_store import CapabilityCatalogStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a local public-apis Markdown snapshot")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.snapshot.is_file() or args.snapshot.stat().st_size > 5_000_000:
        parser.error("Snapshot must be a file of at most 5 MB")
    markdown = args.snapshot.read_text(encoding="utf-8")
    count = CapabilityCatalogStore(args.db).import_markdown(markdown)
    print(f"Imported {count} inert catalog entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
