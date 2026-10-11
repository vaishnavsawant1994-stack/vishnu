from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"

class ContentKind(str, Enum):
    PDF = "pdf"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    IMAGE = "image"
    TEXT = "text"
    STRUCTURED = "structured"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"

class ExtractionMethod(str, Enum):
    NATIVE = "native"
    OCR = "ocr"
    HYBRID = "hybrid"

@dataclass(slots=True)
class SourceReference:
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell: str | None = None
    cell_range: str | None = None
    paragraph: int | None = None
    table: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    bbox: list[float] | None = None
    image: str | None = None

    def compact(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

@dataclass(slots=True)
class VishnuBlock:
    kind: str
    text: str = ""
    source: SourceReference = field(default_factory=SourceReference)
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE
    confidence: float | None = None
    data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source"] = self.source.compact()
        value["extraction_method"] = self.extraction_method.value
        if self.confidence is None:
            value.pop("confidence")
        if self.data is None:
            value.pop("data")
        if not self.metadata:
            value.pop("metadata")
        return value

@dataclass(slots=True)
class VishnuDocument:
    document_id: str
    filename: str
    content_kind: ContentKind
    detected_mime: str
    declared_mime: str
    extension: str
    sha256: str
    size_bytes: int
    blocks: list[VishnuBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    parser_version: str = "vishnu-file-intelligence/1"
    ocr_version: str | None = None
    layout_version: str = "vishnu-layout/1"
    schema_version: str = SCHEMA_VERSION

    @property
    def full_text(self) -> str:
        return "\n\n".join(block.text.strip() for block in self.blocks if block.text.strip()).strip()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "filename": self.filename,
            "content_kind": self.content_kind.value,
            "detected_mime": self.detected_mime,
            "declared_mime": self.declared_mime,
            "extension": self.extension,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "parser_version": self.parser_version,
            "ocr_version": self.ocr_version,
            "layout_version": self.layout_version,
            "blocks": [block.as_dict() for block in self.blocks],
            "full_text": self.full_text,
        }
