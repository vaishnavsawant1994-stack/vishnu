from __future__ import annotations

import io

from PIL import Image, ImageDraw

from file_intelligence import AdaptiveOcrProvider, FileIntelligenceEngine
from file_intelligence.models import ExtractionMethod, SourceReference, VishnuBlock
from file_intelligence.ocr import TesseractOcrProvider
from file_intelligence.visual import build_preprocess_variants, infer_spatial_layout, inspect_image_quality


def _image_bytes() -> bytes:
    image = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 420, 180), outline="black", width=4)
    draw.line((40, 230, 850, 230), fill="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_preprocessing_and_quality_are_local_and_bounded():
    payload = _image_bytes()
    quality = inspect_image_quality(payload)
    assert quality.width == 900
    assert quality.height == 600
    assert quality.likely_surface in {
        "low_contrast_document",
        "screenshot_or_diagram",
        "document_or_form",
        "photo_or_scan",
    }
    variants = build_preprocess_variants(payload)
    assert variants
    assert variants[0][0] == "original"
    assert 2 <= len(variants) <= 4
    for _, candidate in variants:
        with Image.open(io.BytesIO(candidate)) as image:
            assert image.width > 0 and image.height > 0


def test_tesseract_data_is_reconstructed_into_lines_with_bbox_and_confidence():
    data = {
        "text": ["Invoice", "No:", "1234", "Total", "42"],
        "conf": ["95", "90", "99", "88", "92"],
        "left": [10, 100, 150, 510, 590],
        "top": [20, 20, 20, 20, 20],
        "width": [80, 40, 60, 70, 30],
        "height": [20, 20, 20, 20, 20],
        "block_num": [1, 1, 1, 2, 2],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1],
        "word_num": [1, 2, 3, 1, 2],
    }
    lines = TesseractOcrProvider._lines_from_data(
        data,
        orientation_degrees=90,
        language="eng+deu",
        profile="autocontrast_sharpen",
    )
    assert [line["text"] for line in lines] == ["Invoice No: 1234", "Total 42"]
    assert lines[0]["bbox"] == [10.0, 20.0, 210.0, 40.0]
    assert lines[0]["confidence"] > 0.9
    assert lines[0]["metadata"]["orientation_degrees"] == 90
    assert lines[0]["metadata"]["language"] == "eng+deu"


def test_spatial_layout_assigns_columns_reading_order_and_visual_roles():
    blocks = [
        VishnuBlock("text", "Invoice No: 1234", SourceReference(image="scan.png", bbox=[10, 10, 210, 40]), ExtractionMethod.OCR, 0.95),
        VishnuBlock("text", "Amount = 42", SourceReference(image="scan.png", bbox=[10, 70, 210, 100]), ExtractionMethod.OCR, 0.93),
        VishnuBlock("text", "Notes", SourceReference(image="scan.png", bbox=[610, 15, 800, 45]), ExtractionMethod.OCR, 0.91),
        VishnuBlock("text", "Approved", SourceReference(image="scan.png", bbox=[610, 75, 800, 105]), ExtractionMethod.OCR, 0.90),
    ]
    result = infer_spatial_layout(blocks)
    assert [block.metadata["column"] for block in result] == [1, 1, 2, 2]
    assert sorted(block.metadata["reading_order"] for block in result) == [1, 2, 3, 4]
    assert result[0].metadata["visual_role"] == "form_or_key_value"
    assert result[1].metadata["visual_role"] == "equation_candidate"


class _LowThenHighLocalProvider:
    name = "fake-local"
    external = False

    def __init__(self):
        self.calls = 0

    def extract(self, image_bytes, *, filename="image.png", access_class="owner"):
        self.calls += 1
        confidence = 0.25 if self.calls == 1 else 0.96
        return [{"text": "Readable content", "confidence": confidence, "bbox": [10, 10, 250, 40]}]


def test_adaptive_provider_retries_low_confidence_and_selects_better_local_result():
    base = _LowThenHighLocalProvider()
    provider = AdaptiveOcrProvider(base, max_variants=4, min_confidence=0.8)
    result = provider.extract(_image_bytes())
    assert base.calls >= 2
    assert result[0]["confidence"] == 0.96
    assert result[0]["metadata"]["adaptive_profile"] != "original"
    assert provider.external is False


def test_engine_keeps_exact_image_bbox_and_stage6_spatial_layout():
    class Provider:
        name = "fixture-local"
        external = False

        def extract(self, image_bytes, *, filename="image.png", access_class="owner"):
            return [
                {"text": "Invoice No: 1234", "confidence": 0.98, "bbox": [10, 10, 240, 40]},
                {"text": "Second column", "confidence": 0.94, "bbox": [600, 10, 850, 40]},
            ]

    document = FileIntelligenceEngine(ocr_provider=Provider()).extract(
        filename="invoice.png",
        data=_image_bytes(),
        declared_mime="image/png",
    )
    originals = [block for block in document.blocks if block.extraction_method == ExtractionMethod.OCR]
    assert originals
    assert originals[0].source.bbox == [10, 10, 240, 40]
    assert originals[0].metadata["column"] == 1
    assert originals[1].metadata["column"] == 2
    assert any(block.kind == "key_value" and block.data["key"] == "Invoice No" for block in document.blocks)
    assert document.schema_version == "1.2"
    assert document.layout_version == "vishnu-layout/3"
