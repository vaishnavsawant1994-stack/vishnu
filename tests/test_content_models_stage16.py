from __future__ import annotations

from pathlib import Path

import pytest

from file_intelligence import (
    ContentKind,
    ExtractionMethod,
    LocalSemanticGraph,
    SourceReference,
    Stage16DeepDocumentUnderstanding,
    Stage16DeepDocumentUnderstandingProvider,
    VishnuBlock,
    VishnuDocument,
)
from training.content_models import ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import GovernedContentFeedbackStore
from training.deep_document_understanding import (
    STAGE16_MIN_F1,
    STAGE16_SUBTASKS,
    Stage16DocumentUnderstandingCoordinator,
    VishnuStage16SemanticModel,
)


def _source_for(builder, target: str, prefix: str) -> str:
    for index in range(50000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find source for {target}")


def _document(*, document_id: str = "invoice-1", invoice_number: str = "INV-100") -> VishnuDocument:
    blocks = [
        VishnuBlock(
            kind="title",
            text="INVOICE",
            source=SourceReference(page=1, bbox=[10, 10, 190, 38]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.99,
        ),
        VishnuBlock(
            kind="key_value",
            text=f"Invoice Number: {invoice_number}",
            source=SourceReference(page=1, bbox=[10, 50, 190, 72]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.98,
            data={"key": "Invoice Number", "value": invoice_number},
        ),
        VishnuBlock(
            kind="paragraph",
            text="Acme GmbH issued this invoice. Amount due €120.00. Payment is due on 2026-11-01.",
            source=SourceReference(page=1, bbox=[10, 82, 190, 132]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.96,
        ),
        VishnuBlock(
            kind="heading",
            text="Terms",
            source=SourceReference(page=2, bbox=[10, 10, 190, 36]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.99,
        ),
        VishnuBlock(
            kind="paragraph",
            text="John Smith works for Acme GmbH. The customer shall pay within 30 days. See Section 2. https://example.com/terms",
            source=SourceReference(page=2, bbox=[10, 48, 190, 110]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.95,
        ),
        VishnuBlock(
            kind="table",
            text="Item Quantity Amount Widget 2 €120.00",
            source=SourceReference(page=2, bbox=[10, 125, 190, 220]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.94,
            data={
                "kind": "table",
                "cells": [
                    {"row": 0, "column": 0, "text": "Item", "cell_type": "header_cell"},
                    {"row": 0, "column": 1, "text": "Quantity", "cell_type": "header_cell"},
                    {"row": 0, "column": 2, "text": "Amount", "cell_type": "header_cell"},
                    {"row": 1, "column": 0, "text": "Widget", "cell_type": "body_cell"},
                    {"row": 1, "column": 1, "text": "2", "cell_type": "body_cell"},
                    {"row": 1, "column": 2, "text": "€120.00", "cell_type": "body_cell"},
                ],
            },
        ),
    ]
    return VishnuDocument(
        document_id=document_id,
        filename=f"{document_id}.pdf",
        content_kind=ContentKind.PDF,
        detected_mime="application/pdf",
        declared_mime="application/pdf",
        extension=".pdf",
        sha256=(document_id.encode("utf-8").hex() + "0" * 64)[:64],
        size_bytes=12345,
        blocks=blocks,
        ocr_version="vishnu-stage14-neural-ctc",
        layout_version="vishnu-layout/4-stage15",
    )


def test_stage16_builds_grounded_cross_page_document_graph_and_semantic_tables(tmp_path: Path):
    runtime = Stage16DeepDocumentUnderstanding()
    document = _document()
    graph = runtime.understand(document)
    public = graph.public()

    assert graph.document_type == "invoice"
    assert graph.document_type_confidence >= 0.55
    assert graph.model_versions["cross_page_context"] == "vishnu-cross-page/16.1"
    assert public["stage"] == 16
    assert public["grounded_only"] is True
    assert public["foundation_model"] is False
    assert public["contains_hidden_chain_of_thought"] is False

    assert any(section["title"] == "Terms" and section["page"] == 2 for section in graph.sections)
    assert any(field["name"] == "invoice_number" and field["value"] == "INV-100" for field in graph.fields)
    assert any(field["name"] == "amount" and "120.00" in field["value"] for field in graph.fields)
    assert any(entity["kind"] == "organization" and "Acme GmbH" in entity["canonical"] for entity in graph.entities)
    assert any(relation["predicate"] == "works_for" for relation in graph.relations)
    assert any(claim["claim_type"] == "obligation" and "shall pay" in claim["text"] for claim in graph.claims)
    assert any(reference["kind"] == "section" and reference["target"] == "2" for reference in graph.references)
    assert any(reference["kind"] == "url" for reference in graph.references)
    assert graph.tables and graph.tables[0]["semantic"] is True
    assert [column["headers"][0] for column in graph.tables[0]["columns"]] == ["Item", "Quantity", "Amount"]

    assert graph.evidence
    assert all(item["document_sha256"] == document.sha256 for item in graph.evidence)
    assert all(item["model_id"].startswith("vishnu-stage16") for item in graph.evidence)
    assert any(item["page"] == 2 and item["bbox"] for item in graph.evidence)

    answer = runtime.answer(graph, "What is the invoice number?")
    assert answer["answered"] is True
    assert answer["grounded"] is True
    assert answer["answer"] == "INV-100"
    assert answer["citations"] and answer["citations"][0]["page"] == 1

    unsupported = runtime.answer(graph, "What is the weather tomorrow?")
    assert unsupported["answered"] is False
    assert unsupported["answer"] is None
    assert unsupported["reason"] in {"unsupported_by_document", "insufficient_grounding"}

    store = LocalSemanticGraph(tmp_path / "semantic.sqlite3")
    indexed = runtime.index_into_semantic_graph(document, store, scope_type="project", scope_id="stage16")
    assert indexed["semantic_index"]["entities"] >= 1
    assert indexed["document_graph"]["document_type"] == "invoice"


def test_stage16_semantic_comparison_and_multi_document_linking():
    runtime = Stage16DeepDocumentUnderstanding()
    first = runtime.understand(_document(document_id="invoice-a", invoice_number="INV-100"))
    second = runtime.understand(_document(document_id="invoice-b", invoice_number="INV-200"))

    comparison = runtime.compare(first, second)
    assert comparison["grounded"] is True
    assert comparison["semantic_change_count"] >= 1
    assert any(change["kind"] == "field_change" and change["field"] in {"invoice_number", "invoice number"} for change in comparison["changes"])

    links = runtime.link_documents([first, second])
    assert any(link["kind"] == "organization" and len(link["document_ids"]) == 2 for link in links)

    provider = Stage16DeepDocumentUnderstandingProvider(runtime)
    result = provider.analyze(_document())
    assert result["stage"] == 16
    assert result["document_type"] == "invoice"
    provider_answer = provider.answer(_document(), "invoice number")
    assert provider_answer["answered"] is True


class BadSemanticBaseline:
    baseline_id = "stage16-bad-semantic-baseline"

    def predict(self, subtask: str, value) -> str:
        return "wrong"


def _semantic_examples(subtask: str):
    examples = {
        "stage16_document_type": (
            ("invoice", "invoice amount due bill to subtotal tax total"),
            ("contract", "agreement parties effective date terms shall contract"),
        ),
        "stage16_entity_type": (
            ("person", "person John Smith employee signer author"),
            ("organization", "organization Acme GmbH company vendor employer"),
        ),
        "stage16_field_type": (
            ("invoice_number", "invoice number INV-100 reference identifier"),
            ("amount", "amount total price currency €120.00 payable"),
        ),
        "stage16_relation_type": (
            ("works_for", "John Smith works for Acme GmbH employment relation"),
            ("payable_to", "payment payable to Acme GmbH vendor relation"),
        ),
        "stage16_claim_type": (
            ("obligation", "customer shall pay within thirty days required obligation"),
            ("financial", "total amount due is €120.00 financial claim"),
        ),
        "stage16_table_role": (
            ("header", "table header Item Quantity Amount column labels"),
            ("body", "table body Widget 2 €120.00 row values"),
        ),
        "stage16_qa_support": (
            ("supported", "question invoice number answer INV-100 evidence present supported"),
            ("unsupported", "question weather tomorrow no evidence unsupported reject"),
        ),
    }
    return examples[subtask]


def _submit_stage16_feedback(feedback: GovernedContentFeedbackStore, builder) -> None:
    for subtask in STAGE16_SUBTASKS:
        pair = _semantic_examples(subtask)
        for label, text in pair:
            for index in range(3):
                source = _source_for(builder, "train", f"{subtask}-{label}-train-{index}")
                row = feedback.submit(
                    task=ContentModelTask.DOCUMENT_CLASSIFICATION,
                    subtask=subtask,
                    language="multi",
                    source_fingerprint=source,
                    input_payload={"text": f"{text} train{index}"},
                    label=label,
                    provenance={"license": "owner-generated", "stage16": True},
                    consent_basis="owner_provided",
                )
                feedback.approve(row["feedback_id"], reviewer="owner-reviewer")
            source = _source_for(builder, "validation", f"{subtask}-{label}-validation")
            row = feedback.submit(
                task=ContentModelTask.DOCUMENT_CLASSIFICATION,
                subtask=subtask,
                language="multi",
                source_fingerprint=source,
                input_payload={"text": f"{text} validation"},
                label=label,
                provenance={"license": "owner-generated", "stage16": True},
                consent_basis="owner_provided",
            )
            feedback.approve(row["feedback_id"], reviewer="owner-reviewer")
            source = _source_for(builder, "test", f"{subtask}-{label}-test")
            row = feedback.submit(
                task=ContentModelTask.DOCUMENT_CLASSIFICATION,
                subtask=subtask,
                language="multi",
                source_fingerprint=source,
                input_payload={"text": f"{text} test"},
                label=label,
                provenance={"license": "owner-generated", "stage16": True},
                consent_basis="owner_provided",
            )
            feedback.approve(row["feedback_id"], reviewer="owner-reviewer")


def test_stage16_multihead_semantic_model_is_stage12_governed_shadow_qualified_and_owner_gated(tmp_path: Path):
    models = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    feedback = GovernedContentFeedbackStore(tmp_path / "feedback.sqlite3")
    coordinator = Stage16DocumentUnderstandingCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "stage16-evidence.sqlite3",
    )
    _submit_stage16_feedback(feedback, models.datasets)

    candidate = coordinator.train_candidate()
    assert candidate["status"] == "candidate"
    assert candidate["task"] == ContentModelTask.DOCUMENT_CLASSIFICATION.value
    assert candidate["backend_id"] == "vishnu-stage16-multihead-semantic-nb-v1"
    assert candidate["metadata"]["stage"] == 16
    assert candidate["metadata"]["deep_document_understanding"] is True
    assert candidate["metadata"]["grounded_document_qa"] is True
    assert candidate["metadata"]["foundation_model"] is False
    assert candidate["metrics"]["accuracy"] >= 0.85
    for subtask, floor in STAGE16_MIN_F1.items():
        assert candidate["metrics"][f"{subtask}_f1"] >= floor

    artifact = VishnuStage16SemanticModel(candidate["checkpoint_ref"])
    assert set(artifact.heads) == set(STAGE16_SUBTASKS)
    assert artifact.model["trained_by_vishnu"] is True
    assert artifact.model["foundation_model"] is False
    assert artifact.predict("stage16_document_type", {"text": "invoice amount due subtotal total"}, reject_below=0.0)["label"] == "invoice"
    assert artifact.predict("stage16_qa_support", {"text": "weather tomorrow no evidence unsupported reject"}, reject_below=0.0)["label"] == "unsupported"

    with pytest.raises(ValueError, match="shadow qualification"):
        coordinator.approve(candidate["model_id"], owner_id="owner")

    evidence = coordinator.shadow_qualify(candidate["model_id"], baseline=BadSemanticBaseline())
    assert evidence["passed"] is True
    assert evidence["candidate_metrics"]["accuracy"] >= 0.85
    for subtask, floor in STAGE16_MIN_F1.items():
        assert evidence["candidate_metrics"][f"{subtask}_f1"] >= floor

    approved = coordinator.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    with pytest.raises(PermissionError):
        coordinator.activate(candidate["model_id"], owner_authorized=False)
    active = coordinator.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"
    assert active["metadata"]["activation_actor"] == "release_controller"
    loaded = coordinator.active_model()
    assert loaded.predict("stage16_claim_type", {"text": "customer shall pay required obligation"}, reject_below=0.0)["label"] == "obligation"


def test_stage16_does_not_change_stage15_authority_thresholds():
    from training.content_models import ContentModelEvaluator

    rules = ContentModelEvaluator.RULES
    assert rules[ContentModelTask.OCR]["max"]["cer"] == 0.15
    assert rules[ContentModelTask.OCR]["min"]["word_accuracy"] == 0.85
    assert rules[ContentModelTask.HANDWRITING]["max"]["cer"] == 0.25
    assert rules[ContentModelTask.HANDWRITING]["min"]["word_accuracy"] == 0.70
    assert rules[ContentModelTask.LAYOUT]["min"]["f1"] == 0.85
    assert rules[ContentModelTask.TABLE]["min"]["cell_f1"] == 0.85
    assert rules[ContentModelTask.DOCUMENT_CLASSIFICATION]["min"]["accuracy"] == 0.85
