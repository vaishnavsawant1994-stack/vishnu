from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable

from .models import VishnuBlock, VishnuDocument


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalContentIndex:
    """SQLite FTS5 index with exact Vishnu source references and a LIKE fallback."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._init()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_index_documents(
                    document_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    indexed_at TEXT NOT NULL,
                    PRIMARY KEY(document_id,scope_type,scope_id)
                );
                CREATE TABLE IF NOT EXISTS content_index_blocks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_json TEXT NOT NULL DEFAULT '{}',
                    data_json TEXT,
                    confidence REAL,
                    UNIQUE(document_id,scope_type,scope_id,position)
                );
                CREATE INDEX IF NOT EXISTS idx_content_index_scope
                    ON content_index_blocks(scope_type,scope_id,document_id,position);
                """
            )
            try:
                con.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS content_index_fts USING fts5(
                       document_id UNINDEXED, scope_type UNINDEXED, scope_id UNINDEXED,
                       position UNINDEXED, title, kind, text)"""
                )
            except sqlite3.OperationalError:
                pass

    def state(self, *, document_id: str, scope_type: str, scope_id: str) -> dict | None:
        with self._con() as con:
            row = con.execute(
                """SELECT * FROM content_index_documents
                   WHERE document_id=? AND scope_type=? AND scope_id=?""",
                (document_id, scope_type, scope_id),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def remove(self, *, document_id: str, scope_type: str, scope_id: str) -> None:
        with self.lock, self._con() as con:
            con.execute(
                "DELETE FROM content_index_blocks WHERE document_id=? AND scope_type=? AND scope_id=?",
                (document_id, scope_type, scope_id),
            )
            con.execute(
                "DELETE FROM content_index_documents WHERE document_id=? AND scope_type=? AND scope_id=?",
                (document_id, scope_type, scope_id),
            )
            try:
                con.execute(
                    "DELETE FROM content_index_fts WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (document_id, scope_type, scope_id),
                )
            except sqlite3.OperationalError:
                pass

    def index_document(
        self,
        document: VishnuDocument,
        *,
        scope_type: str,
        scope_id: str,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        return self.index_blocks(
            document_id=document.document_id,
            checksum=document.sha256,
            title=title or document.filename,
            blocks=document.blocks,
            scope_type=scope_type,
            scope_id=scope_id,
            metadata={
                "filename": document.filename,
                "content_kind": document.content_kind.value,
                "parser_version": document.parser_version,
                "ocr_version": document.ocr_version,
                "media_version": document.media_version,
                "layout_version": document.layout_version,
                **dict(metadata or {}),
            },
        )

    def index_blocks(
        self,
        *,
        document_id: str,
        checksum: str,
        title: str,
        blocks: Iterable[VishnuBlock],
        scope_type: str,
        scope_id: str,
        metadata: dict | None = None,
    ) -> int:
        clean_scope = str(scope_type or "").strip()
        clean_scope_id = str(scope_id or "").strip()
        if not clean_scope or not clean_scope_id:
            raise ValueError("Content index requires explicit scope_type and scope_id")
        materialized = [block for block in blocks if str(block.text or "").strip()]
        stamp = _now()
        with self.lock, self._con() as con:
            con.execute(
                "DELETE FROM content_index_blocks WHERE document_id=? AND scope_type=? AND scope_id=?",
                (document_id, clean_scope, clean_scope_id),
            )
            con.execute(
                "DELETE FROM content_index_documents WHERE document_id=? AND scope_type=? AND scope_id=?",
                (document_id, clean_scope, clean_scope_id),
            )
            try:
                con.execute(
                    "DELETE FROM content_index_fts WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (document_id, clean_scope, clean_scope_id),
                )
            except sqlite3.OperationalError:
                pass
            con.execute(
                """INSERT INTO content_index_documents(
                   document_id,scope_type,scope_id,title,checksum,metadata_json,indexed_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    document_id,
                    clean_scope,
                    clean_scope_id,
                    str(title or "")[:500],
                    str(checksum or ""),
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                    stamp,
                ),
            )
            for position, block in enumerate(materialized):
                source_json = json.dumps(block.source.compact(), ensure_ascii=False, default=str)
                data_json = None if block.data is None else json.dumps(block.data, ensure_ascii=False, default=str)
                con.execute(
                    """INSERT INTO content_index_blocks(
                       document_id,scope_type,scope_id,position,kind,text,source_json,data_json,confidence)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        document_id,
                        clean_scope,
                        clean_scope_id,
                        position,
                        str(block.kind or "text")[:80],
                        str(block.text),
                        source_json,
                        data_json,
                        block.confidence,
                    ),
                )
                try:
                    con.execute(
                        """INSERT INTO content_index_fts(
                           document_id,scope_type,scope_id,position,title,kind,text)
                           VALUES(?,?,?,?,?,?,?)""",
                        (
                            document_id,
                            clean_scope,
                            clean_scope_id,
                            position,
                            str(title or "")[:500],
                            str(block.kind or "text")[:80],
                            str(block.text),
                        ),
                    )
                except sqlite3.OperationalError:
                    pass
        return len(materialized)

    @staticmethod
    def _match_query(query: str) -> str:
        terms = re.findall(r"[\w@.+#/-]{2,}", str(query or ""), flags=re.UNICODE)[:16]
        if not terms:
            raise ValueError("Search query must contain searchable terms")
        return " AND ".join('"' + term.replace('"', '""') + '"*' for term in terms)

    def search(
        self,
        query: str,
        *,
        scope_type: str,
        scope_id: str | None = None,
        document_id: str | None = None,
        kinds: set[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        scope_type = str(scope_type or "").strip()
        if not scope_type:
            raise ValueError("scope_type is required")
        params: list[object]
        with self._con() as con:
            try:
                clauses = ["x.scope_type=?", "content_index_fts MATCH ?"]
                params = [scope_type, self._match_query(query)]
                if scope_id is not None:
                    clauses.append("x.scope_id=?")
                    params.append(str(scope_id))
                if document_id is not None:
                    clauses.append("x.document_id=?")
                    params.append(str(document_id))
                if kinds:
                    marks = ",".join("?" for _ in kinds)
                    clauses.append(f"x.kind IN ({marks})")
                    params.extend(sorted(kinds))
                params.append(limit)
                rows = con.execute(
                    f"""SELECT x.document_id,x.scope_type,x.scope_id,x.position,x.title,x.kind,x.text,
                               bm25(content_index_fts) AS rank,b.source_json,b.data_json,b.confidence
                        FROM content_index_fts x
                        JOIN content_index_blocks b
                          ON b.document_id=x.document_id AND b.scope_type=x.scope_type
                         AND b.scope_id=x.scope_id AND b.position=CAST(x.position AS INTEGER)
                        WHERE {' AND '.join(clauses)}
                        ORDER BY rank LIMIT ?""",
                    params,
                ).fetchall()
            except sqlite3.OperationalError:
                clauses = ["b.scope_type=?", "(b.text LIKE ? ESCAPE '\\' OR d.title LIKE ? ESCAPE '\\')"]
                like = "%" + str(query or "").replace("%", "\\%").replace("_", "\\_") + "%"
                params = [scope_type, like, like]
                if scope_id is not None:
                    clauses.append("b.scope_id=?")
                    params.append(str(scope_id))
                if document_id is not None:
                    clauses.append("b.document_id=?")
                    params.append(str(document_id))
                if kinds:
                    marks = ",".join("?" for _ in kinds)
                    clauses.append(f"b.kind IN ({marks})")
                    params.extend(sorted(kinds))
                params.append(limit)
                rows = con.execute(
                    f"""SELECT b.document_id,b.scope_type,b.scope_id,b.position,d.title,b.kind,b.text,
                               0.0 AS rank,b.source_json,b.data_json,b.confidence
                        FROM content_index_blocks b
                        JOIN content_index_documents d
                          ON d.document_id=b.document_id AND d.scope_type=b.scope_type AND d.scope_id=b.scope_id
                        WHERE {' AND '.join(clauses)}
                        ORDER BY b.position LIMIT ?""",
                    params,
                ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            source = json.loads(item.pop("source_json") or "{}")
            data_json = item.pop("data_json")
            item["data"] = json.loads(data_json) if data_json else None
            item["source"] = source
            item["score"] = -float(item.pop("rank") or 0.0)
            item["citation"] = {
                "document_id": item["document_id"],
                "scope_type": item["scope_type"],
                "scope_id": item["scope_id"],
                "position": item["position"],
                "title": item["title"],
                "kind": item["kind"],
                "source": source,
            }
            results.append(item)
        return results
