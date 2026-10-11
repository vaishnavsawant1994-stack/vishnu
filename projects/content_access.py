from __future__ import annotations

import hashlib
import json
from typing import Any

from file_intelligence import FileIntelligenceEngine, LocalContentIndex, TesseractOcrProvider
from file_intelligence.models import VishnuDocument


class ProjectContentAccess:
    """Project-scoped, provenance-preserving access to existing project file blobs."""

    def __init__(self, store, *, ocr_provider=None):
        self.store = store
        self.ocr_provider = ocr_provider if ocr_provider is not None else TesseractOcrProvider()
        self.engine = FileIntelligenceEngine(ocr_provider=self.ocr_provider)
        # Reuse the authoritative Project SQLite DB; no second file store is created.
        self.index = LocalContentIndex(store.path)

    def _project_exists(self, project_id: str) -> bool:
        with self.store.con() as con:
            return bool(
                con.execute(
                    "SELECT 1 FROM projects WHERE id=? AND status!='archived'",
                    (str(project_id),),
                ).fetchone()
            )

    def _blob(self, project_id: str, file_id: str) -> dict[str, Any]:
        with self.store.con() as con:
            row = con.execute(
                """SELECT f.id,f.project_id,f.title,f.kind,f.knowledge_id,b.media_type,b.content,b.size_bytes
                   FROM project_files f
                   JOIN project_file_blobs b ON b.file_id=f.id
                   WHERE f.id=? AND f.project_id=?""",
                (str(file_id), str(project_id)),
            ).fetchone()
        if not row:
            raise KeyError("Project file not found in the requested project")
        item = dict(row)
        item["content"] = bytes(item["content"])
        return item

    def list_files(self, project_id: str) -> list[dict]:
        if not self._project_exists(project_id):
            raise KeyError("Project not found")
        with self.store.con() as con:
            rows = con.execute(
                """SELECT f.id,f.title,f.kind,f.url,f.knowledge_id,f.created_at,
                          b.media_type,b.size_bytes
                   FROM project_files f
                   LEFT JOIN project_file_blobs b ON b.file_id=f.id
                   WHERE f.project_id=? ORDER BY f.created_at,f.id""",
                (str(project_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def extract_file(self, project_id: str, file_id: str, *, force: bool = False) -> VishnuDocument:
        row = self._blob(project_id, file_id)
        checksum = hashlib.sha256(row["content"]).hexdigest()
        state = self.index.state(document_id=row["id"], scope_type="project", scope_id=str(project_id))
        if state and state["checksum"] == checksum and not force:
            # We still return a live canonical document; callers never consume stale serialized parser output.
            document = self.engine.extract(
                filename=row["title"],
                data=row["content"],
                declared_mime=row["media_type"] or "application/octet-stream",
            )
        else:
            document = self.engine.extract(
                filename=row["title"],
                data=row["content"],
                declared_mime=row["media_type"] or "application/octet-stream",
            )
        document.document_id = row["id"]
        document.metadata.update(
            {
                "project_id": str(project_id),
                "project_file_id": row["id"],
                "project_file_kind": row["kind"],
                "knowledge_id": row.get("knowledge_id"),
            }
        )
        self.index.index_document(
            document,
            scope_type="project",
            scope_id=str(project_id),
            title=row["title"],
            metadata={
                "project_file_id": row["id"],
                "media_type": row["media_type"],
                "size_bytes": row["size_bytes"],
            },
        )
        return document

    def ensure_indexed(self, project_id: str) -> int:
        files = self.list_files(project_id)
        indexed = 0
        for item in files:
            if item.get("size_bytes") is None:
                continue
            try:
                row = self._blob(project_id, item["id"])
                checksum = hashlib.sha256(row["content"]).hexdigest()
                state = self.index.state(
                    document_id=item["id"],
                    scope_type="project",
                    scope_id=str(project_id),
                )
                if state and state["checksum"] == checksum:
                    continue
                self.extract_file(project_id, item["id"], force=True)
                indexed += 1
            except Exception:
                # A single unsupported/corrupt source must not block other project sources.
                continue
        return indexed

    def search(self, project_id: str, query: str, *, limit: int = 20, kinds: set[str] | None = None) -> list[dict]:
        if not self._project_exists(project_id):
            raise KeyError("Project not found")
        self.ensure_indexed(project_id)
        return self.index.search(
            query,
            scope_type="project",
            scope_id=str(project_id),
            kinds=kinds,
            limit=limit,
        )

    def read(self, project_id: str, file_id: str) -> dict:
        document = self.extract_file(project_id, file_id)
        return document.as_dict()

    def tables(self, project_id: str, file_id: str) -> list[dict]:
        document = self.extract_file(project_id, file_id)
        return [
            {
                "position": position,
                "kind": block.kind,
                "text": block.text,
                "source": block.source.compact(),
                "data": block.data,
                "confidence": block.confidence,
            }
            for position, block in enumerate(document.blocks)
            if block.kind == "table"
        ]

    def forms(self, project_id: str, file_id: str) -> list[dict]:
        document = self.extract_file(project_id, file_id)
        return [
            {
                "position": position,
                "kind": block.kind,
                "text": block.text,
                "source": block.source.compact(),
                "data": block.data,
                "confidence": block.confidence,
            }
            for position, block in enumerate(document.blocks)
            if block.kind in {"key_value", "form_field"}
        ]
