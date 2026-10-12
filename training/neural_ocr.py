from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from training.content_models import ContentDatasetSnapshot, ContentModelTask
from training.continuous_content_models import ModelCycleEvidence, TesseractLineBaseline
from training.open_vocabulary_ocr import (
    LineTextBaseline,
    OpenVocabularyLineVectorizer,
    Stage13OpenVocabularyCoordinator,
    UnicodeGraphemeTokenizer,
    _canonical,
    _now,
    _read_jsonl,
    _text_metrics,
)


class Stage14NeuralPolicyError(ValueError):
    pass


_AUGMENTATION_PROFILES = (
    "rotation",
    "blur",
    "perspective",
    "noise",
    "lighting",
    "compression",
    "scan",
    "screenshot",
    "photo",
)


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.maximum(np.sum(exp, axis=1, keepdims=True), 1e-12)


def _logsumexp(values: Iterable[float]) -> float:
    values = np.asarray(list(values), dtype=np.float64)
    if values.size == 0:
        return float("-inf")
    maximum = float(np.max(values))
    if not math.isfinite(maximum):
        return maximum
    return maximum + float(np.log(np.sum(np.exp(values - maximum))))


def _normalize_line(image: Image.Image, *, height: int, max_width: int = 1024) -> Image.Image:
    gray = ImageOps.autocontrast(ImageOps.exif_transpose(image).convert("L"))
    array = np.asarray(gray, dtype=np.float64)
    ink = 1.0 - array / 255.0
    ys, xs = np.where(ink > 0.035)
    if xs.size:
        left = max(0, int(xs.min()) - 2)
        right = min(gray.width, int(xs.max()) + 3)
        top = max(0, int(ys.min()) - 2)
        bottom = min(gray.height, int(ys.max()) + 3)
        gray = gray.crop((left, top, right, bottom))
    scale = float(height) / max(1, gray.height)
    width = max(4, min(int(round(gray.width * scale)), int(max_width)))
    return gray.resize((width, int(height)), Image.Resampling.BILINEAR)


def _temporal_features(
    image: Image.Image,
    *,
    height: int,
    stride: int,
    context_width: int,
) -> tuple[np.ndarray, float]:
    normalized = _normalize_line(image, height=height)
    ink = 1.0 - np.asarray(normalized, dtype=np.float64) / 255.0
    total_ink = float(np.mean(ink))
    column_ink = np.mean(ink, axis=0)
    blank = column_ink < 0.02
    width = ink.shape[1]

    run_length = np.zeros(width, dtype=np.float64)
    index = 0
    while index < width:
        if not bool(blank[index]):
            index += 1
            continue
        end = index + 1
        while end < width and bool(blank[end]):
            end += 1
        run_length[index:end] = float(end - index)
        index = end

    left_distance = np.zeros(width, dtype=np.float64)
    right_distance = np.zeros(width, dtype=np.float64)
    previous = -width
    for x in range(width):
        if not bool(blank[x]):
            previous = x
        left_distance[x] = min(width, x - previous)
    following = width * 2
    for x in range(width - 1, -1, -1):
        if not bool(blank[x]):
            following = x
        right_distance[x] = min(width, following - x)

    context_width = max(3, int(context_width) | 1)
    pad = context_width // 2
    padded = np.pad(ink, ((0, 0), (pad, pad)), constant_values=0.0)
    frames: list[np.ndarray] = []
    for x in range(0, width, max(1, int(stride))):
        patch = padded[:, x : x + context_width]
        extras = np.asarray(
            [
                column_ink[x],
                min(1.0, run_length[x] / max(1.0, width)),
                min(1.0, left_distance[x] / max(1.0, width)),
                min(1.0, right_distance[x] / max(1.0, width)),
            ],
            dtype=np.float64,
        )
        frames.append(np.concatenate((patch.reshape(-1), extras)))
    if not frames:
        frames.append(np.zeros(height * context_width + 4, dtype=np.float64))
    return np.stack(frames), total_ink


def _apply_augmentation(image: Image.Image, profile: str, *, seed: int) -> Image.Image:
    profile = str(profile)
    gray = ImageOps.exif_transpose(image).convert("L")
    rng = np.random.default_rng(int(seed) % (2**32))
    if profile == "clean":
        return gray.copy()
    if profile == "rotation":
        angle = 0.8 if seed % 2 == 0 else -0.8
        return gray.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=255)
    if profile == "blur":
        return gray.filter(ImageFilter.GaussianBlur(radius=0.2))
    if profile == "perspective":
        shear = 0.012 if seed % 2 == 0 else -0.012
        return gray.transform(
            gray.size,
            Image.Transform.AFFINE,
            (1.0, shear, -shear * gray.height / 2.0, 0.003, 1.0, 0.0),
            resample=Image.Resampling.BILINEAR,
            fillcolor=255,
        )
    if profile == "noise":
        array = np.asarray(gray, dtype=np.int16)
        noise = rng.normal(0.0, 1.2, size=array.shape)
        return Image.fromarray(np.clip(array + noise, 0, 255).astype(np.uint8), "L")
    if profile == "lighting":
        value = ImageEnhance.Brightness(gray).enhance(0.98)
        return ImageEnhance.Contrast(value).enhance(0.98)
    if profile == "compression":
        buffer = io.BytesIO()
        gray.save(buffer, format="JPEG", quality=90, optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as compressed:
            compressed.load()
            return compressed.convert("L").copy()
    if profile == "scan":
        value = ImageOps.autocontrast(gray).filter(ImageFilter.GaussianBlur(radius=0.1))
        buffer = io.BytesIO()
        value.save(buffer, format="JPEG", quality=90, optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as scanned:
            scanned.load()
            return scanned.convert("L").copy()
    if profile == "screenshot":
        up = gray.resize((max(4, gray.width * 2), max(4, gray.height * 2)), Image.Resampling.BICUBIC)
        return up.resize(gray.size, Image.Resampling.LANCZOS).filter(ImageFilter.SHARPEN)
    if profile == "photo":
        value = _apply_augmentation(gray, "perspective", seed=seed)
        value = ImageEnhance.Brightness(value).enhance(0.98)
        array = np.asarray(value, dtype=np.int16)
        noise = rng.normal(0.0, 0.8, size=array.shape)
        return Image.fromarray(np.clip(array + noise, 0, 255).astype(np.uint8), "L")
    raise ValueError(f"unsupported Stage 14 augmentation profile: {profile}")


def _ctc_posteriors(
    log_probabilities: np.ndarray,
    targets: list[int],
    blank_index: int,
) -> tuple[np.ndarray, float]:
    timesteps, classes = log_probabilities.shape
    if not targets:
        posterior = np.zeros((timesteps, classes), dtype=np.float64)
        posterior[:, blank_index] = 1.0
        return posterior, float(-np.sum(log_probabilities[:, blank_index]))
    if timesteps < len(targets):
        raise Stage14NeuralPolicyError("CTC temporal sequence is shorter than the transcript")

    extended = [blank_index]
    for token in targets:
        extended.extend((int(token), blank_index))
    states = len(extended)
    alpha = np.full((timesteps, states), float("-inf"), dtype=np.float64)
    alpha[0, 0] = log_probabilities[0, blank_index]
    if states > 1:
        alpha[0, 1] = log_probabilities[0, extended[1]]
    for t in range(1, timesteps):
        for state in range(states):
            previous = [alpha[t - 1, state]]
            if state > 0:
                previous.append(alpha[t - 1, state - 1])
            if state > 1 and extended[state] != blank_index and extended[state] != extended[state - 2]:
                previous.append(alpha[t - 1, state - 2])
            alpha[t, state] = log_probabilities[t, extended[state]] + _logsumexp(previous)

    log_partition = _logsumexp(
        (alpha[timesteps - 1, states - 1], alpha[timesteps - 1, states - 2])
    )
    beta = np.full((timesteps, states), float("-inf"), dtype=np.float64)
    beta[timesteps - 1, states - 1] = 0.0
    beta[timesteps - 1, states - 2] = 0.0
    for t in range(timesteps - 2, -1, -1):
        for state in range(states):
            following = [
                log_probabilities[t + 1, extended[state]] + beta[t + 1, state]
            ]
            if state + 1 < states:
                following.append(
                    log_probabilities[t + 1, extended[state + 1]] + beta[t + 1, state + 1]
                )
            if (
                state + 2 < states
                and extended[state] != blank_index
                and extended[state] != extended[state + 2]
            ):
                following.append(
                    log_probabilities[t + 1, extended[state + 2]] + beta[t + 1, state + 2]
                )
            beta[t, state] = _logsumexp(following)

    posterior = np.zeros((timesteps, classes), dtype=np.float64)
    for t in range(timesteps):
        for state, class_index in enumerate(extended):
            value = alpha[t, state] + beta[t, state] - log_partition
            if value > -60.0:
                posterior[t, class_index] += math.exp(value)
    posterior /= np.maximum(np.sum(posterior, axis=1, keepdims=True), 1e-12)
    return posterior, float(-log_partition)


def _ctc_prefix_beam_search(
    probabilities: np.ndarray,
    vocabulary: list[str],
    blank_index: int,
    *,
    beam_width: int,
) -> tuple[str, float, list[tuple[str, float]]]:
    log_probabilities = np.log(np.maximum(probabilities, 1e-12))
    negative = -1e30
    beams: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, negative)}

    def add(
        target: dict[tuple[int, ...], tuple[float, float]],
        prefix: tuple[int, ...],
        *,
        blank_value: float | None = None,
        nonblank_value: float | None = None,
    ) -> None:
        old_blank, old_nonblank = target.get(prefix, (negative, negative))
        if blank_value is not None:
            old_blank = _logsumexp((old_blank, blank_value))
        if nonblank_value is not None:
            old_nonblank = _logsumexp((old_nonblank, nonblank_value))
        target[prefix] = (old_blank, old_nonblank)

    for t in range(log_probabilities.shape[0]):
        next_beams: dict[tuple[int, ...], tuple[float, float]] = {}
        for prefix, (blank_score, nonblank_score) in beams.items():
            total = _logsumexp((blank_score, nonblank_score))
            add(
                next_beams,
                prefix,
                blank_value=total + log_probabilities[t, blank_index],
            )
            for class_index in range(len(vocabulary)):
                token_score = log_probabilities[t, class_index]
                if prefix and prefix[-1] == class_index:
                    add(
                        next_beams,
                        prefix,
                        nonblank_value=nonblank_score + token_score,
                    )
                    add(
                        next_beams,
                        prefix + (class_index,),
                        nonblank_value=blank_score + token_score,
                    )
                else:
                    add(
                        next_beams,
                        prefix + (class_index,),
                        nonblank_value=total + token_score,
                    )
        ranked = sorted(
            next_beams.items(),
            key=lambda item: _logsumexp(item[1]),
            reverse=True,
        )[: max(2, int(beam_width))]
        beams = dict(ranked)

    ranked_final = sorted(
        ((prefix, _logsumexp(scores)) for prefix, scores in beams.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked_final:
        return "", 0.0, []
    denominator = _logsumexp(score for _, score in ranked_final)
    best_prefix, best_score = ranked_final[0]
    posterior = max(0.0, min(1.0, math.exp(best_score - denominator)))
    # Raw sequence posterior falls exponentially with decoded length even when
    # each grapheme is locally strong. Normalize it geometrically per decoded
    # grapheme so rejection confidence remains comparable across line lengths.
    confidence = posterior ** (1.0 / max(1, len(best_prefix)))
    alternatives = [
        ("".join(vocabulary[index] for index in prefix), float(score))
        for prefix, score in ranked_final[:3]
    ]
    return "".join(vocabulary[index] for index in best_prefix), confidence, alternatives


class VishnuNeuralCTCTrainer:
    """Whole-line temporal neural OCR/HTR trained with a CTC objective.

    The trainer never consumes Stage 13 character components or estimated
    character boundaries. Approved line images are converted into temporal
    visual frames and optimized directly against whole-line Unicode grapheme
    transcripts with CTC forward/backward training.
    """

    def __init__(
        self,
        *,
        task: ContentModelTask = ContentModelTask.OCR,
        feature_height: int = 20,
        context_width: int = 7,
        stride: int = 2,
        hidden_size: int = 40,
        epochs: int = 120,
        learning_rate: float = 0.07,
        beam_width: int = 12,
    ):
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("Stage 14 CTC trainer supports OCR or handwriting")
        self.task = task
        self.backend_id = (
            "vishnu-neural-ctc-ocr-v2"
            if task is ContentModelTask.OCR
            else "vishnu-neural-ctc-handwriting-v2"
        )
        self.feature_height = max(12, min(int(feature_height), 48))
        self.context_width = max(3, min(int(context_width) | 1, 15))
        self.stride = max(1, min(int(stride), 4))
        self.hidden_size = max(16, min(int(hidden_size), 128))
        self.epochs = max(40, min(int(epochs), 600))
        self.learning_rate = max(0.005, min(float(learning_rate), 0.2))
        self.beam_width = max(4, min(int(beam_width), 32))

    def _training_sequences(
        self,
        rows: list[dict[str, Any]],
        vocabulary: list[str],
        snapshot_sha: str,
    ) -> tuple[list[tuple[np.ndarray, list[int]]], dict[str, int]]:
        index = {token: position for position, token in enumerate(vocabulary)}
        sequences: list[tuple[np.ndarray, list[int]]] = []
        augmentation_counts: Counter[str] = Counter()
        profiles = list(_AUGMENTATION_PROFILES)
        for row_index, row in enumerate(rows):
            payload = dict(row.get("input") or {})
            image = OpenVocabularyLineVectorizer.image(payload)
            tokens = UnicodeGraphemeTokenizer.tokenize(str(row.get("label") or ""))
            targets = [index[token] for token in tokens]
            row_seed = int(
                hashlib.sha256(
                    f"{snapshot_sha}:{row.get('id')}:{row_index}".encode("utf-8")
                ).hexdigest()[:16],
                16,
            )
            variants = [("clean", image)]
            for offset in range(2):
                profile = profiles[(row_index * 2 + offset) % len(profiles)]
                variants.append((profile, _apply_augmentation(image, profile, seed=row_seed + offset)))
            for profile, variant in variants:
                features, _ = _temporal_features(
                    variant,
                    height=self.feature_height,
                    stride=self.stride,
                    context_width=self.context_width,
                )
                sequences.append((features, targets))
                augmentation_counts[profile] += 1
        return sequences, dict(sorted(augmentation_counts.items()))

    @staticmethod
    def _gradient_clip(gradients: list[np.ndarray], maximum: float = 5.0) -> list[np.ndarray]:
        norm = math.sqrt(sum(float(np.sum(value * value)) for value in gradients))
        if norm <= maximum or norm <= 0.0:
            return gradients
        scale = maximum / norm
        return [value * scale for value in gradients]

    def _model_payload(
        self,
        *,
        snapshot: ContentDatasetSnapshot,
        vocabulary: list[str],
        w1: np.ndarray,
        b1: np.ndarray,
        w2: np.ndarray,
        b2: np.ndarray,
        augmentation_counts: dict[str, int],
        seed: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "model_type": "vishnu-stage14-neural-ctc-open-vocabulary",
            "model_scope": "whole_line_temporal_sequence",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "architecture": {
                "family": "temporal_mlp_ctc",
                "visual_encoder": "sliding_context_mlp",
                "input_height": self.feature_height,
                "context_width": self.context_width,
                "stride": self.stride,
                "hidden_size": self.hidden_size,
                "activation": "tanh",
                "sequence_objective": "ctc_forward_backward",
                "decoder": "ctc_prefix_beam_search",
                "beam_width": self.beam_width,
                "stage13_character_geometry": False,
            },
            "open_vocabulary": True,
            "lexicon_required": False,
            "neural_encoder": True,
            "sequence_ctc_ready": True,
            "foundation_model": False,
            "real_world_corpus_qualified": False,
            "vocabulary": vocabulary,
            "blank_index": len(vocabulary),
            "weights": {
                "w1": w1.round(9).tolist(),
                "b1": b1.round(9).tolist(),
                "w2": w2.round(9).tolist(),
                "b2": b2.round(9).tolist(),
            },
            "calibration": {
                "temperature": 1.0,
                "reject_threshold": 0.0,
                "method": "heldout_sequence_brier_grid",
            },
            "augmentation": {
                "profiles_supported": list(_AUGMENTATION_PROFILES),
                "training_variant_counts": augmentation_counts,
                "capture_simulations": ["scan", "screenshot", "photo"],
                "real_images_claimed": False,
            },
            "training": {
                "epochs": self.epochs,
                "learning_rate": self.learning_rate,
                "seed": seed,
                "records": int(snapshot.records),
                "objective": "ctc_forward_backward",
            },
            "trained_by_vishnu": True,
            "created_at": _now(),
        }

    def _calibrate(self, model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return dict(model["calibration"])
        best: tuple[float, float, list[float], list[bool]] | None = None
        for temperature in (0.75, 1.0, 1.25, 1.5, 2.0):
            recognizer = VishnuNeuralOpenVocabularyRecognizer.from_model(model)
            confidences: list[float] = []
            correct: list[bool] = []
            for row in rows:
                detail = recognizer.predict_detailed(
                    dict(row.get("input") or {}),
                    reject_below=0.0,
                    temperature_override=temperature,
                )
                truth = str(row.get("label") or "")
                confidences.append(float(detail["confidence"]))
                correct.append(str(detail["raw_text"]) == truth)
            brier = float(
                np.mean(
                    [
                        (confidence - (1.0 if is_correct else 0.0)) ** 2
                        for confidence, is_correct in zip(confidences, correct)
                    ]
                )
            )
            candidate = (brier, temperature, confidences, correct)
            if best is None or candidate[0] < best[0]:
                best = candidate
        assert best is not None
        _, temperature, confidences, correct = best
        correct_confidences = [value for value, passed in zip(confidences, correct) if passed]
        if correct_confidences:
            reject_threshold = max(0.18, min(0.60, min(correct_confidences) * 0.55))
        else:
            reject_threshold = 0.50
        return {
            "temperature": float(temperature),
            "reject_threshold": float(reject_threshold),
            "method": "heldout_sequence_brier_grid",
            "records": len(rows),
            "correct_records": sum(1 for value in correct if value),
            "brier": float(best[0]),
        }

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("Stage 14 neural CTC trainer task mismatch")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("Stage 14 neural CTC train split is empty")
        vocabulary = sorted(
            {
                token
                for row in rows
                for token in UnicodeGraphemeTokenizer.tokenize(str(row.get("label") or ""))
            }
        )
        if len(vocabulary) < 2:
            raise ValueError("Stage 14 neural CTC model requires at least two learned graphemes")

        sequences, augmentation_counts = self._training_sequences(rows, vocabulary, snapshot.sha256)
        input_size = int(sequences[0][0].shape[1])
        class_count = len(vocabulary) + 1
        blank_index = len(vocabulary)
        seed = int(snapshot.sha256[:16], 16) % (2**32)
        rng = np.random.default_rng(seed)
        w1 = rng.normal(
            0.0,
            np.sqrt(2.0 / max(1, input_size + self.hidden_size)),
            size=(input_size, self.hidden_size),
        )
        b1 = np.zeros((1, self.hidden_size), dtype=np.float64)
        w2 = rng.normal(
            0.0,
            np.sqrt(2.0 / max(1, self.hidden_size + class_count)),
            size=(self.hidden_size, class_count),
        )
        b2 = np.zeros((1, class_count), dtype=np.float64)

        for epoch in range(self.epochs):
            gradients = [np.zeros_like(w1), np.zeros_like(b1), np.zeros_like(w2), np.zeros_like(b2)]
            for features, targets in sequences:
                hidden = np.tanh(features @ w1 + b1)
                probabilities = _softmax(hidden @ w2 + b2)
                posterior, _ = _ctc_posteriors(
                    np.log(np.maximum(probabilities, 1e-12)),
                    targets,
                    blank_index,
                )
                dlogits = (probabilities - posterior) / float(len(sequences))
                gradients[2] += hidden.T @ dlogits
                gradients[3] += np.sum(dlogits, axis=0, keepdims=True)
                dhidden = (dlogits @ w2.T) * (1.0 - hidden * hidden)
                gradients[0] += features.T @ dhidden
                gradients[1] += np.sum(dhidden, axis=0, keepdims=True)
            gradients = self._gradient_clip(gradients)
            rate = self.learning_rate / math.sqrt(1.0 + epoch / 60.0)
            w1 -= rate * gradients[0]
            b1 -= rate * gradients[1]
            w2 -= rate * gradients[2]
            b2 -= rate * gradients[3]

        model = self._model_payload(
            snapshot=snapshot,
            vocabulary=vocabulary,
            w1=w1,
            b1=b1,
            w2=w2,
            b2=b2,
            augmentation_counts=augmentation_counts,
            seed=seed,
        )
        calibration_rows = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path)
        model["calibration"] = self._calibrate(model, calibration_rows)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(
            json.dumps(model, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

        recognizer = VishnuNeuralOpenVocabularyRecognizer.from_model(model)
        eval_rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path) or rows
        truth: list[str] = []
        predicted: list[str] = []
        rejected = 0
        started = time.perf_counter()
        for row in eval_rows:
            truth.append(str(row.get("label") or ""))
            detail = recognizer.predict_detailed(dict(row.get("input") or {}))
            predicted.append(str(detail["text"]))
            rejected += 0 if detail["accepted"] else 1
        metrics = _text_metrics(truth, predicted, (time.perf_counter() - started) * 1000.0)
        metrics["grapheme_vocabulary"] = float(len(vocabulary))
        metrics["open_vocabulary"] = 1.0
        metrics["neural_encoder"] = 1.0
        metrics["sequence_ctc"] = 1.0
        metrics["rejection_rate"] = rejected / max(1.0, float(len(eval_rows)))
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
        if model.get("model_type") != "vishnu-stage14-neural-ctc-open-vocabulary":
            raise ValueError("unsupported Stage 14 Vishnu neural CTC OCR artifact")
        architecture = dict(model["architecture"])
        self.model = model
        self.feature_height = int(architecture["input_height"])
        self.context_width = int(architecture["context_width"])
        self.stride = int(architecture["stride"])
        self.beam_width = int(architecture["beam_width"])
        self.vocabulary = [str(token) for token in model["vocabulary"]]
        self.blank_index = int(model["blank_index"])
        weights = dict(model["weights"])
        self.w1 = np.asarray(weights["w1"], dtype=np.float64)
        self.b1 = np.asarray(weights["b1"], dtype=np.float64)
        self.w2 = np.asarray(weights["w2"], dtype=np.float64)
        self.b2 = np.asarray(weights["b2"], dtype=np.float64)
        calibration = dict(model.get("calibration") or {})
        self.temperature = max(0.25, float(calibration.get("temperature") or 1.0))
        self.reject_threshold = max(0.0, min(1.0, float(calibration.get("reject_threshold") or 0.0)))

    def predict_detailed(
        self,
        payload: dict[str, Any],
        *,
        reject_below: float | None = None,
        temperature_override: float | None = None,
    ) -> dict[str, Any]:
        image = OpenVocabularyLineVectorizer.image(payload)
        features, ink_fraction = _temporal_features(
            image,
            height=self.feature_height,
            stride=self.stride,
            context_width=self.context_width,
        )
        if ink_fraction < 0.002:
            return {
                "text": "",
                "raw_text": "",
                "confidence": 0.0,
                "accepted": False,
                "rejection_reason": "insufficient_ink",
                "decoder": "ctc_prefix_beam_search",
                "alternatives": [],
            }
        hidden = np.tanh(features @ self.w1 + self.b1)
        temperature = max(0.25, float(temperature_override or self.temperature))
        probabilities = _softmax((hidden @ self.w2 + self.b2) / temperature)
        raw_text, confidence, alternatives = _ctc_prefix_beam_search(
            probabilities,
            self.vocabulary,
            self.blank_index,
            beam_width=self.beam_width,
        )
        threshold = self.reject_threshold if reject_below is None else max(0.0, min(1.0, float(reject_below)))
        accepted = bool(raw_text) and confidence >= threshold
        return {
            "text": raw_text if accepted else "",
            "raw_text": raw_text,
            "confidence": float(confidence),
            "accepted": accepted,
            "rejection_reason": None if accepted else "low_confidence",
            "decoder": "ctc_prefix_beam_search",
            "alternatives": [
                {"text": text, "log_probability": score}
                for text, score in alternatives
            ],
        }

    def predict_payload(self, payload: dict[str, Any]) -> tuple[str, float]:
        result = self.predict_detailed(payload)
        return str(result["text"]), float(result["confidence"])

    def predict_image(self, image_bytes: bytes) -> tuple[str, float]:
        payload = OpenVocabularyLineVectorizer().payload(image_bytes)
        return self.predict_payload(payload)

    def predict_image_object(self, image: Image.Image) -> tuple[str, float]:
        buffer = io.BytesIO()
        image.convert("L").save(buffer, format="PNG")
        return self.predict_image(buffer.getvalue())


class Stage14NeuralOCRCoordinator(Stage13OpenVocabularyCoordinator):
    """Governed Stage 14 CTC train -> robust shadow -> owner approval -> activation path."""

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
            provenance["stage14_sequence_ctc"] = True
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
            raise ValueError("Stage 14 supports OCR or handwriting neural CTC models")
        prepared = self._prepare_samples(task=task, subtask=subtask, languages=languages)
        vocabulary = UnicodeGraphemeTokenizer.vocabulary(str(row.get("label") or "") for row in prepared)
        if len(vocabulary) < 2:
            raise ValueError("Stage 14 requires at least two learned graphemes")
        return self.content_models.train(
            task,
            prepared,
            VishnuNeuralCTCTrainer(task=task),
            dataset_name=dataset_name or f"vishnu-{subtask}-stage14-neural-ctc",
            metadata={
                "stage": 14,
                "subtask": str(subtask),
                "languages": sorted({str(item) for item in (languages or ())}),
                "grapheme_vocabulary": list(vocabulary),
                "model_scope": "whole_line_temporal_sequence",
                "open_vocabulary": True,
                "lexicon_required": False,
                "neural_encoder": True,
                "foundation_model": False,
                "sequence_ctc_ready": True,
                "stage13_geometry_decoder_reused": False,
                "augmentation_profiles": list(_AUGMENTATION_PROFILES),
                "confidence_calibration": "heldout_sequence_brier_grid",
                "low_confidence_rejection": True,
                "capture_simulations": ["scan", "screenshot", "photo"],
                "real_world_corpus_qualified": False,
                "trained_by_vishnu": True,
                "continuous_feedback": True,
                "requires_shadow_qualification": True,
                "requires_owner_approval": True,
                "requires_release_controller": True,
            },
        )

    def _robustness_metrics(
        self,
        recognizer: VishnuNeuralOpenVocabularyRecognizer,
        rows: list[dict[str, Any]],
    ) -> dict[str, float]:
        truth: list[str] = []
        predicted: list[str] = []
        started = time.perf_counter()
        for row_index, row in enumerate(rows):
            source_image = OpenVocabularyLineVectorizer.image(dict(row.get("input") or {}))
            label = str(row.get("label") or "")
            row_seed = int(hashlib.sha256(f"robust:{row.get('id')}:{row_index}".encode()).hexdigest()[:16], 16)
            for profile_index, profile in enumerate(_AUGMENTATION_PROFILES):
                augmented = _apply_augmentation(source_image, profile, seed=row_seed + profile_index)
                buffer = io.BytesIO()
                augmented.save(buffer, format="PNG")
                payload = OpenVocabularyLineVectorizer().payload(buffer.getvalue())
                truth.append(label)
                predicted.append(recognizer.predict_payload(payload)[0])
        metrics = _text_metrics(truth, predicted, (time.perf_counter() - started) * 1000.0)
        metrics["profiles"] = float(len(_AUGMENTATION_PROFILES))
        metrics["records"] = float(len(truth))
        return metrics

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
        robust_metrics = self._robustness_metrics(candidate, rows)
        candidate_metrics["robust_cer"] = robust_metrics["cer"]
        candidate_metrics["robust_word_accuracy"] = robust_metrics["word_accuracy"]
        candidate_metrics["robust_char_accuracy"] = robust_metrics["char_accuracy"]
        candidate_metrics["robust_profiles"] = robust_metrics["profiles"]

        reasons = list(self.content_models.evaluator.evaluate_metrics(task, candidate_metrics).reasons)
        robust_evaluation = self.content_models.evaluator.evaluate_metrics(
            task,
            {
                "cer": robust_metrics["cer"],
                "word_accuracy": robust_metrics["word_accuracy"],
            },
        )
        reasons.extend(f"robustness:{reason}" for reason in robust_evaluation.reasons)
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
            "robustness_metrics": robust_metrics,
            "robustness_profiles": list(_AUGMENTATION_PROFILES),
            "capture_simulations": ["scan", "screenshot", "photo"],
            "real_world_corpus_qualified": False,
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
