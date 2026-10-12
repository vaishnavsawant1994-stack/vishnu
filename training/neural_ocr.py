from __future__ import annotations

import base64
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

from training.content_models import ContentDatasetSnapshot, ContentModelTask
from training.continuous_content_models import ModelCycleEvidence, TesseractLineBaseline
from training.open_vocabulary_ocr import (
    LineTextBaseline,
    OpenVocabularyLineVectorizer,
    Stage13OpenVocabularyCoordinator,
    UnicodeGraphemeTokenizer,
    _best_boundaries,
    _blank_runs,
    _canonical,
    _component_segments,
    _crop_ink,
    _now,
    _read_jsonl,
    _resize_segment,
    _text_metrics,
    _training_segments,
)


class Stage14NeuralPolicyError(ValueError):
    pass


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.maximum(np.sum(exp, axis=1, keepdims=True), 1e-12)


def _feature_vector(image: Image.Image, *, width: int, height: int) -> np.ndarray:
    return np.asarray(_resize_segment(image, width, height), dtype=np.float64)


class VishnuNeuralGraphemeTrainer:
    """Vishnu-owned trainable neural grapheme encoder for the Stage 14 baseline.

    This establishes the governed neural OCR/HTR lifecycle without claiming
    foundation-model status. A later Stage 14 tranche can replace the geometry
    decoder with sequence-level CTC/attention while preserving this governance.
    """

    def __init__(
        self,
        *,
        task: ContentModelTask = ContentModelTask.OCR,
        feature_width: int = 12,
        feature_height: int = 16,
        hidden_size: int = 48,
        epochs: int = 450,
        learning_rate: float = 0.12,
    ):
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("Stage 14 neural trainer supports OCR or handwriting")
        self.task = task
        self.backend_id = (
            "vishnu-neural-grapheme-ocr-v1"
            if task is ContentModelTask.OCR
            else "vishnu-neural-grapheme-handwriting-v1"
        )
        self.feature_width = max(8, min(int(feature_width), 32))
        self.feature_height = max(12, min(int(feature_height), 48))
        self.hidden_size = max(8, min(int(hidden_size), 128))
        self.epochs = max(50, min(int(epochs), 2000))
        self.learning_rate = max(0.005, min(float(learning_rate), 0.5))

    def _training_matrix(
        self, rows: list[dict[str, Any]]
    ) -> tuple[np.ndarray, list[str], dict[str, list[int]]]:
        vectors: list[np.ndarray] = []
        labels: list[str] = []
        widths: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            payload = dict(row.get("input") or {})
            image = OpenVocabularyLineVectorizer.image(payload)
            tokens = UnicodeGraphemeTokenizer.tokenize(str(row.get("label") or ""))
            for token, segment, raw_width in _training_segments(image, tokens):
                vectors.append(
                    _feature_vector(
                        segment,
                        width=self.feature_width,
                        height=self.feature_height,
                    )
                )
                labels.append(token)
                widths[token].append(max(1, int(raw_width)))
        if len(set(labels)) < 2:
            raise ValueError("Stage 14 neural model requires at least two learned graphemes")
        return np.stack(vectors), labels, widths

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("Stage 14 neural trainer task mismatch")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("Stage 14 neural train split is empty")

        x, labels, widths = self._training_matrix(rows)
        vocabulary = sorted(set(labels))
        class_index = {token: index for index, token in enumerate(vocabulary)}
        targets = np.asarray([class_index[token] for token in labels], dtype=np.int64)
        one_hot = np.eye(len(vocabulary), dtype=np.float64)[targets]

        seed = int(snapshot.sha256[:16], 16) % (2**32)
        rng = np.random.default_rng(seed)
        scale1 = np.sqrt(2.0 / max(1, x.shape[1] + self.hidden_size))
        scale2 = np.sqrt(2.0 / max(1, self.hidden_size + len(vocabulary)))
        w1 = rng.normal(0.0, scale1, size=(x.shape[1], self.hidden_size))
        b1 = np.zeros((1, self.hidden_size), dtype=np.float64)
        w2 = rng.normal(0.0, scale2, size=(self.hidden_size, len(vocabulary)))
        b2 = np.zeros((1, len(vocabulary)), dtype=np.float64)

        sample_count = float(len(x))
        for epoch in range(self.epochs):
            hidden = np.tanh(x @ w1 + b1)
            probs = _softmax(hidden @ w2 + b2)
            dlogits = (probs - one_hot) / sample_count
            dw2 = hidden.T @ dlogits
            db2 = np.sum(dlogits, axis=0, keepdims=True)
            dhidden = (dlogits @ w2.T) * (1.0 - hidden * hidden)
            dw1 = x.T @ dhidden
            db1 = np.sum(dhidden, axis=0, keepdims=True)
            rate = self.learning_rate / np.sqrt(1.0 + epoch / 80.0)
            w2 -= rate * dw2
            b2 -= rate * db2
            w1 -= rate * dw1
            b1 -= rate * db1

        all_widths = sorted(value for values in widths.values() for value in values)
        median_width = float(all_widths[len(all_widths) // 2])
        model = {
            "schema_version": 1,
            "model_type": "vishnu-stage14-neural-open-vocabulary-grapheme",
            "model_scope": "open_vocabulary_line_sequence",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "architecture": {
                "family": "mlp_visual_grapheme_encoder",
                "input_width": self.feature_width,
                "input_height": self.feature_height,
                "hidden_size": self.hidden_size,
                "activation": "tanh",
                "output": "softmax_graphemes",
                "decoder": "stage13_geometry_sequence_v1",
            },
            "open_vocabulary": True,
            "lexicon_required": False,
            "neural_encoder": True,
            "sequence_ctc_ready": False,
            "foundation_model": False,
            "vocabulary": vocabulary,
            "median_source_token_width": median_width,
            "mean_source_widths": {
                token: round(sum(values) / len(values), 4)
                for token, values in sorted(widths.items())
            },
            "weights": {
                "w1": w1.round(9).tolist(),
                "b1": b1.round(9).tolist(),
                "w2": w2.round(9).tolist(),
                "b2": b2.round(9).tolist(),
            },
            "training": {
                "epochs": self.epochs,
                "learning_rate": self.learning_rate,
                "seed": seed,
                "records": len(rows),
                "grapheme_segments": len(labels),
            },
            "trained_by_vishnu": True,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(
            json.dumps(model, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

        recognizer = VishnuNeuralOpenVocabularyRecognizer.from_model(model)
        eval_rows = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        truth: list[str] = []
        predicted: list[str] = []
        started = time.perf_counter()
        for row in eval_rows:
            truth.append(str(row.get("label") or ""))
            predicted.append(recognizer.predict_payload(dict(row.get("input") or {}))[0])
        metrics = _text_metrics(truth, predicted, (time.perf_counter() - started) * 1000.0)
        metrics["grapheme_vocabulary"] = float(len(vocabulary))
        metrics["open_vocabulary"] = 1.0
        metrics["neural_encoder"] = 1.0
        return output_dir, metrics


class VishnuNeuralOpenVocabularyRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        self._load(json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8")))

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "VishnuNeuralOpenVocabularyRecognizer":
        value = cls.__new__(cls)
        value._load(model)
        return value

    def _load(self, model: dict[str, Any]) -> None:
        if model.get("model_type") != "vishnu-stage14-neural-open-vocabulary-grapheme":
            raise ValueError("unsupported Stage 14 Vishnu neural OCR artifact")
        architecture = dict(model["architecture"])
        self.model = model
        self.feature_width = int(architecture["input_width"])
        self.feature_height = int(architecture["input_height"])
        self.vocabulary = [str(token) for token in model["vocabulary"]]
        weights = dict(model["weights"])
        self.w1 = np.asarray(weights["w1"], dtype=np.float64)
        self.b1 = np.asarray(weights["b1"], dtype=np.float64)
        self.w2 = np.asarray(weights["w2"], dtype=np.float64)
        self.b2 = np.asarray(weights["b2"], dtype=np.float64)
        self.median_width = max(2.0, float(model.get("median_source_token_width") or 8.0))

    def _classify(self, segment: Image.Image) -> tuple[str, float]:
        vector = _feature_vector(
            segment,
            width=self.feature_width,
            height=self.feature_height,
        )[None, :]
        hidden = np.tanh(vector @ self.w1 + self.b1)
        probabilities = _softmax(hidden @ self.w2 + self.b2)[0]
        index = int(np.argmax(probabilities))
        return self.vocabulary[index], float(probabilities[index])

    def _word_regions(self, image: Image.Image) -> list[Image.Image]:
        image = _crop_ink(image)
        min_gap = max(4, int(round(self.median_width * 0.65)))
        gaps = [
            pair
            for pair in _blank_runs(image)
            if pair[0] > 0 and pair[1] < image.width and pair[1] - pair[0] >= min_gap
        ]
        if not gaps:
            return [image] if image.width > 0 else []
        output: list[Image.Image] = []
        left = 0
        for start, end in gaps:
            if start > left:
                region = _crop_ink(image.crop((left, 0, start, image.height)))
                if region.width > 0:
                    output.append(region)
            left = end
        if left < image.width:
            region = _crop_ink(image.crop((left, 0, image.width, image.height)))
            if region.width > 0:
                output.append(region)
        return output

    def _decode_word(self, image: Image.Image) -> tuple[str, float]:
        image = _crop_ink(image)
        if image.width <= 0:
            return "", 0.0
        char_gap = max(1, int(round(self.median_width * 0.12)))
        segments = _component_segments(image, min_gap=char_gap)
        if len(segments) == 1 and image.width > self.median_width * 1.45:
            estimated = max(1, min(256, int(round(image.width / self.median_width))))
            boundaries = _best_boundaries(image, estimated)
            segments = [
                image.crop((start, 0, max(start + 1, end), image.height))
                for start, end in zip(boundaries, boundaries[1:])
            ]
        decoded = [self._classify(segment) for segment in segments]
        if not decoded:
            return "", 0.0
        return "".join(token for token, _ in decoded), sum(conf for _, conf in decoded) / len(decoded)

    def predict_payload(self, payload: dict[str, Any]) -> tuple[str, float]:
        return self.predict_image_object(OpenVocabularyLineVectorizer.image(payload))

    def predict_image(self, image_bytes: bytes) -> tuple[str, float]:
        payload = OpenVocabularyLineVectorizer().payload(image_bytes)
        return self.predict_payload(payload)

    def predict_image_object(self, image: Image.Image) -> tuple[str, float]:
        words = self._word_regions(image.convert("L"))
        if not words:
            return "", 0.0
        decoded = [self._decode_word(word) for word in words]
        return " ".join(text for text, _ in decoded), sum(conf for _, conf in decoded) / len(decoded)


class Stage14NeuralOCRCoordinator(Stage13OpenVocabularyCoordinator):
    """Governed Stage 14 train -> shadow -> owner approval -> activation path."""

    def _prepare_samples(
        self,
        *,
        task: ContentModelTask,
        subtask: str,
        languages: Iterable[str] | None,
    ) -> list[dict[str, Any]]:
        prepared = super()._prepare_samples(task=task, subtask=subtask, languages=languages)
        for row in prepared:
            provenance = dict(row.get("provenance") or {})
            provenance["stage14_neural"] = True
            row["provenance"] = provenance
        return prepared

    def train_candidate(
        self,
        *,
        task: ContentModelTask,
        subtask: str,
        languages: Iterable[str] | None = None,
        dataset_name: str | None = None,
    ) -> dict[str, Any]:
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("Stage 14 supports OCR or handwriting neural models")
        prepared = self._prepare_samples(task=task, subtask=subtask, languages=languages)
        vocabulary = UnicodeGraphemeTokenizer.vocabulary(str(row.get("label") or "") for row in prepared)
        if len(vocabulary) < 2:
            raise ValueError("Stage 14 requires at least two learned graphemes")
        return self.content_models.train(
            task,
            prepared,
            VishnuNeuralGraphemeTrainer(task=task),
            dataset_name=dataset_name or f"vishnu-{subtask}-stage14-neural",
            metadata={
                "stage": 14,
                "subtask": str(subtask),
                "languages": sorted({str(item) for item in (languages or ())}),
                "grapheme_vocabulary": list(vocabulary),
                "model_scope": "open_vocabulary_line_sequence",
                "open_vocabulary": True,
                "lexicon_required": False,
                "neural_encoder": True,
                "foundation_model": False,
                "sequence_ctc_ready": False,
                "stage13_geometry_decoder_reused": True,
                "trained_by_vishnu": True,
                "continuous_feedback": True,
                "requires_shadow_qualification": True,
                "requires_owner_approval": True,
                "requires_release_controller": True,
            },
        )

    def shadow_qualify(
        self,
        model_id: str,
        *,
        baseline: LineTextBaseline | None = None,
        max_cer_regression: float = 0.0,
        min_char_accuracy_delta: float = 0.0,
    ) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        task = ContentModelTask(str(model["task"]))
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING} or model["status"] != "candidate":
            raise ValueError("Stage 14 shadow qualification requires an OCR/handwriting candidate")
        snapshot = self._snapshot_for(model)
        rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path)
        if not rows:
            raise ValueError("Stage 14 shadow qualification requires a held-out split")

        candidate = VishnuNeuralOpenVocabularyRecognizer(model["checkpoint_ref"])
        truth: list[str] = []
        candidate_predictions: list[str] = []
        baseline_predictions: list[str] = []
        started = time.perf_counter()
        for row in rows:
            truth.append(str(row.get("label") or ""))
            candidate_predictions.append(candidate.predict_payload(dict(row.get("input") or {}))[0])
        candidate_ms = (time.perf_counter() - started) * 1000.0

        baseline = baseline or TesseractLineBaseline()
        baseline_error = None
        started = time.perf_counter()
        try:
            for row in rows:
                encoded = str(dict(row.get("input") or {}).get("image_png_b64") or "")
                baseline_predictions.append(str(baseline.predict(base64.b64decode(encoded, validate=True)) or ""))
        except Exception as exc:
            baseline_error = f"baseline_unavailable:{exc.__class__.__name__}"
        baseline_ms = (time.perf_counter() - started) * 1000.0

        candidate_metrics = _text_metrics(truth, candidate_predictions, candidate_ms)
        baseline_metrics = (
            _text_metrics(truth, baseline_predictions, baseline_ms)
            if baseline_error is None and len(baseline_predictions) == len(truth)
            else _text_metrics(truth, [""] * len(truth), baseline_ms)
        )
        reasons = list(self.content_models.evaluator.evaluate_metrics(task, candidate_metrics).reasons)
        if baseline_error:
            reasons.append(baseline_error)
        if candidate_metrics["cer"] > baseline_metrics["cer"] + float(max_cer_regression):
            reasons.append("candidate_cer_worse_than_baseline")
        char_delta = candidate_metrics["char_accuracy"] - baseline_metrics["char_accuracy"]
        if char_delta < float(min_char_accuracy_delta):
            reasons.append("candidate_char_accuracy_delta_below_requirement")

        created_at = _now()
        deltas = {
            "cer": candidate_metrics["cer"] - baseline_metrics["cer"],
            "char_accuracy": char_delta,
            "avg_latency_ms": candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
        }
        evidence_payload = {
            "model_id": model_id,
            "task": task.value,
            "baseline_id": str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            "records": len(rows),
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": deltas,
            "passed": not reasons,
            "reasons": reasons,
            "created_at": created_at,
            "stage": 14,
        }
        evidence = ModelCycleEvidence(
            model_id=model_id,
            task=task.value,
            baseline_id=evidence_payload["baseline_id"],
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas=deltas,
            passed=not reasons,
            reasons=tuple(reasons),
            evidence_sha256=hashlib.sha256(_canonical(evidence_payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
        return self.evidence.record(evidence)

    def approve(self, model_id: str, *, owner_id: str) -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 14 model requires successful shadow qualification before owner approval")
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
            raise ValueError("Stage 14 model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(
            model_id,
            owner_authorized=owner_authorized,
            actor=actor,
        )
