from __future__ import annotations

import json
import time

from .engine import FileIntelligenceEngine
from .production import ProductionContentStore
from .stage17_runtime import Stage17ProductionContentRuntime


class Stage17ContentWorker:
    """Lease-holding production worker whose completion boundary includes Stage 17.

    A content ingestion job cannot become completed until extraction, deep
    understanding, lexical indexing, semantic indexing and graph persistence
    have all succeeded for the job's exact scope.
    """

    def __init__(
        self,
        store: ProductionContentStore,
        *,
        worker_id: str,
        has_gpu: bool = False,
        engine_factory=None,
        intelligence_runtime: Stage17ProductionContentRuntime | None = None,
        max_materialize_bytes: int = 2 * 1024 * 1024 * 1024,
    ):
        self.store = store
        self.worker_id = str(worker_id).strip()
        self.has_gpu = bool(has_gpu)
        self.engine_factory = engine_factory or (lambda max_bytes: FileIntelligenceEngine(max_file_bytes=max_bytes))
        self.intelligence_runtime = intelligence_runtime or Stage17ProductionContentRuntime(store.path)
        self.max_materialize_bytes = int(max_materialize_bytes)
        if not self.worker_id:
            raise ValueError("worker_id is required")

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
                }
            )

            intelligence = self.intelligence_runtime.process(
                document,
                scope_type=job["scope_type"],
                scope_id=job["scope_id"],
                object_sha256=job["object_sha256"],
                extraction_version=int(job["extraction_version"]),
                metadata={"job_id": job["job_id"], "worker_id": self.worker_id},
            )
            if intelligence.get("state") != "completed":
                raise RuntimeError("Stage 17 intelligence did not reach completed state")
            document.metadata["stage17"] = {
                "runtime_version": intelligence["runtime_version"],
                "version_fingerprint": intelligence["version_fingerprint"],
                "graph_sha256": intelligence.get("graph_sha256"),
                "document_type": intelligence.get("document_type"),
                "understanding_state": intelligence["understanding_state"],
                "lexical_index_state": intelligence["lexical_index_state"],
                "semantic_index_state": intelligence["semantic_index_state"],
                "grounded_only": True,
            }
            result = self.store.object_store.put_bytes(
                json.dumps(document.as_dict(), sort_keys=True, ensure_ascii=False, default=str).encode()
            )
            elapsed = (time.perf_counter() - started) * 1000
            return self.store.complete(
                job["job_id"],
                worker_id=self.worker_id,
                result_sha256=result.sha256,
                document_id=document.document_id,
                schema_version=document.schema_version,
                parser_version=document.parser_version,
                metadata={
                    "result_size_bytes": result.size_bytes,
                    "content_kind": document.content_kind.value,
                    "stage17_completed": True,
                    "stage17_runtime": intelligence["runtime_version"],
                    "stage17_version_fingerprint": intelligence["version_fingerprint"],
                    "stage17_graph_sha256": intelligence.get("graph_sha256"),
                },
                duration_ms=elapsed,
            )
        except Exception as exc:
            return self.store.fail(
                job["job_id"],
                worker_id=self.worker_id,
                error=exc,
                retryable=not isinstance(exc, (ValueError, PermissionError)),
                duration_ms=(time.perf_counter() - started) * 1000,
            )
