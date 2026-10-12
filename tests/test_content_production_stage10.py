from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_intelligence import FileIntelligenceEngine
from file_intelligence.production import (
    ContentBenchmark,
    ContentResourceRouter,
    ContentWorker,
    JobStatus,
    ProductionContentStore,
    ResourceClass,
)
from server.runtime_state_api import runtime_state_router


def _upload(store, payload=b"hello Vishnu production content", *, scope_type="knowledge", scope_id="owner", filename="note.txt"):
    upload = store.create_upload(
        scope_type=scope_type,
        scope_id=scope_id,
        filename=filename,
        total_bytes=len(payload),
        declared_mime="text/plain",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )
    split = max(1, len(payload) // 2)
    upload = store.append_chunk(upload["upload_id"], offset=0, chunk=payload[:split])
    upload = store.append_chunk(upload["upload_id"], offset=split, chunk=payload[split:])
    return store.finalize_upload(upload["upload_id"])


def test_resumable_upload_enforces_offsets_checksum_and_content_dedup(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects", max_upload_bytes=1024)
    payload = b"same object"
    sha = hashlib.sha256(payload).hexdigest()
    upload = store.create_upload(scope_type="project", scope_id="p1", filename="a.txt", total_bytes=len(payload), expected_sha256=sha)
    with pytest.raises(ValueError, match="offset"):
        store.append_chunk(upload["upload_id"], offset=1, chunk=b"x")
    store.append_chunk(upload["upload_id"], offset=0, chunk=payload)
    done = store.finalize_upload(upload["upload_id"])
    assert done["object_sha256"] == sha
    assert store.object_store.verify(sha)

    second = store.create_upload(scope_type="project", scope_id="p1", filename="b.txt", total_bytes=len(payload), expected_sha256=sha)
    store.append_chunk(second["upload_id"], offset=0, chunk=payload)
    second = store.finalize_upload(second["upload_id"])
    assert second["object_sha256"] == sha
    assert store.object_store.path_for(sha).is_file()


def test_upload_rejects_size_overflow_and_wrong_expected_hash(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects", max_upload_bytes=8)
    with pytest.raises(ValueError, match="size"):
        store.create_upload(scope_type="knowledge", scope_id="owner", filename="huge.txt", total_bytes=9)
    upload = store.create_upload(scope_type="knowledge", scope_id="owner", filename="a.txt", total_bytes=3, expected_sha256="0" * 64)
    store.append_chunk(upload["upload_id"], offset=0, chunk=b"abc")
    with pytest.raises(ValueError, match="checksum"):
        store.finalize_upload(upload["upload_id"])


def test_queue_is_idempotent_and_force_reprocessing_gets_new_version(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")
    upload = _upload(store)
    first = store.enqueue_upload(upload["upload_id"])
    duplicate = store.enqueue_upload(upload["upload_id"])
    forced = store.enqueue_upload(upload["upload_id"], force=True)
    forced_again = store.enqueue_upload(upload["upload_id"], force=True)
    assert duplicate["job_id"] == first["job_id"]
    assert [first["extraction_version"], forced["extraction_version"], forced_again["extraction_version"]] == [1, 2, 3]


def test_worker_processes_real_vishnu_document_and_result_is_integrity_addressed(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")
    upload = _upload(store, b"Vishnu production ingestion works.")
    job = store.enqueue_upload(upload["upload_id"])
    worker = ContentWorker(store, worker_id="cpu-1", has_gpu=False)
    completed = worker.process_once()
    assert completed["job_id"] == job["job_id"]
    assert completed["status"] == JobStatus.COMPLETED.value
    result = store.result(job["job_id"])
    assert result["result_sha256"] == completed["result_sha256"]
    assert store.object_store.verify(result["result_sha256"])
    assert result["document"]["metadata"]["production_ingestion"] is True
    assert result["document"]["metadata"]["scope_id"] == "owner"
    assert "Vishnu production ingestion works" in result["document"]["full_text"]


def test_gpu_required_jobs_are_not_claimed_by_cpu_only_workers(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")
    obj = store.object_store.put_bytes(b"video bytes")
    job = store.enqueue(object_sha256=obj.sha256, filename="clip.mp4", scope_type="project", scope_id="p1", resource_class=ResourceClass.GPU_REQUIRED)
    assert store.claim(worker_id="cpu", has_gpu=False) is None
    claimed = store.claim(worker_id="gpu", has_gpu=True)
    assert claimed["job_id"] == job["job_id"]


def test_expired_leases_are_reclaimed_and_retry_exhaustion_is_durable(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")
    obj = store.object_store.put_bytes(b"work")
    # The stale claim is a real processing attempt, so use three total attempts:
    # stale lease -> retryable failure -> terminal failure.
    job = store.enqueue(object_sha256=obj.sha256, filename="work.txt", scope_type="knowledge", scope_id="owner", max_attempts=3)
    claimed = store.claim(worker_id="stale")
    assert claimed["attempts"] == 1
    with store.con() as con:
        con.execute("UPDATE content_ingestion_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job["job_id"],))
    assert store.reclaim_expired() == 1
    claimed = store.claim(worker_id="retry")
    assert claimed["attempts"] == 2
    first = store.fail(claimed["job_id"], worker_id="retry", error=RuntimeError("transient"), retryable=True)
    assert first["status"] == JobStatus.QUEUED.value
    with store.con() as con:
        con.execute("UPDATE content_ingestion_jobs SET available_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job["job_id"],))
    second_claim = store.claim(worker_id="retry")
    assert second_claim["attempts"] == 3
    final = store.fail(second_claim["job_id"], worker_id="retry", error=RuntimeError("still failing"), retryable=True)
    assert final["status"] == JobStatus.FAILED.value
    assert final["attempts"] == 3


def test_resource_router_metrics_health_and_benchmark_helpers(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")
    router = ContentResourceRouter()
    assert router.classify("contract.pdf") == ResourceClass.CPU
    assert router.classify("meeting.mp4") == ResourceClass.GPU_PREFERRED
    assert router.classify("anything.bin", require_gpu=True) == ResourceClass.GPU_REQUIRED
    assert store.health()["ready"] is True
    assert store.metrics()["jobs"] == {}
    benchmark = ContentBenchmark.extraction_latency(FileIntelligenceEngine(), [("a.txt", b"hello", "text/plain")])
    assert benchmark["fixtures"] == 1
    assert benchmark["bytes"] == 5
    assert ContentBenchmark.classification_accuracy([("a", "a"), ("b", "a")])["accuracy"] == 0.5


def test_runtime_state_router_preserves_old_route_and_mounts_one_cross_platform_ingestion_surface(tmp_path):
    store = ProductionContentStore(tmp_path / "runtime.sqlite3", tmp_path / "objects")

    class Registry:
        def is_active(self, device_id): return True
        def authorize(self, device_id, capability): return True

    class RuntimeState:
        def snapshot(self): return {}

    runtime = {
        "device_registry": Registry(),
        "events": SimpleNamespace(runtime_state=RuntimeState()),
        "content_ingestion": store,
        "base_project_store": SimpleNamespace(get=lambda project_id: {"id": project_id, "status": "active"}),
    }
    app = FastAPI()
    app.include_router(runtime_state_router(runtime))

    # FastAPI 0.137+ keeps included routers as live lazy route trees rather than
    # copying each APIRoute into app.routes. Validate public routing/OpenAPI instead
    # of relying on that internal representation.
    paths = app.openapi()["paths"]
    assert "/iphone/api/runtime-state" in paths
    assert "/iphone/api/content-ingestion/uploads" in paths
    assert "/iphone/api/content-ingestion/jobs/{job_id}/result" in paths
    assert list(paths).count("/iphone/api/content-ingestion/uploads") == 1

    with TestClient(app) as client:
        assert client.get("/iphone/api/runtime-state").status_code == 401
        assert client.get("/iphone/api/content-ingestion/health").status_code == 401
