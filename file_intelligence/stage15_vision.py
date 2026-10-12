from __future__ import annotations

import io
from typing import Any

from PIL import Image

from .ocr import OcrUnavailable


class Stage15DocumentVisionOcrProvider:
    """Local Stage 15 provider compatible with Vishnu's existing OCR contract.

    It loads only owner/release-controller activated registry artifacts, performs
    no network calls, and never relabels Tesseract as Vishnu-trained.
    """

    name = "vishnu-stage15-neural-document-vision-v1"
    external = False
    version = "vishnu-document-vision/15.1"

    def __init__(self, runtime: Any, *, table_model: Any | None = None):
        self.runtime = runtime
        self.table_model = table_model

    @classmethod
    def from_active_registry(cls, registry: Any) -> "Stage15DocumentVisionOcrProvider":
        from training.content_models import ContentModelTask
        from training.document_vision import (
            Stage15DocumentVisionRuntime,
            VishnuNeuralLayoutRecognizer,
        )
        from training.neural_ocr import VishnuNeuralOpenVocabularyRecognizer
        from training.table_vision import VishnuNeuralTableCellRecognizer

        layout = registry.active(ContentModelTask.LAYOUT)
        ocr = registry.active(ContentModelTask.OCR)
        handwriting = registry.active(ContentModelTask.HANDWRITING)
        table = registry.active(ContentModelTask.TABLE)
        if not layout:
            raise OcrUnavailable("Stage 15 requires an owner-activated Vishnu layout model")
        if int(dict(layout.get("metadata") or {}).get("stage") or 0) < 15:
            raise OcrUnavailable("Active layout model is not Stage 15 qualified")
        if not ocr:
            raise OcrUnavailable("Stage 15 requires an owner-activated Vishnu OCR model")
        if int(dict(ocr.get("metadata") or {}).get("stage") or 0) < 14:
            raise OcrUnavailable("Active OCR model is not Stage 14 sequence-native")
        layout_model = VishnuNeuralLayoutRecognizer(layout["checkpoint_ref"])
        ocr_model = VishnuNeuralOpenVocabularyRecognizer(ocr["checkpoint_ref"])
        handwriting_model = (
            VishnuNeuralOpenVocabularyRecognizer(handwriting["checkpoint_ref"])
            if handwriting and int(dict(handwriting.get("metadata") or {}).get("stage") or 0) >= 14
            else None
        )
        table_model = (
            VishnuNeuralTableCellRecognizer(table["checkpoint_ref"])
            if table and int(dict(table.get("metadata") or {}).get("stage") or 0) >= 15
            else None
        )
        return cls(
            Stage15DocumentVisionRuntime(
                layout_model,
                ocr_model=ocr_model,
                handwriting_model=handwriting_model,
            ),
            table_model=table_model,
        )

    @staticmethod
    def _png(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("L").save(buffer, format="PNG")
        return buffer.getvalue()

    def _enrich_table_cells(
        self,
        *,
        page: Image.Image,
        region: dict[str, Any],
    ) -> dict[str, Any]:
        structure = dict(region.get("structure") or {})
        if self.table_model is None or structure.get("kind") != "table":
            return structure
        from training.document_vision import Stage15LayoutVectorizer

        bbox = [int(value) for value in region.get("bbox") or []]
        if len(bbox) != 4:
            return structure
        left, top, right, bottom = bbox
        crop = page.crop((left, top, right, bottom))
        horizontal = sorted(
            {
                0,
                max(1, crop.height),
                *[
                    max(0, min(crop.height, int(value)))
                    for value in structure.get("horizontal_rule_positions") or []
                ],
            }
        )
        vertical = sorted(
            {
                0,
                max(1, crop.width),
                *[
                    max(0, min(crop.width, int(value)))
                    for value in structure.get("vertical_rule_positions") or []
                ],
            }
        )
        if len(horizontal) < 2 or len(vertical) < 2:
            return structure
        cells: list[dict[str, Any]] = []
        for row_index, (y1, y2) in enumerate(zip(horizontal, horizontal[1:])):
            if y2 - y1 < 2:
                continue
            for column_index, (x1, x2) in enumerate(zip(vertical, vertical[1:])):
                if x2 - x1 < 2:
                    continue
                cell = crop.crop((x1, y1, x2, y2))
                payload = Stage15LayoutVectorizer.payload(
                    self._png(cell),
                    bbox=(left + x1, top + y1, left + x2, top + y2),
                    page_width=page.width,
                    page_height=page.height,
                )
                prediction = self.table_model.predict_payload(payload)
                cells.append(
                    {
                        "row": row_index,
                        "column": column_index,
                        "bbox": [left + x1, top + y1, left + x2, top + y2],
                        "cell_type": prediction["label"],
                        "confidence": prediction["confidence"],
                        "accepted": prediction["accepted"],
                    }
                )
        return {**structure, "cells": cells, "neural_cell_model": True}

    def analyze(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.png",
        access_class: str = "owner",
    ) -> dict[str, Any]:
        if access_class not in {"owner", "trusted-devices", "private"}:
            raise OcrUnavailable("Stage 15 document vision received an unsupported access class")
        result = self.runtime.analyze(image_bytes)
        if self.table_model is not None and result.get("tables"):
            try:
                with Image.open(io.BytesIO(image_bytes)) as source:
                    source.load()
                    page = source.convert("L").copy()
            except Exception as exc:
                raise OcrUnavailable("Stage 15 table structure image is unreadable") from exc
            for region in result["regions"]:
                if region.get("label") == "table":
                    region["structure"] = self._enrich_table_cells(page=page, region=region)
            result["tables"] = [
                region for region in result["regions"] if region.get("label") == "table"
            ]
        result["provider"] = self.name
        result["filename"] = str(filename)
        result["network_used"] = False
        return result

    def extract(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.png",
        access_class: str = "owner",
    ) -> list[dict]:
        result = self.analyze(
            image_bytes,
            filename=filename,
            access_class=access_class,
        )
        output: list[dict[str, Any]] = []
        for region in result.get("regions") or []:
            if region.get("accepted") is not True:
                continue
            text = str(region.get("text") or "").strip()
            if not text:
                continue
            layout_confidence = max(0.0, min(1.0, float(region.get("confidence") or 0.0)))
            text_confidence = max(
                0.0, min(1.0, float(region.get("text_confidence") or layout_confidence))
            )
            output.append(
                {
                    "text": text,
                    "confidence": min(layout_confidence, text_confidence),
                    "bbox": list(region.get("bbox") or []),
                    "metadata": {
                        "provider": self.name,
                        "layout_role": region.get("label"),
                        "reading_order": region.get("reading_order"),
                        "normalized_bbox": region.get("normalized_bbox"),
                        "structure": region.get("structure") or {},
                        "stage15_document_vision": True,
                        "stage14_ctc_text_backend": True,
                        "network_used": False,
                    },
                }
            )
        return output
