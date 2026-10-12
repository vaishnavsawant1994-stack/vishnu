from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from training.content_models import ContentDatasetBuilder, ContentModelCoordinator, ContentModelEvaluator, ContentModelTask
from training.continuous_content_models import GovernedContentFeedbackStore
from training.neural_ocr import Stage14NeuralOCRCoordinator, VishnuNeuralOpenVocabularyRecognizer
from training.open_vocabulary_ocr import OpenVocabularyLineVectorizer, UnicodeGraphemeTokenizer


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(20000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find source for {target}")


def _draw_token(draw: ImageDraw.ImageDraw, token: str, x: int, top: int = 4) -> None:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    left = x + 2
    right = x + 14
    bottom = top + 20
    draw.rectangle((left, top, right, bottom), outline=0, width=1)
    for index in range(8):
        if digest[index] & 1:
            y = top + 2 + index * 2
            if digest[index] & 2:
                draw.rectangle((left + 2, y, right - 2, y + 1), fill=0)
            else:
                draw.rectangle((left + 2, y, left + 7, y + 1), fill=0)


def _line_image(text: str) -> bytes:
    tokens = UnicodeGraphemeTokenizer.tokenize(text)
    width = 8
    for token in tokens:
        width += 16 if token != " " else 14
    image = Image.new("L", (max(width, 24), 30), 255)
    draw = ImageDraw.Draw(image)
    x = 4
    for token in tokens:
        if token == " ":
            x += 14
            continue
        _draw_token(draw, token, x)
        x += 16
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
    stage = Stage14NeuralOCRCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "stage14_evidence.sqlite3",
    )
    return models, feedback, stage


def _approve_line(
    feedback: GovernedContentFeedbackStore,
    *,
    task: ContentModelTask,
    subtask: str,
    language: str,
    source: str,
    text: str,
):
    raw = _line_image(text)
    vectorizer = OpenVocabularyLineVectorizer(height=32)
    payload = vectorizer.payload(
        raw,
        kind="open_vocabulary_line" if task is ContentModelTask.OCR else "open_vocabulary_handwriting_line",
    )
    row = feedback.submit(
        task=task,
        subtask=subtask,
        language=language,
        source_fingerprint=source,
        input_payload=payload,
        label=text,
        provenance={"license": "owner-generated", "approved_source": True},
        consent_basis="owner_provided",
    )
    feedback.approve(row["feedback_id"], reviewer="owner-reviewer")
    return row


class BadLineBaseline:
    baseline_id = "stage14-test-bad-baseline"

    def predict(self, image_bytes: bytes) -> str:
        return "xxxx"


def test_stage14_neural_ocr_trains_open_vocabulary_candidate_and_keeps_owner_gate(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    train_source = _source_for(models.datasets, "train", "stage14-ocr-train")
    validation_source = _source_for(models.datasets, "validation", "stage14-ocr-validation")
    test_source = _source_for(models.datasets, "test", "stage14-ocr-test")

    for text in ("AB", "BA", "AΩ", "ΩB", "B A"):
        _approve_line(
            feedback,
            task=ContentModelTask.OCR,
            subtask="neural_line_ocr",
            language="multi",
            source=train_source,
            text=text,
        )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="neural_line_ocr",
        language="multi",
        source=validation_source,
        text="BΩA",
    )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="neural_line_ocr",
        language="multi",
        source=test_source,
        text="ΩAB",
    )

    candidate = stage.train_candidate(
        task=ContentModelTask.OCR,
        subtask="neural_line_ocr",
        languages=("multi",),
    )
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-neural-grapheme-ocr-v1"
    assert candidate["metadata"]["stage"] == 14
    assert candidate["metadata"]["neural_encoder"] is True
    assert candidate["metadata"]["foundation_model"] is False
    assert candidate["metadata"]["sequence_ctc_ready"] is False
    assert candidate["metadata"]["lexicon_required"] is False
    assert candidate["metrics"]["cer"] <= 0.15
    assert candidate["metrics"]["word_accuracy"] >= 0.85

    artifact = json.loads((Path(candidate["checkpoint_ref"]) / "model.json").read_text())
    assert artifact["architecture"]["family"] == "mlp_visual_grapheme_encoder"
    assert artifact["architecture"]["decoder"] == "stage13_geometry_sequence_v1"
    assert artifact["trained_by_vishnu"] is True
    assert artifact["open_vocabulary"] is True

    recognizer = VishnuNeuralOpenVocabularyRecognizer(candidate["checkpoint_ref"])
    vectorizer = OpenVocabularyLineVectorizer(height=32)
    unseen = vectorizer.payload(_line_image("AΩB"))
    assert recognizer.predict_payload(unseen)[0] == "AΩB"
    assert recognizer.predict_payload(vectorizer.payload(_line_image("AB BA")))[0] == "AB BA"

    with pytest.raises(ValueError, match="Stage 14 model requires successful shadow qualification"):
        stage.approve(candidate["model_id"], owner_id="owner")

    evidence = stage.shadow_qualify(candidate["model_id"], baseline=BadLineBaseline())
    assert evidence["passed"] is True
    approved = stage.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    active = stage.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"


def test_stage14_handwriting_is_a_separate_neural_task_and_artifact(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    train_source = _source_for(models.datasets, "train", "stage14-hw-train")
    validation_source = _source_for(models.datasets, "validation", "stage14-hw-validation")
    test_source = _source_for(models.datasets, "test", "stage14-hw-test")

    for text in ("XY", "YX", "XΩ", "ΩY"):
        _approve_line(
            feedback,
            task=ContentModelTask.HANDWRITING,
            subtask="neural_handwriting_line",
            language="multi",
            source=train_source,
            text=text,
        )
    _approve_line(
        feedback,
        task=ContentModelTask.HANDWRITING,
        subtask="neural_handwriting_line",
        language="multi",
        source=validation_source,
        text="YΩX",
    )
    _approve_line(
        feedback,
        task=ContentModelTask.HANDWRITING,
        subtask="neural_handwriting_line",
        language="multi",
        source=test_source,
        text="ΩXY",
    )

    candidate = stage.train_candidate(
        task=ContentModelTask.HANDWRITING,
        subtask="neural_handwriting_line",
        languages=("multi",),
    )
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-neural-grapheme-handwriting-v1"
    assert candidate["metadata"]["stage"] == 14
    assert candidate["metadata"]["neural_encoder"] is True
    assert candidate["metrics"]["cer"] <= 0.25
    assert candidate["metrics"]["word_accuracy"] >= 0.70
    assert stage.shadow_qualify(candidate["model_id"], baseline=BadLineBaseline())["passed"] is True


def test_stage14_does_not_weaken_stage9_fail_closed_thresholds():
    assert ContentModelEvaluator.RULES[ContentModelTask.OCR] == {
        "max": {"cer": 0.15},
        "min": {"word_accuracy": 0.85},
    }
    assert ContentModelEvaluator.RULES[ContentModelTask.HANDWRITING] == {
        "max": {"cer": 0.25},
        "min": {"word_accuracy": 0.70},
    }
