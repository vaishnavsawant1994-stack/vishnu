from __future__ import annotations

from pathlib import Path

from file_intelligence import FileIntelligenceEngine, OcrUnavailable
from file_intelligence.readers import ContentReadError, sanitize_image
from knowledge.store import KnowledgeError, KnowledgeOcrUnavailable, KnowledgeStore as LegacyKnowledgeStore

class UniversalKnowledgeStore(LegacyKnowledgeStore):
    """KnowledgeStore compatibility layer backed by Vishnu File Intelligence."""

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
            segments.append({"text": block.text, "page": block.source.page, "location": location})
        stored_data = data
        stored_suffix = document.extension or Path(filename).suffix.lower()
        if document.content_kind.value == "image":
            stored_data = sanitize_image(data)
            stored_suffix = ".png"
        return segments, stored_data, stored_suffix
