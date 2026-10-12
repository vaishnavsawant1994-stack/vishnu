from __future__ import annotations

from pathlib import Path

from file_intelligence import FileIntelligenceEngine, LocalContentIndex, OcrUnavailable, TesseractOcrProvider
from file_intelligence.models import ExtractionMethod, SourceReference, VishnuBlock
from file_intelligence.readers import ContentReadError, sanitize_image
from knowledge.store import KnowledgeError, KnowledgeOcrUnavailable, KnowledgeStore as LegacyKnowledgeStore


class UniversalKnowledgeStore(LegacyKnowledgeStore):
    """KnowledgeStore compatibility layer backed by Vishnu File Intelligence."""

    MAX_FILE_BYTES = FileIntelligenceEngine.MAX_FILE_BYTES

    def __init__(self, path, object_dir, *, ocr_provider=None, allow_external_private_ocr: bool = False):
        # Default to Vishnu's local OCR adapter. Construction is safe even when the
        # system tesseract executable is absent; an OCR attempt then fails closed.
        if ocr_provider is None:
            ocr_provider = TesseractOcrProvider()
        super().__init__(
            path,
            object_dir,
            ocr_provider=ocr_provider,
            allow_external_private_ocr=allow_external_private_ocr,
        )

    def _init(self):
        super()._init()
        self.content_index = LocalContentIndex(self.path)

    def _segments_for(self, filename: str, data: bytes, access_class: str):
        provider = self.ocr_provider
        if provider is not None and access_class == "private" and bool(getattr(provider, "external", False)) and not self.allow_external_private_ocr:
            raise KnowledgeOcrUnavailable("OCR unavailable: private content cannot be sent to the configured external OCR provider")
        try:
            engine = FileIntelligenceEngine(
                ocr_provider=provider,
                max_file_bytes=self.MAX_FILE_BYTES,
                allow_external_ocr=(not bool(getattr(provider, "external", False))) or access_class != "private" or self.allow_external_private_ocr,
            )
            document = engine.extract(filename=filename, data=data)
        except OcrUnavailable as exc:
            raise KnowledgeOcrUnavailable(str(exc)) from exc
        except ContentReadError as exc:
            raise KnowledgeError(str(exc)) from exc
        segments = []
        for block in document.blocks:
            location = block.source.compact()
            location["kind"] = block.kind
            location["extraction_method"] = block.extraction_method.value
            if block.confidence is not None:
                location["confidence"] = block.confidence
            if block.data is not None:
                location["structured"] = True
            segments.append({"text": block.text, "page": block.source.page, "location": location})
        stored_data = data
        stored_suffix = document.extension or Path(filename).suffix.lower()
        if document.content_kind.value == "image":
            stored_data = sanitize_image(data)
            stored_suffix = ".png"
        return segments, stored_data, stored_suffix

    @staticmethod
    def _block_from_chunk(chunk: dict) -> VishnuBlock:
        location = dict(chunk.get("location") or {})
        kind = str(location.pop("kind", "text"))
        method_name = str(location.pop("extraction_method", "native"))
        confidence = location.pop("confidence", None)
        allowed = SourceReference.__dataclass_fields__.keys()
        source = SourceReference(**{key: value for key, value in location.items() if key in allowed})
        try:
            method = ExtractionMethod(method_name)
        except ValueError:
            method = ExtractionMethod.NATIVE
        return VishnuBlock(kind, str(chunk.get("content") or ""), source, method, confidence)

    def _index_detail(self, detail: dict) -> None:
        chunks = detail.get("chunks") or []
        blocks = [self._block_from_chunk(chunk) for chunk in chunks if str(chunk.get("content") or "").strip()]
        self.content_index.index_blocks(
            document_id=detail["id"],
            checksum=detail["checksum"],
            title=detail["title"],
            blocks=blocks,
            scope_type="knowledge",
            scope_id=detail["access_class"],
            metadata={
                "lineage_id": detail.get("lineage_id"),
                "version": detail.get("version"),
                "filename": detail.get("filename"),
                "source": detail.get("source"),
                "access_class": detail.get("access_class"),
            },
        )

    def ingest(self, **kwargs):
        detail = super().ingest(**kwargs)
        if detail:
            self._index_detail(detail)
        return detail

    def ensure_exact_index(self, *, access_classes: set[str] | None = None) -> int:
        indexed = 0
        for item in self.list(limit=500, access_classes=access_classes):
            state = self.content_index.state(
                document_id=item["id"],
                scope_type="knowledge",
                scope_id=item["access_class"],
            )
            if state and state["checksum"] == item["checksum"]:
                continue
            detail = self.detail(item["id"])
            if detail:
                self._index_detail(detail)
                indexed += 1
        return indexed

    def search_exact(self, query: str, limit: int = 20, *, access_classes: set[str] | None = None) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        results = []
        for access_class in sorted(classes):
            hits = self.content_index.search(
                query,
                scope_type="knowledge",
                scope_id=access_class,
                limit=max(limit, 20),
            )
            for hit in hits:
                detail = self.detail(hit["document_id"], include_history=False)
                if not detail or not detail.get("current"):
                    continue
                metadata = detail.get("metadata") or {}
                if not bool(metadata.get("available_to_vishnu", True)):
                    continue
                hit["citation"].update(
                    {
                        "lineage_id": detail.get("lineage_id"),
                        "version": detail.get("version"),
                        "checksum": detail.get("checksum"),
                        "source_name": detail.get("source"),
                    }
                )
                results.append(hit)
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: max(1, min(int(limit), 100))]
