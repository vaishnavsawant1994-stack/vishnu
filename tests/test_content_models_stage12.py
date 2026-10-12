from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from training.content_models import ContentDatasetBuilder, ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import (
    ContinuousContentModelCoordinator,
    FeedbackPolicyError,
    GovernedContentFeedbackStore,
    SequenceRasterVectorizer,
)


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(10000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find {target} source")


def _image_bytes(label_index: int, variant: int) -> bytes:
    image = Image.new("L", (120, 40), 255)
    draw = ImageDraw.Draw(image)
    if label_index == 0:
        width = 6 + variant * 2
        draw.rectangle((20, 5, 20 + width, 35), fill=0)
        draw.rectangle((55, 8, 60, 32), fill=0)
    else:
        height = 5 + variant * 2
        draw.rectangle((10, 12, 105, 12 + height), fill=0)
        draw.rectangle((30, 28, 88, 32), fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_stage(tmp_path):
    models = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    feedback = GovernedContentFeedbackStore(tmp_path / "feedback.sqlite3")
    stage = ContinuousContentModelCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "cycle_evidence.sqlite3",
    )
    return models, feedback, stage


def _approve_raster_dataset(
    feedback: GovernedContentFeedbackStore,
    builder: ContentDatasetBuilder,
    *,
    task: ContentModelTask,
    subtask: str,
    kind: str,
    labels: tuple[str, str],
    languages: tuple[str, str],
):
    vectorizer = SequenceRasterVectorizer(width=64, height=24)
    ids = []
    for variant, split in enumerate(("train", "validation", "test")):
        source = _source_for(builder, split, f"{subtask}-{split}")
        for label_index, (label, language) in enumerate(zip(labels, languages)):
            payload = vectorizer.payload(_image_bytes(label_index, variant), kind=kind)
            row = feedback.submit(
                task=task,
                subtask=subtask,
                language=language,
                source_fingerprint=source,
                input_payload=payload,
                label=label,
                provenance={"license": "owner-generated", "approved_source": True},
                consent_basis="owner_provided",
            )
            ids.append(row["feedback_id"])
    for feedback_id in ids:
        feedback.approve(feedback_id, reviewer="owner-reviewer")
    return ids


class BadTextBaseline:
    baseline_id = "test-bad-text-baseline"

    def predict(self, image_bytes: bytes) -> str:
        return "incorrect"


class BadFeatureBaseline:
    baseline_id = "test-bad-feature-baseline"

    def predict(self, payload: dict) -> str:
        return "incorrect"


def test_feedback_is_quarantined_until_explicit_review_and_deduplicated(tmp_path):
    _, feedback, _ = _make_stage(tmp_path)
    payload = {"kind": "numeric_feature_vector", "features": [0.1, 0.2]}
    first = feedback.submit(
        task=ContentModelTask.LAYOUT,
        subtask="region_role",
        language="en",
        source_fingerprint="source-a",
        input_payload=payload,
        label="heading",
        provenance={"license": "owner-generated"},
        consent_basis="owner_provided",
    )
    second = feedback.submit(
        task=ContentModelTask.LAYOUT,
        subtask="region_role",
        language="en",
        source_fingerprint="source-a",
        input_payload=payload,
        label="heading",
        provenance={"license": "owner-generated"},
        consent_basis="owner_provided",
    )
    assert first["feedback_id"] == second["feedback_id"]
    assert feedback.stats()["pending"] == 1
    assert feedback.approved_samples(ContentModelTask.LAYOUT) == []
    approved = feedback.approve(first["feedback_id"], reviewer="owner-reviewer")
    assert approved["status"] == "approved"
    samples = feedback.approved_samples(ContentModelTask.LAYOUT)
    assert len(samples) == 1
    assert samples[0]["provenance"]["approved_for_training"] is True
    assert samples[0]["provenance"]["reviewed_by"] == "owner-reviewer"


def test_feedback_policy_requires_consent_and_ownership_basis(tmp_path):
    _, feedback, _ = _make_stage(tmp_path)
    with pytest.raises(FeedbackPolicyError):
        feedback.submit(
            task=ContentModelTask.OCR,
            subtask="line_ocr",
            language="en",
            source_fingerprint="source",
            input_payload={"features": [1.0]},
            label="hello",
            provenance={},
            consent_basis="owner_provided",
        )
    with pytest.raises(FeedbackPolicyError):
        feedback.submit(
            task=ContentModelTask.OCR,
            subtask="line_ocr",
            language="en",
            source_fingerprint="source",
            input_payload={"features": [1.0]},
            label="hello",
            provenance={"license": "owner-generated"},
            consent_basis="unknown",
        )


def test_multilingual_word_line_model_is_really_trained_shadowed_and_owner_gated(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    _approve_raster_dataset(
        feedback,
        models.datasets,
        task=ContentModelTask.OCR,
        subtask="multilingual_line_ocr",
        kind="word_line_raster",
        labels=("hello", "नमस्ते"),
        languages=("en", "hi"),
    )
    candidate = stage.train_sequence_candidate(
        task=ContentModelTask.OCR,
        subtask="multilingual_line_ocr",
        languages=("en", "hi"),
    )
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-word-line-prototype-v1"
    assert candidate["metadata"]["trained_by_vishnu"] is True
    assert candidate["metadata"]["open_vocabulary"] is False
    assert candidate["metrics"]["word_accuracy"] >= 0.85
    with pytest.raises(ValueError, match="shadow qualification"):
        stage.approve(candidate["model_id"], owner_id="owner")
    evidence = stage.shadow_sequence(candidate["model_id"], baseline=BadTextBaseline())
    assert evidence["passed"] is True
    assert evidence["candidate_metrics"]["cer"] <= 0.15
    approved = stage.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    active = stage.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"


def test_handwriting_line_model_uses_separate_governed_task(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    _approve_raster_dataset(
        feedback,
        models.datasets,
        task=ContentModelTask.HANDWRITING,
        subtask="handwriting_line",
        kind="handwriting_line_raster",
        labels=("approved", "rejected"),
        languages=("en", "en"),
    )
    candidate = stage.train_sequence_candidate(
        task=ContentModelTask.HANDWRITING,
        subtask="handwriting_line",
        languages=("en",),
    )
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-handwriting-line-prototype-v1"
    assert candidate["metrics"]["word_accuracy"] >= 0.70
    evidence = stage.shadow_sequence(candidate["model_id"], baseline=BadTextBaseline())
    assert evidence["passed"] is True


def _approve_feature_dataset(feedback, builder, *, task, subtask, labels, centers):
    ids = []
    for variant, split in enumerate(("train", "validation", "test")):
        source = _source_for(builder, split, f"{subtask}-{split}")
        for label, center in zip(labels, centers):
            payload = {
                "kind": "numeric_feature_vector",
                "features": [round(float(value) + variant * 0.01, 4) for value in center],
            }
            row = feedback.submit(
                task=task,
                subtask=subtask,
                language="und",
                source_fingerprint=source,
                input_payload=payload,
                label=label,
                provenance={"license": "owner-generated"},
                consent_basis="owner_provided",
            )
            ids.append(row["feedback_id"])
    for feedback_id in ids:
        feedback.approve(feedback_id, reviewer="owner-reviewer")


def test_layout_and_table_models_train_and_shadow_against_baselines(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    _approve_feature_dataset(
        feedback,
        models.datasets,
        task=ContentModelTask.LAYOUT,
        subtask="region_role",
        labels=("heading", "paragraph"),
        centers=((0.1, 0.1, 0.2), (0.9, 0.8, 0.9)),
    )
    layout = stage.train_feature_candidate(task=ContentModelTask.LAYOUT, subtask="region_role")
    assert layout["status"] == "candidate"
    assert layout["metrics"]["f1"] >= 0.85
    layout_evidence = stage.shadow_features(layout["model_id"], baseline=BadFeatureBaseline())
    assert layout_evidence["passed"] is True

    _approve_feature_dataset(
        feedback,
        models.datasets,
        task=ContentModelTask.TABLE,
        subtask="table_structure",
        labels=("grid", "key_value"),
        centers=((0.05, 0.15, 0.1), (0.85, 0.9, 0.8)),
    )
    table = stage.train_feature_candidate(task=ContentModelTask.TABLE, subtask="table_structure")
    assert table["status"] == "candidate"
    assert table["metrics"]["cell_f1"] >= 0.85
    table_evidence = stage.shadow_features(table["model_id"], baseline=BadFeatureBaseline())
    assert table_evidence["passed"] is True


def test_prediction_corrections_reenter_quarantine_not_training_automatically(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    correction = stage.record_prediction_correction(
        model_id="vishnu-ocr-example",
        task=ContentModelTask.OCR,
        subtask="multilingual_line_ocr",
        language="de",
        source_fingerprint=_source_for(models.datasets, "train", "correction"),
        input_payload={"kind": "word_line_raster", "features": [0.1, 0.2], "width": 2, "height": 1},
        predicted_label="Haus",
        corrected_label="Maus",
        provenance={"license": "owner-generated"},
        consent_basis="owner_provided",
    )
    assert correction["status"] == "pending"
    assert feedback.approved_samples(ContentModelTask.OCR, subtask="multilingual_line_ocr") == []
    approved = feedback.approve(correction["feedback_id"], reviewer="owner-reviewer")
    assert approved["status"] == "approved"
    sample = feedback.approved_samples(ContentModelTask.OCR, subtask="multilingual_line_ocr")[0]
    assert sample["provenance"]["model_id"] == "vishnu-ocr-example"
    assert sample["provenance"]["predicted_label"] == "Haus"
