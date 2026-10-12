from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np
from PIL import Image, ImageOps

from training.content_models import ContentDatasetSnapshot, ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import (
    GovernedContentFeedbackStore,
    ModelCycleEvidence,
    ModelCycleEvidenceStore,
    _canonical,
    _now,
    _read_jsonl,
)
from training.neural_ocr import VishnuNeuralOpenVocabularyRecognizer


class Stage15PolicyError(ValueError):
    pass


STAGE15_LAYOUT_LABELS = (
    "caption",
    "checkbox",
    "equation",
    "figure",
    "footer",
    "form_field",
    "handwriting",
    "header",
    "heading",
    "key_value",
    "list",
    "page_number",
    "paragraph",
    "signature",
    "stamp",
    "table",
    "title",
    "footnote",
)

REAL_WORLD_CAPTURE_KINDS = ("scan", "photo", "screenshot", "handwriting")
TEXT_REGION_LABELS = {
    "caption",
    "footer",
    "form_field",
    "header",
    "heading",
    "key_value",
    "list",
    "page_number",
    "paragraph",
    "title",
    "footnote",
}
HANDWRITING_REGION_LABELS = {"handwriting", "signature"}


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.maximum(np.sum(exp, axis=1, keepdims=True), 1e-12)


def _macro_f1(expected: list[str], predicted: list[str]) -> float:
    labels = sorted(set(expected) | set(predicted))
    if not labels:
        return 0.0
    values: list[float] = []
    for label in labels:
        tp = sum(1 for truth, guess in zip(expected, predicted) if truth == label and guess == label)
        fp = sum(1 for truth, guess in zip(expected, predicted) if truth != label and guess == label)
        fn = sum(1 for truth, guess in zip(expected, predicted) if truth == label and guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        values.append(2.0 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return float(sum(values) / len(values))


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, lch in enumerate(left, start=1):
        current = [i]
        for j, rch in enumerate(right, start=1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + int(lch != rch))
            )
        previous = current
    return previous[-1]


def _token_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, ltok in enumerate(left, start=1):
        current = [i]
        for j, rtok in enumerate(right, start=1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + int(ltok != rtok))
            )
        previous = current
    return previous[-1]


def _recognition_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    if not records:
        return {
            "cer": 1.0,
            "wer": 1.0,
            "word_accuracy": 0.0,
            "char_accuracy": 0.0,
            "records": 0.0,
            "avg_latency_ms": 0.0,
            "rejection_accuracy": 0.0,
            "calibration_error": 1.0,
        }
    char_edits = char_total = word_edits = word_total = exact = 0
    latency = 0.0
    rejection_correct = 0
    bins: dict[int, list[tuple[float, float]]] = {}
    for row in records:
        truth = str(row.get("truth") or "")
        prediction = str(row.get("prediction") or "")
        char_edits += _levenshtein(truth, prediction)
        char_total += max(1, len(truth))
        truth_words = truth.split()
        prediction_words = prediction.split()
        word_edits += _token_distance(truth_words, prediction_words)
        word_total += max(1, len(truth_words))
        is_correct = truth == prediction
        exact += int(is_correct)
        latency += max(0.0, float(row.get("latency_ms") or 0.0))
        accepted = bool(row.get("accepted", bool(prediction)))
        should_accept = bool(row.get("should_accept", True))
        rejection_correct += int(accepted == should_accept)
        confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
        bucket = min(9, int(confidence * 10.0))
        bins.setdefault(bucket, []).append((confidence, 1.0 if is_correct else 0.0))
    calibration_error = 0.0
    for values in bins.values():
        weight = len(values) / len(records)
        mean_conf = sum(item[0] for item in values) / len(values)
        mean_acc = sum(item[1] for item in values) / len(values)
        calibration_error += weight * abs(mean_conf - mean_acc)
    cer = min(1.0, char_edits / max(1, char_total))
    wer = min(1.0, word_edits / max(1, word_total))
    return {
        "cer": float(cer),
        "wer": float(wer),
        "word_accuracy": exact / len(records),
        "char_accuracy": max(0.0, 1.0 - cer),
        "records": float(len(records)),
        "avg_latency_ms": latency / len(records),
        "rejection_accuracy": rejection_correct / len(records),
        "calibration_error": float(calibration_error),
    }


@dataclass(frozen=True)
class RealWorldQualificationReport:
    qualified: bool
    records: int
    source_groups: int
    capture_counts: dict[str, int]
    ocr_metrics: dict[str, float]
    handwriting_metrics: dict[str, float]
    reasons: tuple[str, ...]
    evidence_sha256: str
    created_at: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        value["real_world_corpus_qualified"] = self.qualified
        value["synthetic_evidence_can_qualify"] = False
        return value


class RealWorldCorpusQualifier:
    """Fail-closed Stage 15 qualification for genuine captured document evidence.

    Synthetic/simulated rows are forbidden here. They remain useful robustness
    tests but can never satisfy Vishnu's real-world corpus claim.
    """

    def __init__(
        self,
        *,
        required_capture_kinds: Iterable[str] = REAL_WORLD_CAPTURE_KINDS,
        min_source_groups: int = 4,
        max_calibration_error: float = 0.20,
        min_rejection_accuracy: float = 0.80,
    ):
        self.required_capture_kinds = tuple(sorted({str(value) for value in required_capture_kinds}))
        self.min_source_groups = max(3, int(min_source_groups))
        self.max_calibration_error = max(0.0, min(1.0, float(max_calibration_error)))
        self.min_rejection_accuracy = max(0.0, min(1.0, float(min_rejection_accuracy)))

    def qualify(self, records: Iterable[dict[str, Any]]) -> RealWorldQualificationReport:
        rows = [dict(row) for row in records]
        reasons: list[str] = []
        captures = {name: 0 for name in self.required_capture_kinds}
        split_sources: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}
        valid_rows: list[dict[str, Any]] = []

        for index, row in enumerate(rows):
            provenance = dict(row.get("provenance") or {})
            source = str(row.get("source_fingerprint") or "").strip()
            consent = str(row.get("consent_basis") or "").strip()
            license_basis = str(
                provenance.get("license") or provenance.get("ownership_basis") or ""
            ).strip()
            capture = str(provenance.get("capture_kind") or row.get("capture_kind") or "").strip()
            split = str(row.get("split") or "test").strip().lower()
            if provenance.get("real_world") is not True:
                reasons.append(f"record_{index}:real_world_provenance_required")
                continue
            if provenance.get("synthetic") is True or provenance.get("simulated") is True:
                reasons.append(f"record_{index}:synthetic_or_simulated_evidence_forbidden")
                continue
            if capture not in self.required_capture_kinds:
                reasons.append(f"record_{index}:unsupported_capture_kind")
                continue
            if not source:
                reasons.append(f"record_{index}:source_fingerprint_required")
                continue
            if consent not in {"owner_provided", "licensed", "public_domain"}:
                reasons.append(f"record_{index}:real_world_consent_required")
                continue
            if not license_basis:
                reasons.append(f"record_{index}:license_or_ownership_basis_required")
                continue
            if split not in split_sources:
                reasons.append(f"record_{index}:invalid_split")
                continue
            captures[capture] += 1
            split_sources[split].add(source)
            valid_rows.append(row)

        for capture, count in captures.items():
            if count <= 0:
                reasons.append(f"missing_capture_kind:{capture}")
        sources = set().union(*split_sources.values())
        if len(sources) < self.min_source_groups:
            reasons.append(f"source_groups_below_{self.min_source_groups}")
        split_names = ("train", "validation", "test")
        for index, left in enumerate(split_names):
            for right in split_names[index + 1 :]:
                if split_sources[left] & split_sources[right]:
                    reasons.append(f"source_group_leakage:{left}:{right}")

        ocr_rows = [row for row in valid_rows if str(row.get("task") or "ocr") == "ocr"]
        handwriting_rows = [
            row for row in valid_rows if str(row.get("task") or "") == "handwriting"
        ]
        if not ocr_rows:
            reasons.append("missing_real_world_ocr_records")
        if not handwriting_rows:
            reasons.append("missing_real_world_handwriting_records")
        ocr_metrics = _recognition_metrics(ocr_rows)
        handwriting_metrics = _recognition_metrics(handwriting_rows)

        if ocr_rows:
            if ocr_metrics["cer"] > 0.15:
                reasons.append("ocr_cer_above_0.15")
            if ocr_metrics["word_accuracy"] < 0.85:
                reasons.append("ocr_word_accuracy_below_0.85")
        if handwriting_rows:
            if handwriting_metrics["cer"] > 0.25:
                reasons.append("handwriting_cer_above_0.25")
            if handwriting_metrics["word_accuracy"] < 0.70:
                reasons.append("handwriting_word_accuracy_below_0.70")
        for name, metrics in (("ocr", ocr_metrics), ("handwriting", handwriting_metrics)):
            if metrics["records"]:
                if metrics["calibration_error"] > self.max_calibration_error:
                    reasons.append(f"{name}_calibration_error_above_{self.max_calibration_error}")
                if metrics["rejection_accuracy"] < self.min_rejection_accuracy:
                    reasons.append(f"{name}_rejection_accuracy_below_{self.min_rejection_accuracy}")

        created_at = _now()
        payload = {
            "records": len(valid_rows),
            "source_groups": len(sources),
            "capture_counts": captures,
            "ocr_metrics": ocr_metrics,
            "handwriting_metrics": handwriting_metrics,
            "reasons": sorted(set(reasons)),
            "created_at": created_at,
            "synthetic_evidence_can_qualify": False,
        }
        return RealWorldQualificationReport(
            qualified=not reasons,
            records=len(valid_rows),
            source_groups=len(sources),
            capture_counts=captures,
            ocr_metrics=ocr_metrics,
            handwriting_metrics=handwriting_metrics,
            reasons=tuple(sorted(set(reasons))),
            evidence_sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )


class Stage15LayoutVectorizer:
    """Convert a page-region crop plus geometry into a fixed visual/spatial vector."""

    FEATURE_NAMES = (
        "ink_density",
        "top_ink",
        "middle_ink",
        "bottom_ink",
        "left_ink",
        "center_ink",
        "right_ink",
        "horizontal_variance",
        "vertical_variance",
        "aspect_ratio",
        "relative_width",
        "relative_height",
        "relative_x",
        "relative_y",
        "edge_ink",
        "interior_ink",
        "horizontal_rule_score",
        "vertical_rule_score",
        "component_density",
        "blank_run_score",
    )

    @staticmethod
    def _decode(payload: dict[str, Any]) -> Image.Image:
        encoded = str(payload.get("image_png_b64") or "")
        if not encoded:
            raise Stage15PolicyError("Stage 15 layout sample requires image_png_b64")
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                return ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise Stage15PolicyError("Stage 15 layout sample image is unreadable") from exc

    @classmethod
    def features(cls, payload: dict[str, Any]) -> np.ndarray:
        image = cls._decode(payload)
        array = 1.0 - np.asarray(
            image.resize((64, 64), Image.Resampling.BILINEAR), dtype=np.float64
        ) / 255.0
        ink = array > 0.08
        row = np.mean(array, axis=1)
        col = np.mean(array, axis=0)
        page_width = max(1.0, float(payload.get("page_width") or image.width))
        page_height = max(1.0, float(payload.get("page_height") or image.height))
        bbox = payload.get("bbox") or [0, 0, image.width, image.height]
        if len(bbox) != 4:
            raise Stage15PolicyError("Stage 15 layout bbox requires four coordinates")
        left, top, right, bottom = [float(value) for value in bbox]
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)
        horizontal_transitions = np.mean(np.abs(np.diff(ink.astype(np.float64), axis=1)))
        vertical_transitions = np.mean(np.abs(np.diff(ink.astype(np.float64), axis=0)))
        blank_columns = np.mean(col < 0.015)
        values = np.asarray(
            [
                np.mean(array),
                np.mean(array[:21]),
                np.mean(array[21:43]),
                np.mean(array[43:]),
                np.mean(array[:, :21]),
                np.mean(array[:, 21:43]),
                np.mean(array[:, 43:]),
                np.var(row),
                np.var(col),
                min(8.0, width / height) / 8.0,
                min(1.0, width / page_width),
                min(1.0, height / page_height),
                min(1.0, max(0.0, left / page_width)),
                min(1.0, max(0.0, top / page_height)),
                float(np.mean(np.concatenate((array[0], array[-1], array[:, 0], array[:, -1])))),
                float(np.mean(array[8:-8, 8:-8])),
                float(np.mean(row > max(0.12, np.mean(row) * 1.8))),
                float(np.mean(col > max(0.12, np.mean(col) * 1.8))),
                float((horizontal_transitions + vertical_transitions) / 2.0),
                float(blank_columns),
            ],
            dtype=np.float64,
        )
        return values

    @staticmethod
    def payload(
        image_bytes: bytes,
        *,
        bbox: tuple[int, int, int, int] | list[int],
        page_width: int,
        page_height: int,
    ) -> dict[str, Any]:
        return {
            "kind": "stage15_document_region",
            "image_png_b64": base64.b64encode(bytes(image_bytes)).decode("ascii"),
            "bbox": [int(value) for value in bbox],
            "page_width": int(page_width),
            "page_height": int(page_height),
        }


class VishnuNeuralLayoutTrainer:
    task = ContentModelTask.LAYOUT
    backend_id = "vishnu-stage15-neural-layout-mlp-v1"

    def __init__(
        self,
        *,
        hidden_size: int = 48,
        epochs: int = 240,
        learning_rate: float = 0.06,
        reject_threshold: float = 0.45,
    ):
        self.hidden_size = max(16, min(128, int(hidden_size)))
        self.epochs = max(60, min(800, int(epochs)))
        self.learning_rate = max(0.005, min(0.2, float(learning_rate)))
        self.reject_threshold = max(0.0, min(0.95, float(reject_threshold)))

    @staticmethod
    def _predict_arrays(
        features: np.ndarray,
        w1: np.ndarray,
        b1: np.ndarray,
        w2: np.ndarray,
        b2: np.ndarray,
    ) -> np.ndarray:
        hidden = np.tanh(features @ w1 + b1)
        return _softmax(hidden @ w2 + b2)

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not ContentModelTask.LAYOUT:
            raise ValueError("Stage 15 neural layout trainer requires layout task")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("Stage 15 layout train split is empty")
        labels = sorted({str(row.get("label") or "") for row in rows})
        if len(labels) < 2:
            raise ValueError("Stage 15 neural layout model requires at least two labels")
        unsupported = [label for label in labels if label not in STAGE15_LAYOUT_LABELS]
        if unsupported:
            raise Stage15PolicyError(f"unsupported Stage 15 layout labels: {unsupported}")
        label_index = {label: index for index, label in enumerate(labels)}
        x = np.stack(
            [Stage15LayoutVectorizer.features(dict(row.get("input") or {})) for row in rows]
        )
        y = np.asarray([label_index[str(row["label"])] for row in rows], dtype=np.int64)
        seed = int(snapshot.sha256[:16], 16) % (2**32)
        rng = np.random.default_rng(seed)
        w1 = rng.normal(0.0, 0.18, size=(x.shape[1], self.hidden_size))
        b1 = np.zeros((1, self.hidden_size), dtype=np.float64)
        w2 = rng.normal(0.0, 0.18, size=(self.hidden_size, len(labels)))
        b2 = np.zeros((1, len(labels)), dtype=np.float64)

        for epoch in range(self.epochs):
            hidden = np.tanh(x @ w1 + b1)
            probabilities = _softmax(hidden @ w2 + b2)
            target = np.zeros_like(probabilities)
            target[np.arange(len(y)), y] = 1.0
            dlogits = (probabilities - target) / max(1, len(y))
            dw2 = hidden.T @ dlogits
            db2 = np.sum(dlogits, axis=0, keepdims=True)
            dhidden = (dlogits @ w2.T) * (1.0 - hidden * hidden)
            dw1 = x.T @ dhidden
            db1 = np.sum(dhidden, axis=0, keepdims=True)
            scale = max(
                1.0,
                float(
                    max(
                        np.linalg.norm(dw1),
                        np.linalg.norm(db1),
                        np.linalg.norm(dw2),
                        np.linalg.norm(db2),
                    )
                )
                / 5.0,
            )
            rate = self.learning_rate / math.sqrt(1.0 + epoch / 100.0)
            w1 -= rate * dw1 / scale
            b1 -= rate * db1 / scale
            w2 -= rate * dw2 / scale
            b2 -= rate * db2 / scale

        model = {
            "schema_version": 1,
            "model_type": "vishnu-stage15-neural-document-layout",
            "task": ContentModelTask.LAYOUT.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "labels": labels,
            "feature_names": list(Stage15LayoutVectorizer.FEATURE_NAMES),
            "architecture": {
                "family": "visual_spatial_mlp",
                "input_features": int(x.shape[1]),
                "hidden_size": self.hidden_size,
                "activation": "tanh",
                "region_proposals": "deterministic_whitespace_ink_regions",
                "reading_order": "geometry_column_aware",
                "stage14_ctc_text_backend": True,
            },
            "weights": {
                "w1": w1.round(9).tolist(),
                "b1": b1.round(9).tolist(),
                "w2": w2.round(9).tolist(),
                "b2": b2.round(9).tolist(),
            },
            "confidence": {
                "reject_threshold": self.reject_threshold,
                "rejection_label": "unknown",
            },
            "trained_by_vishnu": True,
            "neural_layout_classifier": True,
            "foundation_model": False,
            "real_world_corpus_qualified": False,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(
            json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        evaluation_rows = (
            _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        )
        recognizer = VishnuNeuralLayoutRecognizer.from_model(model)
        truth = [str(row.get("label") or "") for row in evaluation_rows]
        predictions = [
            str(
                recognizer.predict_payload(
                    dict(row.get("input") or {}), reject_below=0.0
                )["label"]
            )
            for row in evaluation_rows
        ]
        return output_dir, {
            "f1": _macro_f1(truth, predictions),
            "accuracy": sum(int(a == b) for a, b in zip(truth, predictions)) / max(1, len(truth)),
            "evaluation_records": float(len(truth)),
            "neural_layout_classifier": 1.0,
        }


class VishnuNeuralLayoutRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        self._load(json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8")))

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "VishnuNeuralLayoutRecognizer":
        value = cls.__new__(cls)
        value._load(model)
        return value

    def _load(self, model: dict[str, Any]) -> None:
        if model.get("model_type") != "vishnu-stage15-neural-document-layout":
            raise ValueError("unsupported Stage 15 Vishnu neural layout artifact")
        self.model = model
        self.labels = [str(value) for value in model["labels"]]
        weights = dict(model["weights"])
        self.w1 = np.asarray(weights["w1"], dtype=np.float64)
        self.b1 = np.asarray(weights["b1"], dtype=np.float64)
        self.w2 = np.asarray(weights["w2"], dtype=np.float64)
        self.b2 = np.asarray(weights["b2"], dtype=np.float64)
        confidence = dict(model.get("confidence") or {})
        self.reject_threshold = max(
            0.0, min(1.0, float(confidence.get("reject_threshold") or 0.0))
        )

    def predict_payload(
        self, payload: dict[str, Any], *, reject_below: float | None = None
    ) -> dict[str, Any]:
        vector = Stage15LayoutVectorizer.features(payload).reshape(1, -1)
        probabilities = VishnuNeuralLayoutTrainer._predict_arrays(
            vector, self.w1, self.b1, self.w2, self.b2
        )[0]
        index = int(np.argmax(probabilities))
        raw_label = self.labels[index]
        confidence = float(probabilities[index])
        threshold = (
            self.reject_threshold
            if reject_below is None
            else max(0.0, min(1.0, float(reject_below)))
        )
        accepted = confidence >= threshold
        alternatives = sorted(
            (
                {"label": label, "confidence": float(probabilities[position])}
                for position, label in enumerate(self.labels)
            ),
            key=lambda item: (-item["confidence"], item["label"]),
        )[:3]
        return {
            "label": raw_label if accepted else "unknown",
            "raw_label": raw_label,
            "confidence": confidence,
            "accepted": accepted,
            "rejection_reason": None if accepted else "low_confidence",
            "alternatives": alternatives,
        }


@dataclass(frozen=True)
class Stage15Region:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    reading_order: int
    text: str = ""
    text_confidence: float = 0.0
    accepted: bool = True
    rejection_reason: str | None = None
    structure: dict[str, Any] | None = None

    def public(self, *, page_width: int, page_height: int) -> dict[str, Any]:
        left, top, right, bottom = self.bbox
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bbox": list(self.bbox),
            "normalized_bbox": [
                left / max(1, page_width),
                top / max(1, page_height),
                right / max(1, page_width),
                bottom / max(1, page_height),
            ],
            "reading_order": self.reading_order,
            "text": self.text,
            "text_confidence": self.text_confidence,
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason,
            "structure": self.structure or {},
        }


class Stage15DocumentVisionRuntime:
    """Page proposals + neural layout + governed Stage 14 OCR/HTR routing."""

    def __init__(
        self,
        layout_model: VishnuNeuralLayoutRecognizer,
        *,
        ocr_model: VishnuNeuralOpenVocabularyRecognizer | None = None,
        handwriting_model: VishnuNeuralOpenVocabularyRecognizer | None = None,
    ):
        self.layout_model = layout_model
        self.ocr_model = ocr_model
        self.handwriting_model = handwriting_model

    @staticmethod
    def _open(image_bytes: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.load()
                return ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise Stage15PolicyError("Stage 15 page image is unreadable") from exc

    @staticmethod
    def _runs(mask: np.ndarray, *, minimum: int = 1) -> list[tuple[int, int]]:
        output: list[tuple[int, int]] = []
        start: int | None = None
        for index, active in enumerate(mask.tolist()):
            if active and start is None:
                start = index
            elif not active and start is not None:
                if index - start >= minimum:
                    output.append((start, index))
                start = None
        if start is not None and len(mask) - start >= minimum:
            output.append((start, len(mask)))
        return output

    @classmethod
    def propose_regions(cls, page: Image.Image) -> list[tuple[int, int, int, int]]:
        gray = ImageOps.autocontrast(page.convert("L"))
        ink = 1.0 - np.asarray(gray, dtype=np.float64) / 255.0
        active_rows = np.mean(ink, axis=1) > 0.008
        row_runs = cls._runs(active_rows, minimum=2)
        boxes: list[tuple[int, int, int, int]] = []
        for top, bottom in row_runs:
            band = ink[top:bottom]
            active_cols = np.mean(band, axis=0) > 0.006
            col_runs = cls._runs(active_cols, minimum=2)
            if len(col_runs) > 5:
                col_runs = [(col_runs[0][0], col_runs[-1][1])]
            merged: list[tuple[int, int]] = []
            for left, right in col_runs:
                if merged and left - merged[-1][1] < max(8, page.width // 80):
                    merged[-1] = (merged[-1][0], right)
                else:
                    merged.append((left, right))
            for left, right in merged:
                if (right - left) * (bottom - top) >= 12:
                    boxes.append(
                        (
                            max(0, left - 2),
                            max(0, top - 1),
                            min(page.width, right + 2),
                            min(page.height, bottom + 1),
                        )
                    )
        if not boxes:
            bbox = ImageOps.invert(gray).getbbox()
            if bbox:
                boxes.append(tuple(int(value) for value in bbox))
        return boxes

    @staticmethod
    def _reading_order(
        boxes: list[tuple[int, int, int, int]], page_width: int
    ) -> list[tuple[int, int, int, int]]:
        if not boxes:
            return []
        centers = [
            ((left + right) / 2.0, (top + bottom) / 2.0, box)
            for box in boxes
            for left, top, right, bottom in [box]
        ]
        left_items = [item for item in centers if item[0] < page_width * 0.48]
        right_items = [item for item in centers if item[0] > page_width * 0.52]
        spans = [item for item in centers if page_width * 0.48 <= item[0] <= page_width * 0.52]
        if left_items and right_items and not spans:
            return [
                item[2]
                for item in sorted(left_items, key=lambda item: (item[1], item[0]))
                + sorted(right_items, key=lambda item: (item[1], item[0]))
            ]
        return [item[2] for item in sorted(centers, key=lambda item: (item[1], item[0]))]

    @staticmethod
    def _png(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("L").save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _table_structure(crop: Image.Image, box: tuple[int, int, int, int]) -> dict[str, Any]:
        ink = 1.0 - np.asarray(crop.convert("L"), dtype=np.float64) / 255.0
        row_score = np.mean(ink, axis=1)
        col_score = np.mean(ink, axis=0)
        row_lines = np.where(row_score > max(0.35, float(np.mean(row_score) * 2.4)))[0].tolist()
        col_lines = np.where(col_score > max(0.35, float(np.mean(col_score) * 2.4)))[0].tolist()
        return {
            "kind": "table",
            "horizontal_rule_positions": row_lines[:64],
            "vertical_rule_positions": col_lines[:64],
            "cell_grid_estimate": {
                "rows": max(1, len(row_lines) - 1) if row_lines else 1,
                "columns": max(1, len(col_lines) - 1) if col_lines else 1,
            },
            "region_bbox": list(box),
        }

    def analyze(self, image_bytes: bytes) -> dict[str, Any]:
        page = self._open(image_bytes)
        boxes = self._reading_order(self.propose_regions(page), page.width)
        regions: list[Stage15Region] = []
        for order, box in enumerate(boxes):
            crop = page.crop(box)
            payload = Stage15LayoutVectorizer.payload(
                self._png(crop),
                bbox=box,
                page_width=page.width,
                page_height=page.height,
            )
            layout = self.layout_model.predict_payload(payload)
            label = str(layout["label"])
            text = ""
            text_confidence = 0.0
            structure: dict[str, Any] | None = None
            if label in TEXT_REGION_LABELS and self.ocr_model is not None:
                detail = self.ocr_model.predict_detailed(
                    {"image_png_b64": payload["image_png_b64"]}
                )
                text = str(detail["text"])
                text_confidence = float(detail["confidence"])
            elif label in HANDWRITING_REGION_LABELS and self.handwriting_model is not None:
                detail = self.handwriting_model.predict_detailed(
                    {"image_png_b64": payload["image_png_b64"]}
                )
                text = str(detail["text"])
                text_confidence = float(detail["confidence"])
            if label == "table":
                structure = self._table_structure(crop, box)
            elif label in {"form_field", "key_value", "checkbox"}:
                structure = {"kind": "form", "field_type": label, "region_bbox": list(box)}
            elif label in {"figure", "equation"}:
                structure = {"kind": label, "region_bbox": list(box)}
            regions.append(
                Stage15Region(
                    label=label,
                    confidence=float(layout["confidence"]),
                    bbox=box,
                    reading_order=order,
                    text=text,
                    text_confidence=text_confidence,
                    accepted=bool(layout["accepted"]),
                    rejection_reason=layout["rejection_reason"],
                    structure=structure,
                )
            )
        public = [
            region.public(page_width=page.width, page_height=page.height) for region in regions
        ]
        accepted = [region for region in regions if region.accepted]
        return {
            "schema_version": 1,
            "layout_version": "vishnu-layout/4-stage15",
            "page": {"width": page.width, "height": page.height},
            "regions": public,
            "reading_order": [region.reading_order for region in accepted],
            "text": "\n".join(region.text for region in accepted if region.text),
            "tables": [item for item in public if item["label"] == "table"],
            "forms": [
                item
                for item in public
                if item["label"] in {"form_field", "key_value", "checkbox"}
            ],
            "figures": [item for item in public if item["label"] in {"figure", "equation"}],
            "model_scope": "region_proposals_plus_neural_layout_plus_stage14_ctc",
            "stage14_ctc_text_backend": True,
            "real_world_corpus_qualified": False,
            "foundation_model": False,
        }


class LayoutBaseline(Protocol):
    baseline_id: str

    def predict(self, payload: dict[str, Any]) -> str: ...


class Stage15DocumentVisionCoordinator:
    """Governed Stage 15 layout train/shadow/owner/release lifecycle."""

    def __init__(
        self,
        *,
        content_models: ContentModelCoordinator,
        feedback: GovernedContentFeedbackStore,
        evidence_path: str | Path,
    ):
        self.content_models = content_models
        self.feedback = feedback
        self.evidence = ModelCycleEvidenceStore(evidence_path)

    def _prepare_samples(
        self,
        *,
        subtask: str = "document_layout",
        languages: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.feedback.approved_samples(
            ContentModelTask.LAYOUT, subtask=subtask, languages=languages
        )
        prepared: list[dict[str, Any]] = []
        for row in rows:
            original = row.get("input")
            if not isinstance(original, dict) or not original.get("image_png_b64"):
                raise Stage15PolicyError("Stage 15 layout feedback requires image_png_b64")
            label = str(row.get("label") or "")
            if label not in STAGE15_LAYOUT_LABELS:
                raise Stage15PolicyError(f"unsupported Stage 15 layout label: {label}")
            provenance = dict(row.get("provenance") or {})
            prepared.append(
                {
                    **row,
                    "input": dict(original),
                    "provenance": {
                        **provenance,
                        "stage15_document_layout": True,
                        "neural_layout_classifier": True,
                    },
                }
            )
        return prepared

    def train_candidate(
        self,
        *,
        subtask: str = "document_layout",
        languages: Iterable[str] | None = None,
        dataset_name: str | None = None,
    ) -> dict[str, Any]:
        samples = self._prepare_samples(subtask=subtask, languages=languages)
        return self.content_models.train(
            ContentModelTask.LAYOUT,
            samples,
            VishnuNeuralLayoutTrainer(),
            dataset_name=dataset_name or "vishnu-stage15-neural-document-layout",
            metadata={
                "stage": 15,
                "subtask": subtask,
                "languages": sorted({str(value) for value in (languages or ())}),
                "layout_version": "vishnu-layout/4-stage15",
                "labels_supported": list(STAGE15_LAYOUT_LABELS),
                "neural_layout_classifier": True,
                "region_proposals": "deterministic_whitespace_ink_regions",
                "stage14_ctc_text_backend": True,
                "real_world_corpus_qualified": False,
                "foundation_model": False,
                "trained_by_vishnu": True,
                "continuous_feedback": True,
                "requires_shadow_qualification": True,
                "requires_owner_approval": True,
                "requires_release_controller": True,
            },
        )

    def _snapshot_for(self, model: dict[str, Any]) -> ContentDatasetSnapshot:
        root = Path(self.content_models.datasets.root) / str(model["dataset_snapshot_id"])
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        return ContentDatasetSnapshot(
            snapshot_id=str(manifest["snapshot_id"]),
            task=ContentModelTask(str(manifest["task"])),
            created_at=str(manifest["created_at"]),
            root=str(root),
            train_path=str(root / "train.jsonl"),
            validation_path=str(root / "validation.jsonl"),
            test_path=str(root / "test.jsonl"),
            manifest_path=str(root / "manifest.json"),
            records=int(manifest["records"]),
            sha256=str(manifest["dataset_sha256"]),
        )

    def shadow_qualify(
        self,
        model_id: str,
        *,
        baseline: LayoutBaseline,
        min_f1_delta: float = 0.0,
    ) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        if model["task"] != ContentModelTask.LAYOUT.value or model["status"] != "candidate":
            raise ValueError("Stage 15 shadow qualification requires a layout candidate")
        snapshot = self._snapshot_for(model)
        rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path)
        if not rows:
            raise ValueError("Stage 15 shadow qualification requires a held-out split")
        candidate = VishnuNeuralLayoutRecognizer(model["checkpoint_ref"])
        truth = [str(row.get("label") or "") for row in rows]
        candidate_predictions = [
            str(
                candidate.predict_payload(
                    dict(row.get("input") or {}), reject_below=0.0
                )["label"]
            )
            for row in rows
        ]
        baseline_predictions = [
            str(baseline.predict(dict(row.get("input") or {})) or "unknown") for row in rows
        ]
        candidate_f1 = _macro_f1(truth, candidate_predictions)
        baseline_f1 = _macro_f1(truth, baseline_predictions)
        candidate_metrics = {
            "f1": candidate_f1,
            "accuracy": sum(int(a == b) for a, b in zip(truth, candidate_predictions))
            / max(1, len(truth)),
        }
        baseline_metrics = {
            "f1": baseline_f1,
            "accuracy": sum(int(a == b) for a, b in zip(truth, baseline_predictions))
            / max(1, len(truth)),
        }
        reasons = list(
            self.content_models.evaluator.evaluate_metrics(
                ContentModelTask.LAYOUT, candidate_metrics
            ).reasons
        )
        delta = candidate_f1 - baseline_f1
        if delta < float(min_f1_delta):
            reasons.append("candidate_layout_f1_delta_below_requirement")
        created_at = _now()
        deltas = {
            "f1": delta,
            "accuracy": candidate_metrics["accuracy"] - baseline_metrics["accuracy"],
        }
        payload = {
            "model_id": model_id,
            "task": ContentModelTask.LAYOUT.value,
            "baseline_id": str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            "records": len(rows),
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": deltas,
            "passed": not reasons,
            "reasons": reasons,
            "created_at": created_at,
        }
        evidence = ModelCycleEvidence(
            model_id=model_id,
            task=ContentModelTask.LAYOUT.value,
            baseline_id=payload["baseline_id"],
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas=deltas,
            passed=not reasons,
            reasons=tuple(reasons),
            evidence_sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
        return self.evidence.record(evidence)

    def approve(self, model_id: str, *, owner_id: str) -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError(
                "Stage 15 layout model requires successful shadow qualification before owner approval"
            )
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(
        self,
        model_id: str,
        *,
        owner_authorized: bool,
        actor: str = "release_controller",
    ) -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError(
                "Stage 15 layout model requires successful shadow qualification before activation"
            )
        return self.content_models.registry.activate(
            model_id, owner_authorized=owner_authorized, actor=actor
        )
