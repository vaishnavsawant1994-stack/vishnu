from __future__ import annotations

from pathlib import Path

from file_intelligence import (
    ContentKind,
    FileIntelligenceEngine,
    OcrUnavailable,
    Stage18ProductionMultimodalRuntime,
    TesseractOcrProvider,
    VishnuDocument,
)
from file_intelligence.models import ExtractionMethod, SourceReference, VishnuBlock
from file_intelligence.readers import ContentReadError, sanitize_image
from knowledge.store import KnowledgeError, KnowledgeOcrUnavailable, KnowledgeStore as LegacyKnowledgeStore


class UniversalKnowledgeStore(LegacyKnowledgeStore):
    """KnowledgeStore compatibility layer backed by Stage 18 File Intelligence."""

    MAX_FILE_BYTES = FileIntelligenceEngine.MAX_FILE_BYTES

    def __init__(self, path, object_dir, *, ocr_provider=None, allow_external_private_ocr: bool = False):
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
        self.stage18_runtime = Stage18ProductionMultimodalRuntime(self.path)
        # Compatibility: existing semantic callers/tests still use the Stage 17
        # name, while the runtime now composes and persists both Stage 17 and 18.
        self.stage17_runtime = self.stage18_runtime
        self.content_index = self.stage18_runtime.content_index
        self.semantic_graph = self.stage18_runtime.semantic_graph

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

    @staticmethod
    def _content_kind_for(filename: str) -> ContentKind:
        suffix = Path(filename).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
            return ContentKind.IMAGE
        if suffix == ".pdf":
            return ContentKind.PDF
        if suffix in {".xlsx", ".csv"}:
            return ContentKind.SPREADSHEET
        if suffix == ".pptx":
            return ContentKind.PRESENTATION
        if suffix in {".txt", ".md", ".markdown"}:
            return ContentKind.TEXT
        return ContentKind.DOCUMENT

    def _document_from_detail(self, detail: dict) -> VishnuDocument:
        chunks = detail.get("chunks") or []
        blocks = [self._block_from_chunk(chunk) for chunk in chunks if str(chunk.get("content") or "").strip()]
        filename = str(detail.get("filename") or detail.get("title") or detail["id"])
        extension = Path(filename).suffix.lower()
        return VishnuDocument(
            document_id=str(detail["id"]),
            filename=filename,
            content_kind=self._content_kind_for(filename),
            detected_mime=str((detail.get("metadata") or {}).get("detected_mime") or detail.get("media_type") or "application/octet-stream"),
            declared_mime=str((detail.get("metadata") or {}).get("declared_mime") or detail.get("media_type") or "application/octet-stream"),
            extension=extension,
            sha256=str(detail["checksum"]),
            size_bytes=int(detail.get("size_bytes") or (detail.get("metadata") or {}).get("size_bytes") or 0),
            blocks=blocks,
            metadata={
                "knowledge": True,
                "lineage_id": detail.get("lineage_id"),
                "version": detail.get("version"),
                "source": detail.get("source"),
                "access_class": detail.get("access_class"),
                "capture_kind": (detail.get("metadata") or {}).get("capture_kind"),
            },
        )

    def _raw_content_for(self, document_id: str) -> bytes | None:
        with self._con() as con:
            row = con.execute("SELECT object_name FROM knowledge_documents WHERE id=?", (str(document_id),)).fetchone()
        if not row:
            return None
        path = self.object_dir / str(row["object_name"])
        return path.read_bytes() if path.is_file() else None

    def _index_detail(self, detail: dict) -> None:
        document = self._document_from_detail(detail)
        status = self.stage18_runtime.process(
            document,
            scope_type="knowledge",
            scope_id=str(detail["access_class"]),
            object_sha256=document.sha256,
            extraction_version=max(1, int(detail.get("version") or 1)),
            metadata={
                "lineage_id": detail.get("lineage_id"),
                "knowledge_version": detail.get("version"),
                "title": detail.get("title"),
                "source": detail.get("source"),
                "available_to_vishnu": bool((detail.get("metadata") or {}).get("available_to_vishnu", True)),
            },
            raw_content=self._raw_content_for(detail["id"]),
        )
        if status.get("state") != "completed" or dict(status.get("stage17") or {}).get("state") != "completed":
            raise KnowledgeError("Stage 18 knowledge intelligence did not complete")

    def ingest(self, **kwargs):
        detail = super().ingest(**kwargs)
        if detail:
            self._index_detail(detail)
        return detail

    def ensure_exact_index(self, *, access_classes: set[str] | None = None) -> int:
        indexed = 0
        for item in self.list(limit=500, access_classes=access_classes):
            stage17 = self.stage18_runtime.status(
                document_id=item["id"], scope_type="knowledge", scope_id=item["access_class"]
            )
            stage18 = self.stage18_runtime.stage18_status(
                document_id=item["id"], scope_type="knowledge", scope_id=item["access_class"]
            )
            if (
                stage17
                and stage17["state"] == "completed"
                and stage17["object_sha256"] == item["checksum"]
                and stage18
                and stage18["state"] == "completed"
                and stage18["object_sha256"] == item["checksum"]
            ):
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
            hits = self.content_index.search(query, scope_type="knowledge", scope_id=access_class, limit=max(limit, 20))
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

    def semantic_query(self, query: str, *, access_classes: set[str] | None = None, limit: int = 30) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        return [
            self.stage18_runtime.search(query, scope_type="knowledge", scope_id=access_class, limit=limit)
            for access_class in sorted(classes)
        ]

    def grounded_answer(self, question: str, *, access_classes: set[str] | None = None, document_id: str | None = None) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        answers = []
        for access_class in sorted(classes):
            result = self.stage18_runtime.answer(question, scope_type="knowledge", scope_id=access_class, document_id=document_id)
            result["access_class"] = access_class
            answers.append(result)
        return answers

    def grounded_visual_answer(self, question: str, *, access_classes: set[str] | None = None, document_id: str | None = None) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        answers = []
        for access_class in sorted(classes):
            result = self.stage18_runtime.answer_visual(question, scope_type="knowledge", scope_id=access_class, document_id=document_id)
            result["access_class"] = access_class
            answers.append(result)
        return answers

    def compare_documents(self, first_document_id: str, second_document_id: str, *, access_class: str) -> dict:
        self.ensure_exact_index(access_classes={access_class})
        return self.stage18_runtime.compare(
            first_document_id=first_document_id,
            second_document_id=second_document_id,
            scope_type="knowledge",
            scope_id=access_class,
        )

    def compare_visual_documents(self, first_document_id: str, second_document_id: str, *, access_class: str) -> dict:
        self.ensure_exact_index(access_classes={access_class})
        return self.stage18_runtime.compare_visual(
            first_document_id=first_document_id,
            second_document_id=second_document_id,
            scope_type="knowledge",
            scope_id=access_class,
        )

    def semantic_links(self, *, access_classes: set[str] | None = None, limit: int = 100) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        return [
            {"access_class": access_class, "links": self.stage18_runtime.links(scope_type="knowledge", scope_id=access_class, limit=limit)}
            for access_class in sorted(classes)
        ]

    def semantic_contradictions(self, *, access_classes: set[str] | None = None, limit: int = 100) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        return [
            {"access_class": access_class, "contradictions": self.stage18_runtime.contradictions(scope_type="knowledge", scope_id=access_class, limit=limit)}
            for access_class in sorted(classes)
        ]

    def semantic_timeline(self, *, access_classes: set[str] | None = None, limit: int = 200) -> list[dict]:
        self.ensure_exact_index(access_classes=access_classes)
        classes = access_classes or {"owner", "trusted-devices", "private"}
        return [
            {"access_class": access_class, "events": self.stage18_runtime.timeline(scope_type="knowledge", scope_id=access_class, limit=limit)}
            for access_class in sorted(classes)
        ]
