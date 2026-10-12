from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from training.content_models import ContentDatasetBuilder, ContentModelCoordinator, ContentModelStatus
from training.ocr_family import (
    GovernedOCRSampleCollector,
    OCRModelMaturationCoordinator,
    OCRSamplePolicyError,
    OCRShadowBenchmark,
    TesseractGlyphBaseline,
    VishnuGlyphRecognizer,
)


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(10000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find {target} source")


def _glyph(label: str, thickness: int) -> bytes:
    image = Image.new("L", (32, 32), 255)
    draw = ImageDraw.Draw(image)
    if label == "I":
        x = 16
        draw.rectangle((x - thickness, 4, x + thickness, 27), fill=0)
    elif label == "-":
        y = 16
        draw.rectangle((4, y - thickness, 27, y + thickness), fill=0)
    else:
        raise ValueError(label)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _approved(image: bytes, label: str, source: str, *, sample_id: str) -> dict:
    return {
        "id": sample_id,
        "image_bytes": image,
        "label": label,
        "source_fingerprint": source,
        "consent_basis": "synthetic",
        "provenance": {
            "kind": "stage11_test_fixture",
            "approved_for_training": True,
            "license": "synthetic-test-fixture",
        },
    }


def _samples(builder: ContentDatasetBuilder) -> list[dict]:
    rows: list[dict] = []
    for split, thickness in (("train", 2), ("validation", 3), ("test", 4)):
        rows.append(
            _approved(
                _glyph("I", thickness),
                "I",
                _source_for(builder, split, f"{split}-vertical"),
                sample_id=f"{split}-I",
            )
        )
        rows.append(
            _approved(
                _glyph("-", thickness),
                "-",
                _source_for(builder, split, f"{split}-horizontal"),
                sample_id=f"{split}-dash",
            )
        )
    return rows


class _WeakBaseline:
    baseline_id = "stage11-weak-baseline"

    def predict(self, image_bytes: bytes) -> str:
        return "?"


def _runtime(tmp_path):
    content = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    return OCRModelMaturationCoordinator(
        content,
        shadow_store_path=tmp_path / "shadow.sqlite3",
    )


def test_governed_ocr_collection_requires_explicit_training_approval_and_license(tmp_path):
    collector = GovernedOCRSampleCollector()
    image = _glyph("I", 2)
    with pytest.raises(OCRSamplePolicyError, match="approved_for_training"):
        collector.collect(
            [
                {
                    "image_bytes": image,
                    "label": "I",
                    "source_fingerprint": "owner-source",
                    "consent_basis": "owner_provided",
                    "provenance": {"license": "owner-owned"},
                }
            ]
        )
    with pytest.raises(OCRSamplePolicyError, match="license"):
        collector.collect(
            [
                {
                    "image_bytes": image,
                    "label": "I",
                    "source_fingerprint": "owner-source",
                    "consent_basis": "owner_provided",
                    "provenance": {"approved_for_training": True},
                }
            ]
        )


def test_governed_ocr_collection_deduplicates_normalized_glyphs(tmp_path):
    builder = ContentDatasetBuilder(tmp_path / "helper")
    samples = _samples(builder)
    samples.append(dict(samples[0], id="duplicate-I"))
    governed = GovernedOCRSampleCollector().collect(samples)
    assert len(governed) == 6
    assert len({row["provenance"]["sample_sha256"] for row in governed}) == 6
    assert all(row["input"]["kind"] == "isolated_glyph_raster" for row in governed)


def test_stage11_trains_a_real_vishnu_owned_glyph_artifact(tmp_path):
    runtime = _runtime(tmp_path)
    helper = ContentDatasetBuilder(tmp_path / "helper")
    model = runtime.train_candidate(_samples(helper))

    assert model["status"] == ContentModelStatus.CANDIDATE.value
    assert model["backend_id"] == "vishnu-glyph-prototype-v1"
    assert model["metadata"]["trained_by_vishnu"] is True
    assert model["metadata"]["model_scope"] == "isolated_glyph_only"
    assert model["metadata"]["full_page_ocr"] is False
    assert model["metrics"]["cer"] <= 0.15
    assert model["metrics"]["word_accuracy"] >= 0.85

    recognizer = VishnuGlyphRecognizer(model["checkpoint_ref"])
    assert recognizer.model["trained_by_vishnu"] is True
    assert recognizer.model["model_scope"] == "isolated_glyph_only"
    assert set(recognizer.model["prototypes"]) == {"I", "-"}
    assert recognizer.predict_image(_glyph("I", 3))[0] == "I"
    assert recognizer.predict_image(_glyph("-", 3))[0] == "-"


def test_stage11_requires_successful_shadow_before_owner_promotion(tmp_path):
    runtime = _runtime(tmp_path)
    helper = ContentDatasetBuilder(tmp_path / "helper")
    model = runtime.train_candidate(_samples(helper))

    with pytest.raises(ValueError, match="shadow qualification"):
        runtime.approve(model["model_id"], owner_id="owner-test")

    evidence = runtime.shadow_qualify(model["model_id"], baseline=_WeakBaseline())
    assert evidence["passed"] is True
    assert evidence["candidate_metrics"]["word_accuracy"] >= 0.85
    assert evidence["candidate_metrics"]["cer"] <= 0.15
    assert evidence["candidate_metrics"]["word_accuracy"] > evidence["baseline_metrics"]["word_accuracy"]
    assert len(evidence["evidence_sha256"]) == 64

    approved = runtime.approve(model["model_id"], owner_id="owner-test")
    assert approved["status"] == ContentModelStatus.OWNER_APPROVED.value
    with pytest.raises(PermissionError):
        runtime.activate(model["model_id"], owner_authorized=False)
    active = runtime.activate(model["model_id"], owner_authorized=True)
    assert active["status"] == ContentModelStatus.ACTIVE.value
    assert active["owner_approved_by"] == "owner-test"


def test_stage11_shadow_fails_closed_when_candidate_does_not_beat_required_baseline(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.benchmark = OCRShadowBenchmark(min_accuracy_delta=0.10)
    helper = ContentDatasetBuilder(tmp_path / "helper")
    model = runtime.train_candidate(_samples(helper))

    class _PerfectBaseline:
        baseline_id = "perfect-baseline"

        def predict(self, image_bytes: bytes) -> str:
            image = Image.open(io.BytesIO(image_bytes)).convert("L")
            pixels = image.load()
            vertical = sum(255 - pixels[image.width // 2, y] for y in range(image.height))
            horizontal = sum(255 - pixels[x, image.height // 2] for x in range(image.width))
            return "I" if vertical >= horizontal else "-"

    evidence = runtime.shadow_qualify(model["model_id"], baseline=_PerfectBaseline())
    assert evidence["passed"] is False
    assert "candidate_accuracy_delta_below_requirement" in evidence["reasons"]
    with pytest.raises(ValueError, match="shadow qualification"):
        runtime.approve(model["model_id"], owner_id="owner-test")


def test_tesseract_remains_explicit_baseline_not_vishnu_trained():
    baseline = TesseractGlyphBaseline()
    assert baseline.baseline_id == "tesseract-local-glyph"
    assert baseline.provider.name.startswith("tesseract-local/")
    assert baseline.provider.external is False
