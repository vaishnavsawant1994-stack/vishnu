from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from file_intelligence import (
    ContentKind,
    ContentWorker,
    ExtractionMethod,
    SourceReference,
    Stage17ContentWorker,
    Stage17PolicyError,
    Stage17ProductionContentRuntime,
    Stage18ContentWorker,
    VishnuBlock,
    VishnuDocument,
)
from file_intelligence.production import JobStatus, ProductionContentStore
from knowledge.universal_store import UniversalKnowledgeStore
from server.content_ingestion_api import content_ingestion_router


INVOICE_TEXT = b"""INVOICE
Invoice Number: INV-700
Acme GmbH issued this invoice.
Amount due EUR 120.00.
Payment is due on 2026-11-01.
The customer shall pay within 30 days.
"""


def _document(document_id: str, invoice_number: str = "INV-700", company: str = "Acme GmbH") -> VishnuDocument:
    text = (
        "INVOICE\n"
        f"Invoice Number: {invoice_number}\n"
        f"{company} issued this invoice.\n"
        "Amount due EUR 120.00.\n"
        "Payment is due on 2026-11-01.\n"
        "The customer shall pay within 30 days."
    )
    digest = hashlib.sha256(text.encode()).hexdigest()
    return VishnuDocument(
        document_id=document_id,
        filename=f"{document_id}.txt",
        content_kind=ContentKind.TEXT,
        detected_mime="text/plain",
        declared_mime="text/plain",
        extension=".txt",
        sha256=digest,
        size_bytes=len(text.encode()),
        blocks=[
            VishnuBlock(
                kind="text",
                text=text,
                source=SourceReference(line_start=1, line_end=6),
                extraction_method=ExtractionMethod.NATIVE,
                confidence=1.0,
            )
        ],
    )


def test_stage17_worker_remains_available_after_stage18_becomes_canonical():
    assert Stage17ContentWorker is not None
    assert ContentWorker is Stage18ContentWorker


def test_stage17_production_worker_requires_understanding_and_indexes_before_completion(tmp_path: Path):
    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    obj = store.object_store.put_bytes(INVOICE_TEXT)
    job = store.enqueue(
        object_sha256=obj.sha256,
        filename="invoice.txt",
        scope_type="project",
        scope_id="project-a",
        declared_mime="text/plain",
        max_attempts=1,
    )
    worker = ContentWorker(store, worker_id="stage17-test-worker")
    completed = worker.process_once()
    assert completed is not None
    assert completed["job_id"] == job["job_id"]
    assert completed["status"] == JobStatus.COMPLETED.value
    assert completed["metadata"]["stage17_completed"] is True
    assert completed["metadata"]["stage18_completed"] is True

    result = store.result(job["job_id"])
    assert result is not None
    document_id = result["document"]["document_id"]
    intelligence = Stage17ProductionContentRuntime(store.path)
    status = intelligence.status(document_id=document_id, scope_type="project", scope_id="project-a")
    assert status is not None
    assert status["state"] == "completed"
    assert status["extraction_state"] == "completed"
    assert status["understanding_state"] == "completed"
    assert status["lexical_index_state"] == "completed"
    assert status["semantic_index_state"] == "completed"
    assert status["graph_sha256"]
    assert status["document_type"] == "invoice"

    graph = intelligence.graph(document_id=document_id, scope_type="project", scope_id="project-a")
    assert graph is not None
    assert graph.document_type == "invoice"
    assert any(field["name"] == "invoice_number" and field["value"] == "INV-700" for field in graph.fields)
    assert graph.evidence
    answer = intelligence.answer("What is the invoice number?", scope_type="project", scope_id="project-a", document_id=document_id)
    assert answer["answered"] is True
    assert answer["grounded"] is True
    assert answer["answer"] == "INV-700"
    assert answer["citations"]
    unsupported = intelligence.answer("What will the weather be tomorrow?", scope_type="project", scope_id="project-a", document_id=document_id)
    assert unsupported["answered"] is False
    assert unsupported["grounded"] is False
    assert unsupported["reason"] == "unsupported_by_available_evidence"
    assert unsupported["citations"] == []


def test_stage17_scope_isolation_blocks_cross_project_retrieval(tmp_path: Path):
    runtime = Stage17ProductionContentRuntime(tmp_path / "stage17.sqlite3")
    document = _document("invoice-project-a")
    runtime.process(document, scope_type="project", scope_id="project-a", object_sha256=document.sha256)
    same_scope = runtime.search("INV-700", scope_type="project", scope_id="project-a")
    assert same_scope["lexical"]
    other_scope = runtime.search("INV-700", scope_type="project", scope_id="project-b")
    assert other_scope["lexical"] == []
    assert other_scope["semantic"]["entities"] == []
    assert other_scope["semantic"]["relations"] == []
    rejected = runtime.answer("What is the invoice number?", scope_type="project", scope_id="project-b")
    assert rejected["answered"] is False
    assert rejected["citations"] == []
    assert runtime.status(document_id=document.document_id, scope_type="project", scope_id="project-b") is None
    assert runtime.graph(document_id=document.document_id, scope_type="project", scope_id="project-b") is None


def test_stage17_compare_links_and_versioned_reprocessing_are_grounded(tmp_path: Path):
    runtime = Stage17ProductionContentRuntime(tmp_path / "stage17.sqlite3")
    first = _document("invoice-a", "INV-700")
    second = _document("invoice-b", "INV-800")
    runtime.process(first, scope_type="project", scope_id="project-a", object_sha256=first.sha256, extraction_version=1)
    runtime.process(second, scope_type="project", scope_id="project-a", object_sha256=second.sha256, extraction_version=1)
    comparison = runtime.compare(first_document_id=first.document_id, second_document_id=second.document_id, scope_type="project", scope_id="project-a")
    assert comparison["grounded"] is True
    assert comparison["semantic_change_count"] >= 1
    assert any(change["kind"] == "field_change" for change in comparison["changes"])
    links = runtime.links(scope_type="project", scope_id="project-a")
    assert any(link["kind"] == "organization" and set(link["document_ids"]) == {"invoice-a", "invoice-b"} for link in links)
    assert runtime.needs_reprocessing(first, scope_type="project", scope_id="project-a", extraction_version=1) is False
    assert runtime.needs_reprocessing(first, scope_type="project", scope_id="project-a", extraction_version=2) is True
    candidates = runtime.reprocessing_candidates(scope_type="project", scope_id="project-a", runtime_version="future-stage17-runtime")
    assert {item["document_id"] for item in candidates} == {"invoice-a", "invoice-b"}


def test_stage17_fail_closed_does_not_complete_ingestion_when_semantics_fail(tmp_path: Path):
    class FailingIntelligence:
        def process(self, *args, **kwargs):
            raise RuntimeError("semantic pipeline failed")

    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    obj = store.object_store.put_bytes(INVOICE_TEXT)
    job = store.enqueue(
        object_sha256=obj.sha256,
        filename="invoice.txt",
        scope_type="project",
        scope_id="project-failure",
        declared_mime="text/plain",
        max_attempts=1,
    )
    worker = Stage17ContentWorker(store, worker_id="failing-stage17-worker", intelligence_runtime=FailingIntelligence())
    failed = worker.process_once()
    assert failed is not None
    assert failed["status"] == JobStatus.FAILED.value
    assert failed["error_code"] == "RuntimeError"
    assert store.result(job["job_id"]) is None


def test_stage17_knowledge_uses_deep_graph_and_preserves_access_classes(tmp_path: Path):
    store = UniversalKnowledgeStore(tmp_path / "knowledge.sqlite3", tmp_path / "knowledge-objects")
    owner = store.ingest(filename="owner-invoice.txt", data=INVOICE_TEXT, title="Owner invoice", access_class="owner")
    assert owner is not None
    owner_status = store.stage17_runtime.status(document_id=owner["id"], scope_type="knowledge", scope_id="owner")
    assert owner_status is not None and owner_status["state"] == "completed"
    answers = store.grounded_answer("What is the invoice number?", access_classes={"owner"}, document_id=owner["id"])
    assert len(answers) == 1
    assert answers[0]["answered"] is True
    assert answers[0]["answer"] == "INV-700"
    assert answers[0]["access_class"] == "owner"
    private_payload = INVOICE_TEXT.replace(b"INV-700", b"INV-PRIVATE")
    private = store.ingest(filename="private-invoice.txt", data=private_payload, title="Private invoice", access_class="private")
    assert private is not None
    owner_search = store.semantic_query("INV-PRIVATE", access_classes={"owner"})
    assert owner_search[0]["lexical"] == []
    private_search = store.semantic_query("INV-PRIVATE", access_classes={"private"})
    assert private_search[0]["lexical"]


def test_stage17_rejects_missing_scope_and_sha_mismatch(tmp_path: Path):
    runtime = Stage17ProductionContentRuntime(tmp_path / "stage17.sqlite3")
    document = _document("invoice-policy")
    with pytest.raises(Stage17PolicyError):
        runtime.process(document, scope_type="project", scope_id="", object_sha256=document.sha256)
    with pytest.raises(Stage17PolicyError):
        runtime.process(document, scope_type="project", scope_id="project-a", object_sha256="0" * 64)


def test_stage17_content_ingestion_router_exposes_grounded_intelligence_surface(tmp_path: Path):
    class Registry:
        def is_active(self, device_id):
            return True
        def authorize(self, device_id, scope):
            return True
    class Projects:
        def get(self, project_id):
            return {"id": project_id, "status": "active"}

    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    runtime = {"device_registry": Registry(), "base_project_store": Projects()}
    router = content_ingestion_router(runtime, store)
    paths = {route.path for route in router.routes}
    assert "/iphone/api/content-ingestion/intelligence/search" in paths
    assert "/iphone/api/content-ingestion/intelligence/answer" in paths
    assert "/iphone/api/content-ingestion/intelligence/compare" in paths
    assert "/iphone/api/content-ingestion/intelligence/{scope_type}/{scope_id}/links" in paths
    assert runtime["content_intelligence"].path == store.path
