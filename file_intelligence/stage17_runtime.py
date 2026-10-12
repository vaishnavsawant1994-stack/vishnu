from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from .deep_document import DocumentGraph, Stage16DeepDocumentUnderstanding
from .index import LocalContentIndex
from .models import VishnuDocument
from .semantic import LocalSemanticGraph


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class Stage17PolicyError(ValueError):
    pass


class Stage17ProductionContentRuntime:
    """Durable, scope-isolated production authority for Vishnu content intelligence.

    Stage 17 does not invent another OCR/layout/semantic stack. It composes the
    canonical VishnuDocument with Stage 16 understanding, LocalContentIndex and
    LocalSemanticGraph and records exactly which model/parser versions produced
    the stored intelligence.
    """

    version = "vishnu-production-content-runtime/17.1"
    schema_version = 1

    def __init__(self, db_path: str | Path, *, understanding: Stage16DeepDocumentUnderstanding | None = None):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.understanding = understanding or Stage16DeepDocumentUnderstanding()
        self.content_index = LocalContentIndex(self.path)
        self.semantic_graph = LocalSemanticGraph(self.path)
        self._init()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _init(self) -> None:
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS stage17_content_intelligence(
                    document_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    object_sha256 TEXT NOT NULL,
                    extraction_version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    extraction_state TEXT NOT NULL,
                    understanding_state TEXT NOT NULL,
                    lexical_index_state TEXT NOT NULL,
                    semantic_index_state TEXT NOT NULL,
                    runtime_version TEXT NOT NULL,
                    version_fingerprint TEXT NOT NULL,
                    graph_sha256 TEXT,
                    graph_json TEXT,
                    document_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(document_id,scope_type,scope_id)
                );
                CREATE INDEX IF NOT EXISTS idx_stage17_scope
                    ON stage17_content_intelligence(scope_type,scope_id,state,updated_at);
                CREATE INDEX IF NOT EXISTS idx_stage17_object
                    ON stage17_content_intelligence(object_sha256,scope_type,scope_id);
                CREATE TABLE IF NOT EXISTS stage17_content_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_stage17_events_scope
                    ON stage17_content_events(scope_type,scope_id,at,event_type);
                """
            )

    @staticmethod
    def _scope(scope_type: str, scope_id: str) -> tuple[str, str]:
        st, si = str(scope_type or "").strip(), str(scope_id or "").strip()
        if not st or not si:
            raise Stage17PolicyError("Stage 17 requires explicit scope_type and scope_id")
        return st, si

    def _event(self, con, event_type: str, *, document_id: str, scope_type: str, scope_id: str, metadata: dict | None = None) -> None:
        con.execute(
            "INSERT INTO stage17_content_events(at,event_type,document_id,scope_type,scope_id,metadata_json) VALUES(?,?,?,?,?,?)",
            (_now(), event_type, document_id, scope_type, scope_id, _canonical(metadata or {})),
        )

    def version_manifest(self, document: VishnuDocument) -> dict[str, Any]:
        return {
            "stage17_runtime": self.version,
            "stage16_understanding": self.understanding.version,
            "parser": document.parser_version,
            "layout": document.layout_version,
            "ocr": document.ocr_version,
            "media": document.media_version,
            "document_schema": document.schema_version,
        }

    def version_fingerprint(self, document: VishnuDocument) -> str:
        return _sha(self.version_manifest(document))

    def status(self, *, document_id: str, scope_type: str, scope_id: str) -> dict | None:
        st, si = self._scope(scope_type, scope_id)
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM stage17_content_intelligence WHERE document_id=? AND scope_type=? AND scope_id=?",
                (str(document_id), st, si),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item.pop("graph_json", None)
        return item

    def _graph_from_payload(self, payload: dict[str, Any]) -> DocumentGraph:
        keys = {
            "document_id", "document_sha256", "filename", "document_type", "document_type_confidence",
            "nodes", "edges", "sections", "fields", "entities", "relations", "claims", "references",
            "tables", "evidence", "model_versions", "warnings",
        }
        return DocumentGraph(**{key: payload[key] for key in keys if key in payload})

    def graph(self, *, document_id: str, scope_type: str, scope_id: str) -> DocumentGraph | None:
        st, si = self._scope(scope_type, scope_id)
        with self._con() as con:
            row = con.execute(
                "SELECT graph_json,state FROM stage17_content_intelligence WHERE document_id=? AND scope_type=? AND scope_id=?",
                (str(document_id), st, si),
            ).fetchone()
        if not row or row["state"] != "completed" or not row["graph_json"]:
            return None
        return self._graph_from_payload(json.loads(row["graph_json"]))

    def needs_reprocessing(
        self,
        document: VishnuDocument,
        *,
        scope_type: str,
        scope_id: str,
        extraction_version: int = 1,
    ) -> bool:
        current = self.status(document_id=document.document_id, scope_type=scope_type, scope_id=scope_id)
        if not current or current["state"] != "completed":
            return True
        return any(
            (
                current["object_sha256"] != document.sha256,
                int(current["extraction_version"]) != int(extraction_version),
                current["runtime_version"] != self.version,
                current["version_fingerprint"] != self.version_fingerprint(document),
            )
        )

    def process(
        self,
        document: VishnuDocument,
        *,
        scope_type: str,
        scope_id: str,
        object_sha256: str | None = None,
        extraction_version: int = 1,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        if not isinstance(document, VishnuDocument):
            raise TypeError("Stage 17 requires VishnuDocument input")
        st, si = self._scope(scope_type, scope_id)
        object_sha = str(object_sha256 or document.sha256).strip().lower()
        if object_sha != document.sha256.lower():
            raise Stage17PolicyError("Object SHA-256 does not match the canonical document")
        fingerprint = self.version_fingerprint(document)
        stamp = _now()
        with self.lock, self._con() as con:
            prior = con.execute(
                "SELECT state,object_sha256,extraction_version,runtime_version,version_fingerprint FROM stage17_content_intelligence WHERE document_id=? AND scope_type=? AND scope_id=?",
                (document.document_id, st, si),
            ).fetchone()
            if prior and prior["state"] == "completed" and prior["object_sha256"] == object_sha and int(prior["extraction_version"]) == int(extraction_version) and prior["runtime_version"] == self.version and prior["version_fingerprint"] == fingerprint:
                return self.status(document_id=document.document_id, scope_type=st, scope_id=si) or {}
            con.execute(
                """INSERT INTO stage17_content_intelligence(
                   document_id,scope_type,scope_id,object_sha256,extraction_version,state,
                   extraction_state,understanding_state,lexical_index_state,semantic_index_state,
                   runtime_version,version_fingerprint,created_at,updated_at,metadata_json)
                   VALUES(?,?,?,?,?,'running','completed','running','pending','pending',?,?,?,?,?)
                   ON CONFLICT(document_id,scope_type,scope_id) DO UPDATE SET
                   object_sha256=excluded.object_sha256,extraction_version=excluded.extraction_version,
                   state='running',extraction_state='completed',understanding_state='running',
                   lexical_index_state='pending',semantic_index_state='pending',runtime_version=excluded.runtime_version,
                   version_fingerprint=excluded.version_fingerprint,updated_at=excluded.updated_at,completed_at=NULL,
                   error_code=NULL,error_message=NULL,metadata_json=excluded.metadata_json""",
                (document.document_id, st, si, object_sha, int(extraction_version), self.version, fingerprint, stamp, stamp, _canonical(metadata or {})),
            )
            self._event(con, "stage17.processing_started", document_id=document.document_id, scope_type=st, scope_id=si, metadata={"extraction_version": int(extraction_version), "version_fingerprint": fingerprint})
            con.commit()

        try:
            graph = self.understanding.understand(document)
            graph_payload = graph.public()
            graph_sha = _sha(graph_payload)
            with self._con() as con:
                con.execute(
                    "UPDATE stage17_content_intelligence SET understanding_state='completed',graph_sha256=?,graph_json=?,document_type=?,updated_at=? WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (graph_sha, _canonical(graph_payload), graph.document_type, _now(), document.document_id, st, si),
                )
                self._event(con, "stage17.understanding_completed", document_id=document.document_id, scope_type=st, scope_id=si, metadata={"graph_sha256": graph_sha, "document_type": graph.document_type})

            lexical_blocks = self.content_index.index_document(
                document,
                scope_type=st,
                scope_id=si,
                metadata={
                    "stage17": True,
                    "stage17_runtime": self.version,
                    "stage16_understanding": self.understanding.version,
                    "version_fingerprint": fingerprint,
                    "graph_sha256": graph_sha,
                    "document_type": graph.document_type,
                },
            )
            with self._con() as con:
                con.execute("UPDATE stage17_content_intelligence SET lexical_index_state='completed',updated_at=? WHERE document_id=? AND scope_type=? AND scope_id=?", (_now(), document.document_id, st, si))
                self._event(con, "stage17.lexical_index_completed", document_id=document.document_id, scope_type=st, scope_id=si, metadata={"blocks": lexical_blocks})

            semantic = self.semantic_graph.index_document(document, scope_type=st, scope_id=si, title=document.filename)
            completed = _now()
            with self._con() as con:
                con.execute(
                    "UPDATE stage17_content_intelligence SET state='completed',semantic_index_state='completed',updated_at=?,completed_at=?,error_code=NULL,error_message=NULL WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (completed, completed, document.document_id, st, si),
                )
                self._event(con, "stage17.completed", document_id=document.document_id, scope_type=st, scope_id=si, metadata={"lexical_blocks": lexical_blocks, "semantic": semantic, "graph_sha256": graph_sha})
            return self.status(document_id=document.document_id, scope_type=st, scope_id=si) or {}
        except Exception as exc:
            with self._con() as con:
                con.execute(
                    "UPDATE stage17_content_intelligence SET state='failed',updated_at=?,error_code=?,error_message=? WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (_now(), type(exc).__name__, str(exc)[:2000], document.document_id, st, si),
                )
                self._event(con, "stage17.failed", document_id=document.document_id, scope_type=st, scope_id=si, metadata={"error_code": type(exc).__name__})
            raise

    def search(
        self,
        query: str,
        *,
        scope_type: str,
        scope_id: str,
        document_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        st, si = self._scope(scope_type, scope_id)
        lexical = self.content_index.search(query, scope_type=st, scope_id=si, document_id=document_id, limit=limit)
        semantic = self.semantic_graph.query(query, scope_type=st, scope_id=si, limit=limit)
        return {
            "stage": 17,
            "query": query,
            "scope_type": st,
            "scope_id": si,
            "document_id": document_id,
            "lexical": lexical,
            "semantic": semantic,
            "grounded_only": True,
        }

    def _candidate_graphs(self, *, scope_type: str, scope_id: str, document_id: str | None = None, limit: int = 100) -> list[DocumentGraph]:
        st, si = self._scope(scope_type, scope_id)
        sql = "SELECT graph_json FROM stage17_content_intelligence WHERE scope_type=? AND scope_id=? AND state='completed' AND graph_json IS NOT NULL"
        args: list[Any] = [st, si]
        if document_id is not None:
            sql += " AND document_id=?"
            args.append(str(document_id))
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        with self._con() as con:
            rows = con.execute(sql, args).fetchall()
        return [self._graph_from_payload(json.loads(row["graph_json"])) for row in rows]

    def answer(
        self,
        question: str,
        *,
        scope_type: str,
        scope_id: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        st, si = self._scope(scope_type, scope_id)
        answers = []
        for graph in self._candidate_graphs(scope_type=st, scope_id=si, document_id=document_id):
            result = self.understanding.answer(graph, question)
            if result.get("answered") and result.get("grounded") and result.get("citations"):
                answers.append({**result, "document_id": graph.document_id, "document_type": graph.document_type})
        if not answers:
            return {
                "stage": 17,
                "answered": False,
                "grounded": False,
                "answer": None,
                "reason": "unsupported_by_available_evidence",
                "citations": [],
                "scope_type": st,
                "scope_id": si,
                "document_id": document_id,
            }
        answers.sort(key=lambda item: (-float(item.get("confidence") or 0.0), str(item["document_id"])))
        best = answers[0]
        return {"stage": 17, "scope_type": st, "scope_id": si, **best, "candidate_documents": len(answers)}

    def compare(self, *, first_document_id: str, second_document_id: str, scope_type: str, scope_id: str) -> dict[str, Any]:
        st, si = self._scope(scope_type, scope_id)
        first = self.graph(document_id=first_document_id, scope_type=st, scope_id=si)
        second = self.graph(document_id=second_document_id, scope_type=st, scope_id=si)
        if first is None or second is None:
            raise KeyError("Both documents must have completed Stage 17 intelligence in the same scope")
        return {"stage": 17, "scope_type": st, "scope_id": si, **self.understanding.compare(first, second)}

    def links(self, *, scope_type: str, scope_id: str, limit: int = 100) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        graphs = self._candidate_graphs(scope_type=st, scope_id=si, limit=limit)
        return self.understanding.link_documents(graphs)

    def contradictions(self, *, scope_type: str, scope_id: str, limit: int = 100) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        return self.semantic_graph.contradictions(scope_type=st, scope_id=si, limit=limit)

    def timeline(self, *, scope_type: str, scope_id: str, limit: int = 200) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        return self.semantic_graph.timeline(scope_type=st, scope_id=si, limit=limit)

    def reprocessing_candidates(self, *, scope_type: str, scope_id: str, runtime_version: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        target = str(runtime_version or self.version)
        with self._con() as con:
            rows = con.execute(
                """SELECT document_id,object_sha256,extraction_version,runtime_version,version_fingerprint,updated_at
                   FROM stage17_content_intelligence
                   WHERE scope_type=? AND scope_id=? AND (state!='completed' OR runtime_version!=?)
                   ORDER BY updated_at LIMIT ?""",
                (st, si, target, max(1, min(int(limit), 5000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def events(self, *, scope_type: str, scope_id: str, limit: int = 200) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        with self._con() as con:
            rows = con.execute(
                "SELECT * FROM stage17_content_events WHERE scope_type=? AND scope_id=? ORDER BY id DESC LIMIT ?",
                (st, si, max(1, min(int(limit), 1000))),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            out.append(item)
        return out

    def health(self) -> dict[str, Any]:
        with self._con() as con:
            rows = con.execute("SELECT state,COUNT(*) count FROM stage17_content_intelligence GROUP BY state").fetchall()
        return {
            "ready": True,
            "stage": 17,
            "runtime_version": self.version,
            "understanding_version": self.understanding.version,
            "states": {row["state"]: int(row["count"]) for row in rows},
            "grounded_only": True,
            "scope_isolation_required": True,
        }
