from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from file_intelligence import Stage15DocumentVisionOcrProvider
from file_intelligence.ocr import OcrUnavailable
from training.content_models import ContentDatasetBuilder, ContentModelCoordinator, ContentModelEvaluator, ContentModelTask
from training.continuous_content_models import GovernedContentFeedbackStore
from training.document_vision import (
    REAL_WORLD_CAPTURE_KINDS,
    RealWorldCorpusQualifier,
    Stage15DocumentVisionCoordinator,
    Stage15DocumentVisionRuntime,
    Stage15LayoutVectorizer,
    VishnuNeuralLayoutRecognizer,
)
from training.real_world_evidence import Stage15RealWorldQualificationCoordinator
from training.table_vision import Stage15TableCoordinator


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(20000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find source for {target}")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("L").save(buffer, format="PNG")
    return buffer.getvalue()


def _layout_image(label: str, variant: int = 0) -> bytes:
    image = Image.new("L", (160, 80), 255)
    draw = ImageDraw.Draw(image)
    shift = variant % 3
    if label == "title":
        draw.rectangle((8, 8 + shift, 150, 22 + shift), fill=0)
        draw.rectangle((24, 29 + shift, 136, 34 + shift), fill=0)
    elif label == "paragraph":
        for row in range(8 + shift, 70, 9):
            draw.rectangle((8, row, 146 - (row % 3) * 8, row + 2), fill=0)
    elif label == "table":
        for x in (8, 55, 102, 151):
            draw.line((x, 5, x, 73), fill=0, width=2)
        for y in (5, 27, 49, 73):
            draw.line((8, y, 151, y), fill=0, width=2)
    elif label == "header_cell":
        draw.rectangle((4, 4, 155, 75), outline=0, width=2)
        draw.rectangle((5, 5, 154, 20 + shift), fill=0)
    elif label == "body_cell":
        draw.rectangle((4, 4, 155, 75), outline=0, width=1)
        for row in (25 + shift, 43 + shift, 60 + shift):
            draw.line((15, row, 140, row), fill=0, width=2)
    else:
        raise AssertionError(label)
    return _png(image)


def _layout_payload(label: str, variant: int = 0) -> dict:
    boxes = {
        "title": (10, 8, 190, 45),
        "paragraph": (15, 80, 185, 180),
        "table": (20, 190, 180, 290),
        "header_cell": (20, 20, 180, 70),
        "body_cell": (20, 80, 180, 160),
    }
    return Stage15LayoutVectorizer.payload(
        _layout_image(label, variant),
        bbox=boxes[label],
        page_width=200,
        page_height=320,
    )


def _make_stage(tmp_path):
    models = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    feedback = GovernedContentFeedbackStore(tmp_path / "feedback.sqlite3")
    layout = Stage15DocumentVisionCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "layout-evidence.sqlite3",
    )
    table = Stage15TableCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "table-evidence.sqlite3",
    )
    return models, feedback, layout, table


def _approve(
    feedback: GovernedContentFeedbackStore,
    *,
    task: ContentModelTask,
    subtask: str,
    source: str,
    label: str,
    payload: dict,
):
    row = feedback.submit(
        task=task,
        subtask=subtask,
        language="multi",
        source_fingerprint=source,
        input_payload=payload,
        label=label,
        provenance={"license": "owner-generated", "approved_source": True},
        consent_basis="owner_provided",
    )
    feedback.approve(row["feedback_id"], reviewer="owner-reviewer")


class BadLayoutBaseline:
    baseline_id = "stage15-bad-layout-baseline"

    def predict(self, payload: dict) -> str:
        return "figure"


class BadTableBaseline:
    baseline_id = "stage15-bad-table-baseline"

    def predict(self, payload: dict) -> str:
        return "non_cell"


def test_stage15_real_world_gate_rejects_synthetic_and_requires_provenance(tmp_path):
    qualifier = RealWorldCorpusQualifier()
    synthetic = qualifier.qualify(
        [
            {
                "task": "ocr",
                "truth": "invoice",
                "prediction": "invoice",
                "accepted": True,
                "should_accept": True,
                "confidence": 0.99,
                "capture_kind": "scan",
                "source_fingerprint": "synthetic-1",
                "consent_basis": "synthetic",
                "split": "test",
                "provenance": {
                    "real_world": False,
                    "synthetic": True,
                    "capture_kind": "scan",
                    "license": "generated",
                },
            }
        ]
    )
    assert synthetic.qualified is False
    assert synthetic.public()["real_world_corpus_qualified"] is False
    assert any("real_world_provenance_required" in reason for reason in synthetic.reasons)

    coordinator = Stage15RealWorldQualificationCoordinator(tmp_path / "real-world.jsonl")
    recorded = coordinator.qualify(
        [
            {
                "task": "ocr",
                "truth": "invoice",
                "prediction": "invoice",
                "accepted": True,
                "should_accept": True,
                "confidence": 0.99,
                "source_fingerprint": "generated-only",
                "consent_basis": "synthetic",
                "split": "test",
                "provenance": {
                    "real_world": False,
                    "synthetic": True,
                    "capture_kind": "photo",
                    "license": "generated",
                },
            }
        ]
    )
    assert recorded["report"]["real_world_corpus_qualified"] is False
    with pytest.raises(ValueError, match="synthetic evidence cannot satisfy"):
        coordinator.assert_qualified()


def test_stage15_real_world_gate_can_validate_genuine_evidence_contract_without_claiming_repo_corpus():
    # Metadata-shaped records test gate logic only; they do not make this repo a genuine corpus.
    rows = [
        {
            "task": "ocr",
            "truth": "scan text",
            "prediction": "scan text",
            "accepted": True,
            "should_accept": True,
            "confidence": 0.99,
            "source_fingerprint": "real-scan-a",
            "consent_basis": "owner_provided",
            "split": "train",
            "provenance": {"real_world": True, "synthetic": False, "capture_kind": "scan", "ownership_basis": "owner-captured"},
        },
        {
            "task": "ocr",
            "truth": "photo text",
            "prediction": "photo text",
            "accepted": True,
            "should_accept": True,
            "confidence": 0.98,
            "source_fingerprint": "real-photo-b",
            "consent_basis": "owner_provided",
            "split": "validation",
            "provenance": {"real_world": True, "synthetic": False, "capture_kind": "photo", "ownership_basis": "owner-captured"},
        },
        {
            "task": "ocr",
            "truth": "screen text",
            "prediction": "screen text",
            "accepted": True,
            "should_accept": True,
            "confidence": 0.98,
            "source_fingerprint": "real-screen-c",
            "consent_basis": "owner_provided",
            "split": "test",
            "provenance": {"real_world": True, "synthetic": False, "capture_kind": "screenshot", "ownership_basis": "owner-captured"},
        },
        {
            "task": "handwriting",
            "truth": "written",
            "prediction": "written",
            "accepted": True,
            "should_accept": True,
            "confidence": 0.97,
            "source_fingerprint": "real-hand-d",
            "consent_basis": "owner_provided",
            "split": "test",
            "provenance": {"real_world": True, "synthetic": False, "capture_kind": "handwriting", "ownership_basis": "owner-captured"},
        },
    ]
    report = RealWorldCorpusQualifier().qualify(rows)
    assert report.qualified is True
    assert set(report.capture_counts) == set(REAL_WORLD_CAPTURE_KINDS)
    assert report.ocr_metrics["cer"] <= 0.15
    assert report.handwriting_metrics["cer"] <= 0.25


def test_stage15_neural_layout_is_governed_shadowed_and_owner_gated(tmp_path):
    models, feedback, stage, _ = _make_stage(tmp_path)
    train_sources = [
        _source_for(models.datasets, "train", f"stage15-layout-train-{index}")
        for index in range(4)
    ]
    validation_source = _source_for(models.datasets, "validation", "stage15-layout-validation")
    test_source = _source_for(models.datasets, "test", "stage15-layout-test")
    labels = ("title", "paragraph", "table")

    for source_index, source in enumerate(train_sources):
        for label in labels:
            _approve(
                feedback,
                task=ContentModelTask.LAYOUT,
                subtask="document_layout",
                source=source,
                label=label,
                payload=_layout_payload(label, source_index),
            )
    for label in labels:
        _approve(feedback, task=ContentModelTask.LAYOUT, subtask="document_layout", source=validation_source, label=label, payload=_layout_payload(label, 7))
        _approve(feedback, task=ContentModelTask.LAYOUT, subtask="document_layout", source=test_source, label=label, payload=_layout_payload(label, 8))

    candidate = stage.train_candidate(languages=("multi",))
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-stage15-neural-layout-mlp-v1"
    assert candidate["metadata"]["stage"] == 15
    assert candidate["metadata"]["neural_layout_classifier"] is True
    assert candidate["metadata"]["stage14_ctc_text_backend"] is True
    assert candidate["metadata"]["foundation_model"] is False
    assert candidate["metadata"]["real_world_corpus_qualified"] is False
    assert candidate["metrics"]["f1"] >= 0.85

    artifact = json.loads((Path(candidate["checkpoint_ref"]) / "model.json").read_text())
    assert artifact["model_type"] == "vishnu-stage15-neural-document-layout"
    assert artifact["architecture"]["family"] == "visual_spatial_mlp"
    recognizer = VishnuNeuralLayoutRecognizer(candidate["checkpoint_ref"])
    assert recognizer.predict_payload(_layout_payload("table", 9), reject_below=0.0)["label"] == "table"

    with pytest.raises(ValueError, match="successful shadow qualification"):
        stage.approve(candidate["model_id"], owner_id="owner")
    evidence = stage.shadow_qualify(candidate["model_id"], baseline=BadLayoutBaseline())
    assert evidence["passed"] is True
    approved = stage.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    with pytest.raises(PermissionError):
        stage.activate(candidate["model_id"], owner_authorized=False)
    active = stage.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"


def test_stage15_neural_table_cell_model_keeps_separate_table_authority(tmp_path):
    models, feedback, _, table = _make_stage(tmp_path)
    train_sources = [
        _source_for(models.datasets, "train", f"stage15-table-train-{index}")
        for index in range(4)
    ]
    validation_source = _source_for(models.datasets, "validation", "stage15-table-validation")
    test_source = _source_for(models.datasets, "test", "stage15-table-test")
    labels = ("header_cell", "body_cell")

    for source_index, source in enumerate(train_sources):
        for label in labels:
            _approve(feedback, task=ContentModelTask.TABLE, subtask="table_cells", source=source, label=label, payload=_layout_payload(label, source_index))
    for label in labels:
        _approve(feedback, task=ContentModelTask.TABLE, subtask="table_cells", source=validation_source, label=label, payload=_layout_payload(label, 7))
        _approve(feedback, task=ContentModelTask.TABLE, subtask="table_cells", source=test_source, label=label, payload=_layout_payload(label, 8))

    candidate = table.train_candidate(languages=("multi",))
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-stage15-neural-table-cell-mlp-v1"
    assert candidate["metadata"]["stage"] == 15
    assert candidate["metadata"]["neural_table_cell_classifier"] is True
    assert candidate["metrics"]["cell_f1"] >= 0.85
    with pytest.raises(ValueError, match="successful shadow qualification"):
        table.approve(candidate["model_id"], owner_id="owner")
    evidence = table.shadow_qualify(candidate["model_id"], baseline=BadTableBaseline())
    assert evidence["passed"] is True
    approved = table.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"


class AlwaysTableLayout:
    def predict_payload(self, payload: dict, *, reject_below=None):
        return {"label": "table", "raw_label": "table", "confidence": 0.99, "accepted": True, "rejection_reason": None, "alternatives": []}


def test_stage15_page_runtime_preserves_bbox_reading_order_and_structures():
    page = Image.new("L", (240, 180), 255)
    draw = ImageDraw.Draw(page)
    for y in (20, 55, 90):
        draw.rectangle((15, y, 100, y + 8), fill=0)
        draw.rectangle((135, y, 220, y + 8), fill=0)
    runtime = Stage15DocumentVisionRuntime(AlwaysTableLayout())
    result = runtime.analyze(_png(page))
    assert result["layout_version"] == "vishnu-layout/4-stage15"
    assert result["stage14_ctc_text_backend"] is True
    assert result["real_world_corpus_qualified"] is False
    assert result["foundation_model"] is False
    assert result["regions"]
    assert all(len(region["bbox"]) == 4 for region in result["regions"])
    assert all(region["structure"]["kind"] == "table" for region in result["regions"])
    assert [region["reading_order"] for region in result["regions"]] == list(range(len(result["regions"])))


class FakeRuntime:
    def analyze(self, image_bytes: bytes):
        return {
            "regions": [
                {"label": "paragraph", "confidence": 0.96, "bbox": [1, 2, 20, 12], "normalized_bbox": [0.01, 0.02, 0.2, 0.12], "reading_order": 0, "text": "hello", "text_confidence": 0.93, "accepted": True, "rejection_reason": None, "structure": {}},
                {"label": "figure", "confidence": 0.90, "bbox": [3, 20, 40, 60], "normalized_bbox": [0.03, 0.2, 0.4, 0.6], "reading_order": 1, "text": "", "text_confidence": 0.0, "accepted": True, "rejection_reason": None, "structure": {"kind": "figure"}},
            ],
            "tables": [],
        }


def test_stage15_provider_uses_existing_local_ocr_contract_and_does_not_invent_text():
    provider = Stage15DocumentVisionOcrProvider(FakeRuntime())
    rows = provider.extract(_png(Image.new("L", (64, 64), 255)))
    assert provider.external is False
    assert len(rows) == 1
    assert rows[0]["text"] == "hello"
    assert rows[0]["confidence"] == 0.93
    assert rows[0]["metadata"]["stage15_document_vision"] is True
    assert rows[0]["metadata"]["network_used"] is False


class EmptyRegistry:
    def active(self, task):
        return None


def test_stage15_provider_fails_closed_without_owner_activated_models():
    with pytest.raises(OcrUnavailable, match="owner-activated Vishnu layout model"):
        Stage15DocumentVisionOcrProvider.from_active_registry(EmptyRegistry())


def test_stage15_does_not_weaken_stage9_thresholds():
    assert ContentModelEvaluator.RULES[ContentModelTask.OCR] == {"max": {"cer": 0.15}, "min": {"word_accuracy": 0.85}}
    assert ContentModelEvaluator.RULES[ContentModelTask.HANDWRITING] == {"max": {"cer": 0.25}, "min": {"word_accuracy": 0.70}}
    assert ContentModelEvaluator.RULES[ContentModelTask.LAYOUT] == {"min": {"f1": 0.85}}
    assert ContentModelEvaluator.RULES[ContentModelTask.TABLE] == {"min": {"cell_f1": 0.85}}
