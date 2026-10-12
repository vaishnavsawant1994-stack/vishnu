from __future__ import annotations

import json
import time

from .engine import FileIntelligenceEngine
from .production import ProductionContentStore
from .stage18_multimodal import Stage18ProductionMultimodalRuntime


class Stage18ContentWorker:
    """Canonical production worker whose completion boundary includes Stage 18.

    Extraction, Stage 16 deep understanding, Stage 17 indexing and Stage 18
    multimodal evidence persistence must all complete before the ingestion job is
    reported successful. Non-visual files still receive an explicit empty Stage
    18 graph; no visual claim is fabricated.
    """

    def __init__(
        self,
        store: ProductionContentStore,
        *,
        worker_id: str,
        has_gpu: bool = False,
        engine_factory=None,
        intelligence_runtime: Stage18ProductionMultimodalRuntime | None = None,
        max_materialize_bytes: int = 2 * 1024 * 1024 * 1024,
    ):
        self.store = store
        self.worker_id = str(worker_id).strip()
        self.has_gpu = bool(has_gpu)
        self.engine_factory = engine_factory or (lambda max_bytes: FileIntelligenceEngine(max_file_bytes=max_bytes))
        self.intelligence_runtime = intelligence_runtime or Stage18ProductionMultimodalRuntime(store.path)
        self.max_materialize_bytes = int(max_materialize_bytes)
        if not self.worker_id:
            raise ValueError("worker_id is required")

    def _persist_job_completion_metadata(self, job_id: str, metadata: dict) -> dict:
        with self.store.con() as con:
            row = con.execute("SELECT metadata_json FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            merged = json.loads(row["metadata_json"] or "{}")
            merged.update(metadata)
            con.execute(
                "UPDATE content_ingestion_jobs SET metadata_json=? WHERE job_id=?",
                (json.dumps(merged, sort_keys=True, default=str), job_id),
            )
        current = self.store.job(job_id)
        if current is None:
            raise KeyError(job_id)
        return current

    def process_once(self) -> dict | None:
        job = self.store.claim(worker_id=self.worker_id, has_gpu=self.has_gpu)
        if not job:
            return None
        started = time.perf_counter()
        try:
            path = self.store.object_store.path_for(job["object_sha256"])
            size = path.stat().st_size
            if size > self.max_materialize_bytes:
                raise ValueError("Object exceeds this worker's bounded materialization limit")
            data = path.read_bytes()
            document = self.engine_factory(max(size + 1, FileIntelligenceEngine.MAX_FILE_BYTES)).extract(
                filename=job["filename"],
                data=data,
                declared_mime=job["declared_mime"],
            )
            document.document_id = f"{job['scope_type']}:{job['scope_id']}:{job['object_sha256']}:{job['extraction_version']}"
            document.metadata.update(
                {
                    "production_ingestion": True,
                    "scope_type": job["scope_type"],
                    "scope_id": job["scope_id"],
                    "object_sha256": job["object_sha256"],
                    "extraction_version": job["extraction_version"],
                    "worker_id": self.worker_id,
                    "resource_class": job["resource_class"],
                    "stage17_required": True,
                    "stage18_required": True,
                }
            )
            intelligence = self.intelligence_runtime.process(
                document,
                scope_type=job["scope_type"],
                scope_id=job["scope_id"],
                object_sha256=job["object_sha256"],
                extraction_version=int(job["extraction_version"]),
                metadata={"job_id": job["job_id"], "worker_id": self.worker_id},
                raw_content=data,
            )
            if intelligence.get("state") != "completed":
                raise RuntimeError("Stage 18 intelligence did not reach completed state")
            stage17 = dict(intelligence.get("stage17") or {})
            if stage17.get("state") != "completed":
                raise RuntimeError("Stage 17 intelligence did not reach completed state")
            document.metadata["stage17"] = {
                "runtime_version": stage17.get("runtime_version"),
                "version_fingerprint": stage17.get("version_fingerprint"),
                "graph_sha256": stage17.get("graph_sha256"),
                "document_type": stage17.get("document_type"),
                "understanding_state": stage17.get("understanding_state"),
                "lexical_index_state": stage17.get("lexical_index_state"),
                "semantic_index_state": stage17.get("semantic_index_state"),
                "grounded_only": True,
            }
            document.metadata["stage18"] = {
                "runtime_version": intelligence.get("runtime_version"),
                "version_fingerprint": intelligence.get("version_fingerprint"),
                "graph_sha256": intelligence.get("graph_sha256"),
                "real_world_corpus_qualified": bool(intelligence.get("real_world_corpus_qualified")),
                "real_world_evidence_sha256": intelligence.get("real_world_evidence_sha256"),
                "grounded_only": True,
                "foundation_model": False,
            }
            result = self.store.object_store.put_bytes(
                json.dumps(document.as_dict(), sort_keys=True, ensure_ascii=False, default=str).encode()
            )
            elapsed = (time.perf_counter() - started) * 1000
            completion_metadata = {
                "result_size_bytes": result.size_bytes,
                "content_kind": document.content_kind.value,
                "stage17_completed": True,
                "stage17_runtime": stage17.get("runtime_version"),
                "stage17_version_fingerprint": stage17.get("version_fingerprint"),
                "stage17_graph_sha256": stage17.get("graph_sha256"),
                "stage18_completed": True,
                "stage18_runtime": intelligence.get("runtime_version"),
                "stage18_version_fingerprint": intelligence.get("version_fingerprint"),
                "stage18_graph_sha256": intelligence.get("graph_sha256"),
                "real_world_corpus_qualified": bool(intelligence.get("real_world_corpus_qualified")),
            }
            self.store.complete(
                job["job_id"],
                worker_id=self.worker_id,
                result_sha256=result.sha256,
                document_id=document.document_id,
                schema_version=document.schema_version,
                parser_version=document.parser_version,
                metadata=completion_metadata,
                duration_ms=elapsed,
            )
            return self._persist_job_completion_metadata(job["job_id"], completion_metadata)
        except Exception as exc:
            current = self.store.job(job["job_id"])
            if current and current.get("status") == "completed":
                raise
            return self.store.fail(
                job["job_id"],
                worker_id=self.worker_id,
                error=exc,
                retryable=not isinstance(exc, (ValueError, PermissionError)),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
