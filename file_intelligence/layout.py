from __future__ import annotations

import re
from copy import deepcopy
from typing import Iterable

from .models import SourceReference, VishnuBlock
from .visual import infer_spatial_layout

_KEY_VALUE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _./()#-]{0,80})\s*[:=]\s*(\S.+?)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•‣◦]|\d+[.)])\s+(.+)$")
_CHECKBOX = re.compile(r"^\s*(?:\[(?P<mark>[ xX✓✔])\]|☐|☑|☒)\s*(?P<label>.+?)\s*$")
_HEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+){0,4}|[A-Z])(?:[.)]|\s)\s*\S")


def _copy_source(source: SourceReference, **changes) -> SourceReference:
    values = source.compact()
    values.update({key: value for key, value in changes.items() if value is not None})
    return SourceReference(**values)


def _looks_like_heading(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean or "\n" in clean or len(clean) > 140:
        return False
    if _HEADING_NUMBER.match(clean):
        return True
    return clean.isupper() and 1 <= len(clean.split()) <= 12 and len(clean) <= 120


def _normalized_table(block: VishnuBlock) -> None:
    rows = []
    if isinstance(block.data, dict) and isinstance(block.data.get("rows"), list):
        rows = block.data["rows"]
    if not rows:
        return
    width = max((len(row) for row in rows if isinstance(row, list)), default=0)
    normalized = []
    for row in rows:
        values = list(row) if isinstance(row, list) else [row]
        normalized.append(values + [None] * (width - len(values)))
    headers = [str(value or "").strip() for value in normalized[0]] if normalized else []
    has_header = bool(headers) and any(headers) and len(normalized) > 1
    block.data = {
        **(block.data if isinstance(block.data, dict) else {}),
        "rows": normalized,
        "columns": headers if has_header else [f"column_{index + 1}" for index in range(width)],
        "row_count": len(normalized),
        "column_count": width,
        "has_header": has_header,
    }
    block.metadata = {**block.metadata, "layout": "table"}


def _line_blocks(block: VishnuBlock) -> list[VishnuBlock]:
    lines = [line.strip() for line in block.text.splitlines() if line.strip()]
    if not lines:
        return []
    derived: list[VishnuBlock] = []
    for offset, line in enumerate(lines):
        source = _copy_source(
            block.source,
            line_start=(block.source.line_start + offset if block.source.line_start else None),
            line_end=(block.source.line_start + offset if block.source.line_start else None),
        )
        checkbox = _CHECKBOX.match(line)
        if checkbox:
            mark = checkbox.groupdict().get("mark") or ""
            derived.append(VishnuBlock(
                "form_field",
                checkbox.group("label"),
                source,
                block.extraction_method,
                block.confidence,
                data={"field_type": "checkbox", "checked": mark.strip().lower() in {"x", "✓", "✔"}},
                metadata={"derived": True},
            ))
            continue
        kv = _KEY_VALUE.match(line)
        if kv:
            key, value = kv.group(1).strip(), kv.group(2).strip()
            derived.append(VishnuBlock(
                "key_value",
                f"{key}: {value}",
                _copy_source(source, field=key),
                block.extraction_method,
                block.confidence,
                data={"key": key, "value": value},
                metadata={"derived": True},
            ))
            continue
        bullet = _BULLET.match(line)
        if bullet:
            derived.append(VishnuBlock(
                "list_item",
                bullet.group(1).strip(),
                source,
                block.extraction_method,
                block.confidence,
                metadata={"derived": True},
            ))
            continue
        if _looks_like_heading(line):
            derived.append(VishnuBlock(
                "heading",
                line,
                source,
                block.extraction_method,
                block.confidence,
                metadata={"derived": True, "layout": "heading", "inferred": True},
            ))
    return derived


def _table_key_values(block: VishnuBlock) -> list[VishnuBlock]:
    if block.kind != "table" or not isinstance(block.data, dict):
        return []
    rows = block.data.get("rows")
    if not isinstance(rows, list):
        return []
    derived: list[VishnuBlock] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != 2:
            continue
        key = str(row[0] or "").strip()
        value = str(row[1] or "").strip()
        if not key or not value or len(key) > 80:
            continue
        derived.append(VishnuBlock(
            "key_value",
            f"{key}: {value}",
            _copy_source(block.source, field=key),
            block.extraction_method,
            block.confidence,
            data={"key": key, "value": value, "table_row": row_index},
            metadata={"derived": True, "from_table": True},
        ))
    return derived


def enrich_layout(blocks: Iterable[VishnuBlock]) -> list[VishnuBlock]:
    """Deterministically enrich parser/OCR blocks without using a remote model."""
    enriched: list[VishnuBlock] = []
    for original in blocks:
        block = deepcopy(original)
        text = block.text.strip()
        if block.kind == "table":
            _normalized_table(block)
        elif block.kind in {"text", "paragraph"} and text:
            if _looks_like_heading(text):
                block.kind = "heading"
                block.metadata = {**block.metadata, "layout": "heading", "inferred": True}
            else:
                block.metadata = {**block.metadata, "layout": block.kind}
        enriched.append(block)
        enriched.extend(_line_blocks(block))
        enriched.extend(_table_key_values(block))
    return infer_spatial_layout(enriched)
