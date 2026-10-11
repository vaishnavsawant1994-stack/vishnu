from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from .detection import Detection, detect_content
from .models import ContentKind, VishnuDocument
from .ocr import OcrUnavailable
from .readers import ContentReadError, read_csv, read_docx, read_html, read_image, read_json, read_jsonl, read_pdf, read_pptx, read_text, read_xlsx, read_xml

class UnsupportedContentError(ContentReadError):
    pass

class FileIntelligenceEngine:
    """Deterministic, local-first content extraction for Vishnu; no network calls."""
    MAX_FILE_BYTES = 50 * 1024 * 1024

    def __init__(self, *, ocr_provider=None, max_file_bytes: int | None = None, allow_external_ocr: bool = False):
        if ocr_provider is not None and bool(getattr(ocr_provider, "external", False)) and not allow_external_ocr:
            raise OcrUnavailable("External OCR is disabled by default; configure it explicitly if policy permits")
        self.ocr_provider = ocr_provider
        self.max_file_bytes = int(max_file_bytes or self.MAX_FILE_BYTES)
        self.allow_external_ocr = bool(allow_external_ocr)

    def extract(self, *, filename: str, data: bytes, declared_mime: str = "application/octet-stream") -> VishnuDocument:
        safe_name = Path(str(filename or "")).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ContentReadError("A safe filename is required")
        if not data:
            raise ContentReadError("File is empty")
        if len(data) > self.max_file_bytes:
            raise ContentReadError("File exceeds the configured size limit")
        detection = detect_content(safe_name, data, declared_mime)
        document = VishnuDocument(document_id=str(uuid.uuid4()), filename=safe_name, content_kind=detection.kind, detected_mime=detection.mime, declared_mime=declared_mime or "application/octet-stream", extension=detection.extension, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
        blocks, warnings, ocr_version = self._read(detection, safe_name, data)
        document.blocks = blocks
        document.warnings.extend(warnings)
        document.ocr_version = ocr_version
        if not document.blocks:
            raise ContentReadError("No readable content was found")
        return document

    def _read(self, detection: Detection, filename: str, data: bytes):
        suffix = detection.extension.lower()
        if detection.kind == ContentKind.PDF:
            blocks, warnings, ocr_version = read_pdf(data, filename, self.ocr_provider)
            return blocks, warnings, ocr_version
        if detection.kind == ContentKind.IMAGE:
            blocks, ocr_version = read_image(data, filename, self.ocr_provider)
            return blocks, [], ocr_version
        if suffix == ".docx": return read_docx(data), [], None
        if suffix == ".xlsx": return read_xlsx(data), [], None
        if suffix == ".pptx": return read_pptx(data), [], None
        if suffix == ".json": return read_json(data), [], None
        if suffix == ".jsonl": return read_jsonl(data), [], None
        if suffix == ".csv": return read_csv(data), [], None
        if suffix == ".xml": return read_xml(data), [], None
        if suffix in {".html", ".htm"}: return read_html(data), [], None
        if detection.kind == ContentKind.TEXT: return read_text(data), [], None
        raise UnsupportedContentError(f"Unsupported file type: {suffix or detection.mime or 'unknown'}")
