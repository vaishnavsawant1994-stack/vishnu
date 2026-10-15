from __future__ import annotations

import re
import time
from typing import Any


_SERIAL_RE = re.compile(r"\b(?:S/N|SN|SERIAL|IMEI|MODEL|PART)[:#\s-]*([A-Z0-9][A-Z0-9._/-]{3,63})\b", re.IGNORECASE)


class DocumentIntelligence:
    """Normalizes on-device OCR/barcode/document extraction before model use."""

    def __init__(self, *, events=None) -> None:
        self.events = events

    @staticmethod
    def _text(value: str | None) -> str:
        return str(value or "")[:100_000]

    def ingest(
        self,
        *,
        source: str,
        text: str | None = None,
        barcodes: list[dict[str, Any]] | None = None,
        fields: dict[str, Any] | None = None,
        handwriting: bool = False,
        confidence: float = 0.8,
        captured_at: float | None = None,
    ) -> dict:
        clean_text = self._text(text)
        codes: list[dict[str, str]] = []
        for item in (barcodes or [])[:64]:
            raw = str(item.get("value") or item.get("raw_value") or "")[:4096]
            if not raw:
                continue
            codes.append({
                "format": str(item.get("format") or "unknown")[:80],
                "value": raw,
            })
        safe_fields: dict[str, Any] = {}
        for key, value in list((fields or {}).items())[:128]:
            name = str(key)[:120]
            if isinstance(value, str):
                safe_fields[name] = value[:4096]
            elif isinstance(value, (int, float, bool)) or value is None:
                safe_fields[name] = value
        serials = sorted({match.group(1) for match in _SERIAL_RE.finditer(clean_text)})[:64]
        result = {
            "source": str(source or "document")[:160],
            "text": clean_text,
            "barcodes": codes,
            "fields": safe_fields,
            "serial_candidates": serials,
            "handwriting": bool(handwriting),
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "captured_at": float(captured_at or time.time()),
            "local_extraction": True,
            "raw_image_retained": False,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        if self.events is not None:
            self.events.emit(
                "sensorium.document.extracted",
                source=result["source"],
                text_characters=len(clean_text),
                barcodes=len(codes),
                serial_candidates=len(serials),
                execution_authority=False,
            )
        return result
