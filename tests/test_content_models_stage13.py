from __future__ import annotations

import base64
import hashlib
import io

import pytest
from PIL import Image, ImageDraw

from training.content_models import ContentDatasetBuilder, ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import GovernedContentFeedbackStore
from training.open_vocabulary_ocr import (
    OpenVocabularyLineVectorizer,
    Stage13OpenVocabularyCoordinator,
    UnicodeGraphemeTokenizer,
    VishnuOpenVocabularyRecognizer,
    VishnuPageSequenceRecognizer,
)


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(20000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find source for {target}")


def _graphemes(text: str) -> list[str]:
    return UnicodeGraphemeTokenizer.tokenize(text)


def _draw_token(draw: ImageDraw.ImageDraw, token: str, x: int, top: int = 4) -> None:
    # Deterministic visual alphabet independent of host fonts. It lets the test
    # prove sequence composition and Unicode labels without requiring a font.
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    left = x + 2
    right = x + 14
    bottom = top + 20
    draw.rectangle((left, top, left + 2, bottom), fill=0)
    if digest[0] & 1:
        draw.rectangle((left, top, right, top + 2), fill=0)
    else:
        draw.rectangle((left, bottom - 2, right, bottom), fill=0)
    if digest[1] & 1:
        draw.rectangle((right - 2, top + 3, right, bottom), fill=0)
    if digest[2] & 1:
        draw.rectangle((left + 2, top + 9, right - 2, top + 11), fill=0)
    if digest[3] & 1:
        draw.rectangle((left + 6, top + 3, left + 8, bottom - 3), fill=0)


def _line_image(text: str) -> bytes:
    tokens = _graphemes(text)
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
    stage = Stage13OpenVocabularyCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "stage13_evidence.sqlite3",
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
    baseline_id = "stage13-test-bad-line-baseline"

    def predict(self, image_bytes: bytes) -> str:
        return "xxxx"


def test_unicode_grapheme_tokenizer_keeps_combining_marks_and_spaces_stable():
    assert UnicodeGraphemeTokenizer.tokenize(" cafe\u0301  Ω ") == ["c", "a", "f", "é", " ", "Ω"]
    assert " " not in UnicodeGraphemeTokenizer.vocabulary(["ab cd", "Ωa"])
    assert set(UnicodeGraphemeTokenizer.vocabulary(["ab", "Ωa"])) == {"a", "b", "Ω"}


def test_variable_width_line_vectorizer_preserves_internal_space(tmp_path):
    vectorizer = OpenVocabularyLineVectorizer(height=32)
    one = vectorizer.payload(_line_image("AB"))
    two = vectorizer.payload(_line_image("AB BA"))
    assert one["kind"] == "open_vocabulary_line"
    assert two["width"] > one["width"]
    assert len(two["pixels"]) == two["width"] * two["height"]
    assert base64.b64decode(two["image_png_b64"], validate=True)


def test_open_vocabulary_model_composes_unseen_word_and_is_owner_gated(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    train_source = _source_for(models.datasets, "train", "stage13-train")
    validation_source = _source_for(models.datasets, "validation", "stage13-validation")
    test_source = _source_for(models.datasets, "test", "stage13-test")

    # Training vocabulary is A/B/Ω, but the held-out sequences are not present in
    # the training lexicon. Success therefore proves composition, not word lookup.
    for text in ("AB", "BA", "AΩ", "ΩB", "B A"):
        _approve_line(
            feedback,
            task=ContentModelTask.OCR,
            subtask="open_line_ocr",
            language="multi",
            source=train_source,
            text=text,
        )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="open_line_ocr",
        language="multi",
        source=validation_source,
        text="BΩA",
    )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="open_line_ocr",
        language="multi",
        source=test_source,
        text="ΩAB",
    )

    candidate = stage.train_candidate(
        task=ContentModelTask.OCR,
        subtask="open_line_ocr",
        languages=("multi",),
    )
    assert candidate["status"] == "candidate"
    assert candidate["metadata"]["open_vocabulary"] is True
    assert candidate["metadata"]["lexicon_required"] is False
    assert candidate["metadata"]["page_segmentation_supported"] is True
    assert candidate["backend_id"] == "vishnu-open-vocabulary-segmental-ocr-v1"
    assert candidate["metrics"]["cer"] <= 0.15

    recognizer = VishnuOpenVocabularyRecognizer(candidate["checkpoint_ref"])
    unseen = OpenVocabularyLineVectorizer(height=32).payload(_line_image("AΩB"))
    text, confidence = recognizer.predict_payload(unseen)
    assert text == "AΩB"
    assert confidence >= 0.0

    spaced = OpenVocabularyLineVectorizer(height=32).payload(_line_image("AB BA"))
    assert recognizer.predict_payload(spaced)[0] == "AB BA"

    with pytest.raises(ValueError, match="shadow qualification"):
        stage.approve(candidate["model_id"], owner_id="owner")
    evidence = stage.shadow_qualify(candidate["model_id"], baseline=BadLineBaseline())
    assert evidence["passed"] is True
    assert evidence["candidate_metrics"]["char_accuracy"] >= 0.85
    approved = stage.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    active = stage.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"


def test_open_vocabulary_handwriting_uses_separate_task_and_artifact(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    train_source = _source_for(models.datasets, "train", "hw-train")
    validation_source = _source_for(models.datasets, "validation", "hw-validation")
    test_source = _source_for(models.datasets, "test", "hw-test")
    for text in ("XY", "YX", "XΩ", "ΩY"):
        _approve_line(
            feedback,
            task=ContentModelTask.HANDWRITING,
            subtask="open_handwriting_line",
            language="multi",
            source=train_source,
            text=text,
        )
    _approve_line(
        feedback,
        task=ContentModelTask.HANDWRITING,
        subtask="open_handwriting_line",
        language="multi",
        source=validation_source,
        text="YΩX",
    )
    _approve_line(
        feedback,
        task=ContentModelTask.HANDWRITING,
        subtask="open_handwriting_line",
        language="multi",
        source=test_source,
        text="ΩXY",
    )
    candidate = stage.train_candidate(
        task=ContentModelTask.HANDWRITING,
        subtask="open_handwriting_line",
        languages=("multi",),
    )
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-open-vocabulary-segmental-handwriting-v1"
    assert candidate["metadata"]["open_vocabulary"] is True
    assert candidate["metrics"]["cer"] <= 0.25
    assert stage.shadow_qualify(candidate["model_id"], baseline=BadLineBaseline())["passed"] is True


def test_page_recognizer_segments_multiple_lines_with_exact_boxes(tmp_path):
    models, feedback, stage = _make_stage(tmp_path)
    train_source = _source_for(models.datasets, "train", "page-train")
    validation_source = _source_for(models.datasets, "validation", "page-validation")
    test_source = _source_for(models.datasets, "test", "page-test")
    for text in ("AB", "BA", "AA", "BB"):
        _approve_line(
            feedback,
            task=ContentModelTask.OCR,
            subtask="page_line_ocr",
            language="en",
            source=train_source,
            text=text,
        )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="page_line_ocr",
        language="en",
        source=validation_source,
        text="ABA",
    )
    _approve_line(
        feedback,
        task=ContentModelTask.OCR,
        subtask="page_line_ocr",
        language="en",
        source=test_source,
        text="BAB",
    )
    candidate = stage.train_candidate(task=ContentModelTask.OCR, subtask="page_line_ocr", languages=("en",))
    recognizer = VishnuOpenVocabularyRecognizer(candidate["checkpoint_ref"])
    page = Image.new("L", (160, 90), 255)
    for y, text in ((5, "AB"), (50, "BA")):
        with Image.open(io.BytesIO(_line_image(text))) as line:
            page.paste(line.convert("L"), (8, y))
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    result = VishnuPageSequenceRecognizer(recognizer).recognize(buffer.getvalue())
    assert result["text"] == "AB\nBA"
    assert result["line_count"] == 2
    assert all(len(line["bbox"]) == 4 for line in result["lines"])
    assert result["lines"][0]["bbox"][1] < result["lines"][1]["bbox"][1]
