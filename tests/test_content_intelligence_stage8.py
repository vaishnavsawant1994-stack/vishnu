from __future__ import annotations

from file_intelligence.models import ExtractionMethod, SourceReference, VishnuBlock
from file_intelligence.semantic import LocalSemanticGraph, extract_entities


def block(text, *, page=1, kind="text", data=None):
    return VishnuBlock(kind, text, SourceReference(page=page), ExtractionMethod.NATIVE, 0.99, data)


def test_semantic_entity_extraction_is_local_and_deterministic():
    entities = extract_entities("Alice Smith works at Acme Technologies on 2026-10-12. Email alice@example.com. Total €1,250.00")
    pairs = {(item["kind"], item["normalized"]) for item in entities}
    assert ("person", "alice smith") in pairs
    assert any(kind == "organization" and "acme technologies" in value for kind, value in pairs)
    assert ("date", "2026-10-12") in pairs
    assert ("email", "alice@example.com") in pairs
    assert ("money", "€1250.00") in pairs


def test_graph_links_documents_and_preserves_exact_citations(tmp_path):
    graph = LocalSemanticGraph(tmp_path / "project.sqlite3")
    graph.index_blocks(document_id="doc-a", title="Contract", scope_type="project", scope_id="p1", checksum="a", blocks=[block("Alice Smith works at Acme Technologies on 2026-10-12.", page=2)])
    graph.index_blocks(document_id="doc-b", title="Meeting", scope_type="project", scope_id="p1", checksum="b", blocks=[block("Alice Smith approved the launch on 2026-10-13.", page=5)])
    links = graph.cross_document_links(scope_type="project", scope_id="p1")
    alice = next(item for item in links if item["canonical"] == "Alice Smith")
    assert alice["document_count"] == 2
    assert {mention["citation"]["document_id"] for mention in alice["mentions"]} == {"doc-a", "doc-b"}
    assert {mention["citation"]["source"]["page"] for mention in alice["mentions"]} == {2, 5}


def test_graph_scope_isolation_prevents_cross_project_leakage(tmp_path):
    graph = LocalSemanticGraph(tmp_path / "project.sqlite3")
    graph.index_blocks(document_id="a", title="A", scope_type="project", scope_id="p1", checksum="a", blocks=[block("Alice Smith works at Acme Technologies")])
    graph.index_blocks(document_id="b", title="B", scope_type="project", scope_id="p2", checksum="b", blocks=[block("Alice Smith works at Other Systems")])
    p1 = graph.query("Alice Smith", scope_type="project", scope_id="p1")
    p2 = graph.query("Alice Smith", scope_type="project", scope_id="p2")
    assert all(rel["scope_id"] == "p1" for rel in p1["relations"])
    assert all(rel["scope_id"] == "p2" for rel in p2["relations"])
    assert "Other Systems" not in str(p1)
    assert "Acme Technologies" not in str(p2)


def test_structured_field_conflicts_are_reported_as_evidence_not_auto_resolved(tmp_path):
    graph = LocalSemanticGraph(tmp_path / "knowledge.sqlite3")
    first = block("Status: active", kind="key_value", data={"key": "Status", "value": "active"})
    second = block("Status: cancelled", kind="key_value", data={"key": "Status", "value": "cancelled"})
    graph.index_blocks(document_id="doc-a", title="Record A", scope_type="knowledge", scope_id="owner", checksum="a", blocks=[first])
    graph.index_blocks(document_id="doc-a", title="Record A", scope_type="knowledge", scope_id="owner", checksum="b", blocks=[first, second])
    conflicts = graph.contradictions(scope_type="knowledge", scope_id="owner")
    assert len(conflicts) == 1
    assert conflicts[0]["predicate"] == "status"
    assert {item["object"] for item in conflicts[0]["variants"]} == {"active", "cancelled"}


def test_semantic_timeline_orders_normalized_dates_with_sources(tmp_path):
    graph = LocalSemanticGraph(tmp_path / "project.sqlite3")
    graph.index_blocks(document_id="late", title="Late", scope_type="project", scope_id="p1", checksum="1", blocks=[block("Milestone on 2026-12-01", page=3)])
    graph.index_blocks(document_id="early", title="Early", scope_type="project", scope_id="p1", checksum="2", blocks=[block("Kickoff on 2026-01-05", page=1)])
    timeline = graph.timeline(scope_type="project", scope_id="p1")
    assert [item["date"] for item in timeline] == ["2026-01-05", "2026-12-01"]
    assert timeline[0]["citation"]["source"]["page"] == 1
