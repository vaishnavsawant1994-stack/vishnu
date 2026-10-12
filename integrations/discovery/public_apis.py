"""Deterministic, offline parser for the public-apis Markdown catalog.

This module does not fetch URLs, load provider code, or register executable tools.
It intentionally preserves the difference between discovery and authorization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import html
import re
from urllib.parse import urlsplit

SOURCE = "https://github.com/public-apis/public-apis"
_HEADER = re.compile(r"^### ([^#].*?)\\s*$")
_ROW = re.compile(r"^\\|(.+)\\|\\s*$")
_LINK = re.compile(r"^\\[([^]]+)\\]\\((https?://[^)]+)\\)$")


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    name: str
    description: str
    category: str
    documentation_url: str
    auth: str
    https: bool | None
    cors: str
    source: str = SOURCE
    lifecycle: str = "discovered"
    executable: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _cells(line: str) -> list[str]:
    if not _ROW.match(line):
        return []
    return [html.unescape(cell.strip()) for cell in line.strip().strip("|").split("|")]


def _safe_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False


def parse_public_apis_category(text: str, *, max_entries: int = 10000) -> list[CatalogEntry]:
    """Parse standard public-apis README category tables without network access.

    Only HTTPS documentation links are admitted to the discovery catalog.
    Entries remain inert metadata; importing them does not grant any capability.
    """
    if not isinstance(text, str) or len(text) > 5_000_000:
        raise ValueError("catalog input exceeds supported size")
    if not 1 <= max_entries <= 100000:
        raise ValueError("invalid catalog entry limit")
    category = ""
    result: list[CatalogEntry] = []
    seen: set[str] = set()
    for line in text.splitlines():
        header = _HEADER.match(line)
        if header:
            category = header.group(1).strip()[:120]
            continue
        cells = _cells(line)
        if not category or len(cells) != 5 or cells[0].lower() in {"api", ":---", "---"} or cells[0].startswith("---"):
            continue
        match = _LINK.match(cells[0])
        if not match:
            continue
        name, url = match.groups()
        if not _safe_url(url):
            continue
        name = name.strip()[:200]
        if not name:
            continue
        identity = hashlib.sha256((category.casefold() + "\\n" + url).encode("utf-8")).hexdigest()[:24]
        if identity in seen:
            continue
        seen.add(identity)
        https = {"yes": True, "no": False}.get(cells[3].strip().lower())
        result.append(CatalogEntry(
            id="public_apis:" + identity,
            name=name,
            description=cells[1].strip()[:1000],
            category=category,
            documentation_url=url,
            auth=cells[2].strip()[:120],
            https=https,
            cors=cells[4].strip()[:40],
        ))
        if len(result) >= max_entries:
            break
    return result


def parse_public_apis(text: str, *, max_entries: int = 10000) -> list[dict]:
    """Return JSON-compatible, stable, non-executable catalog records."""
    return [entry.as_dict() for entry in parse_public_apis_category(text, max_entries=max_entries)]
