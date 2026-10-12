from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from PIL import Image, ImageOps

from training.content_models import ContentDatasetSnapshot, ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import (
    GovernedContentFeedbackStore,
    ModelCycleEvidence,
    ModelCycleEvidenceStore,
    TesseractLineBaseline,
)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    file = Path(path)
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]


def _levenshtein(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, lvalue in enumerate(left, start=1):
        current = [i]
        for j, rvalue in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (lvalue != rvalue)))
        previous = current
    return previous[-1]


def _text_metrics(expected: list[str], predicted: list[str], elapsed_ms: float) -> dict[str, float]:
    if not expected:
        return {
            "cer": 1.0,
            "wer": 1.0,
            "word_accuracy": 0.0,
            "char_accuracy": 0.0,
            "records": 0.0,
            "avg_latency_ms": 0.0,
        }
    char_edits = char_total = word_edits = word_total = exact = 0
    for truth, guess in zip(expected, predicted):
        char_edits += _levenshtein(truth, guess)
        char_total += max(1, len(truth))
        truth_words, guess_words = truth.split(), guess.split()
        word_edits += _levenshtein(truth_words, guess_words)
        word_total += max(1, len(truth_words))
        exact += int(truth == guess)
    cer = min(1.0, char_edits / max(1, char_total))
    wer = min(1.0, word_edits / max(1, word_total))
    return {
        "cer": cer,
        "wer": wer,
        "word_accuracy": exact / len(expected),
        "char_accuracy": max(0.0, 1.0 - cer),
        "records": float(len(expected)),
        "avg_latency_ms": elapsed_ms / len(expected),
    }


class OpenVocabularyPolicyError(ValueError):
    pass


class UnicodeGraphemeTokenizer:
    """Small dependency-free grapheme tokenizer for governed OCR labels.

    It keeps combining marks, variation selectors and ZWJ sequences with their
    base code point. Whitespace is normalized to one ASCII space. The tokenizer
    is intentionally deterministic so dataset/model hashes are reproducible.
    """

    @staticmethod
    def tokenize(text: str) -> list[str]:
        normalized = unicodedata.normalize("NFC", str(text or ""))
        output: list[str] = []
        pending_zwj = False
        for char in normalized:
            if char.isspace():
                if output and output[-1] != " ":
                    output.append(" ")
                pending_zwj = False
                continue
            code = ord(char)
            combining = bool(unicodedata.combining(char))
            variation = 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF
            if char == "\u200d":
                if output and output[-1] != " ":
                    output[-1] += char
                    pending_zwj = True
                continue
            if (combining or variation or pending_zwj) and output and output[-1] != " ":
                output[-1] += char
                pending_zwj = False if pending_zwj and not combining and not variation else pending_zwj
            else:
                output.append(char)
                pending_zwj = False
        while output and output[-1] == " ":
            output.pop()
        return output

    @classmethod
    def vocabulary(cls, labels: Iterable[str]) -> tuple[str, ...]:
        values = {token for label in labels for token in cls.tokenize(label) if token != " "}
        return tuple(sorted(values))


class OpenVocabularyLineVectorizer:
    """Variable-width line normalizer preserving sequence geometry and spaces."""

    def __init__(self, *, height: int = 32, max_width: int = 1024):
        self.height = max(16, min(int(height), 96))
        self.max_width = max(96, min(int(max_width), 4096))

    def payload(self, image_bytes: bytes, *, kind: str = "open_vocabulary_line") -> dict[str, Any]:
        if not image_bytes:
            raise OpenVocabularyPolicyError("line image bytes are required")
        try:
            with Image.open(io.BytesIO(bytes(image_bytes))) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise OpenVocabularyPolicyError("line image is not readable") from exc
        image = ImageOps.autocontrast(image)
        inverse = ImageOps.invert(image)
        bbox = inverse.getbbox()
        if bbox is None:
            raise OpenVocabularyPolicyError("line image is blank")
        # Keep internal whitespace but remove empty outside margin.
        content = image.crop((bbox[0], 0, bbox[2], image.height))
        scale = self.height / max(1, content.height)
        width = max(1, int(round(content.width * scale)))
        if width > self.max_width:
            scale = self.max_width / max(1, content.width)
            height = max(8, int(round(content.height * scale)))
            content = content.resize((self.max_width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("L", (self.max_width, self.height), 255)
            canvas.paste(content, (0, (self.height - height) // 2))
        else:
            content = content.resize((width, self.height), Image.Resampling.LANCZOS)
            canvas = content
        flat = canvas.get_flattened_data() if hasattr(canvas, "get_flattened_data") else canvas.getdata()
        pixels = [int(value) for value in flat]
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=False)
        png = buffer.getvalue()
        return {
            "schema_version": 1,
            "kind": str(kind),
            "width": canvas.width,
            "height": canvas.height,
            "pixels": pixels,
            "image_png_b64": base64.b64encode(png).decode("ascii"),
            "normalized_sha256": hashlib.sha256(png).hexdigest(),
        }

    @staticmethod
    def image(payload: dict[str, Any]) -> Image.Image:
        encoded = str(payload.get("image_png_b64") or "")
        if encoded:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                return source.convert("L")
        width, height = int(payload.get("width") or 0), int(payload.get("height") or 0)
        pixels = payload.get("pixels") or []
        if width <= 0 or height <= 0 or len(pixels) != width * height:
            raise ValueError("invalid open-vocabulary line payload")
        image = Image.new("L", (width, height))
        image.putdata([int(value) for value in pixels])
        return image


def _ink_columns(image: Image.Image) -> list[float]:
    gray = image.convert("L")
    pixels = list(gray.getdata())
    values = []
    for x in range(gray.width):
        values.append(sum(1.0 - (pixels[y * gray.width + x] / 255.0) for y in range(gray.height)))
    return values


def _crop_ink(image: Image.Image) -> Image.Image:
    bbox = ImageOps.invert(image.convert("L")).getbbox()
    return image.crop(bbox) if bbox else image.copy()


def _resize_segment(image: Image.Image, width: int, height: int) -> list[float]:
    image = _crop_ink(image.convert("L"))
    if image.width <= 0 or image.height <= 0:
        return [0.0] * (width * height)
    max_w, max_h = max(1, width - 4), max(1, height - 4)
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (width, height), 255)
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    flat = canvas.get_flattened_data() if hasattr(canvas, "get_flattened_data") else canvas.getdata()
    return [round(1.0 - (float(value) / 255.0), 6) for value in flat]


def _best_boundaries(image: Image.Image, count: int) -> list[int]:
    if count <= 1:
        return [0, image.width]
    ink = _ink_columns(image)
    width = image.width
    result = [0]
    previous = 0
    for index in range(1, count):
        target = int(round(index * width / count))
        radius = max(2, int(round(width / max(4, count * 2))))
        low = max(previous + 1, target - radius)
        high = min(width - (count - index), target + radius)
        if low > high:
            boundary = max(previous + 1, min(width - (count - index), target))
        else:
            boundary = min(range(low, high + 1), key=lambda x: (ink[x], abs(x - target)))
        result.append(boundary)
        previous = boundary
    result.append(width)
    return result


def _split_training_tokens(image: Image.Image, tokens: list[str]) -> list[tuple[str, Image.Image, int]]:
    non_space = [token for token in tokens if token != " "]
    if not non_space:
        return []
    # Find wide blank runs and use them as word separators when their count agrees.
    ink = _ink_columns(image)
    threshold = max(0.1, image.height * 0.01)
    blank_runs: list[tuple[int, int]] = []
    start = None
    for index, value in enumerate(ink):
        if value <= threshold and start is None:
            start = index
        elif value > threshold and start is not None:
            blank_runs.append((start, index))
            start = None
    if start is not None:
        blank_runs.append((start, image.width))
    expected_spaces = sum(token == " " for token in tokens)
    internal = [(a, b) for a, b in blank_runs if a > 0 and b < image.width and b - a >= max(3, image.height // 8)]
    internal.sort(key=lambda pair: pair[1] - pair[0], reverse=True)
    separators = sorted(internal[:expected_spaces], key=lambda pair: pair[0]) if expected_spaces else []

    token_words: list[list[str]] = [[]]
    for token in tokens:
        if token == " ":
            if token_words[-1]:
                token_words.append([])
        else:
            token_words[-1].append(token)
    token_words = [word for word in token_words if word]

    if len(separators) == max(0, len(token_words) - 1):
        word_regions = []
        left = 0
        for start, end in separators:
            word_regions.append((left, start))
            left = end
        word_regions.append((left, image.width))
    else:
        totals = [len(word) for word in token_words]
        denom = max(1, sum(totals))
        word_regions = []
        left = 0
        consumed = 0
        for i, size in enumerate(totals):
            consumed += size
            right = image.width if i == len(totals) - 1 else int(round(image.width * consumed / denom))
            word_regions.append((left, right))
            left = right

    output: list[tuple[str, Image.Image, int]] = []
    for word, (left, right) in zip(token_words, word_regions):
        region = _crop_ink(image.crop((left, 0, max(left + 1, right), image.height)))
        boundaries = _best_boundaries(region, len(word))
        for token, start, end in zip(word, boundaries, boundaries[1:]):
            segment = region.crop((start, 0, max(start + 1, end), region.height))
            output.append((token, segment, max(1, end - start)))
    return output


def _distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("prototype shape mismatch")
    return sum((a - b) ** 2 for a, b in zip(left, right)) / max(1, len(left))


class VishnuSegmentalSequenceTrainer:
    """Open-vocabulary Unicode line recognizer trained from governed line images.

    The model learns grapheme-level visual prototypes and width statistics, then
    composes arbitrary grapheme sequences at inference time. It does not store a
    word lexicon, so unseen words can be produced from known graphemes.
    """

    def __init__(
        self,
        *,
        task: ContentModelTask = ContentModelTask.OCR,
        backend_id: str | None = None,
        token_width: int = 24,
        token_height: int = 32,
    ):
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("segmental sequence trainer supports OCR or handwriting")
        self.task = task
        self.backend_id = backend_id or (
            "vishnu-open-vocabulary-segmental-ocr-v1"
            if task is ContentModelTask.OCR
            else "vishnu-open-vocabulary-segmental-handwriting-v1"
        )
        self.token_width = max(12, min(int(token_width), 48))
        self.token_height = max(16, min(int(token_height), 64))

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("segmental sequence trainer task mismatch")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("open-vocabulary train split is empty")
        vectors: dict[str, list[list[float]]] = defaultdict(list)
        widths: dict[str, list[int]] = defaultdict(list)
        languages: set[str] = set()
        scripts: set[str] = set()
        for row in rows:
            label = str(row.get("label") or "")
            tokens = UnicodeGraphemeTokenizer.tokenize(label)
            if not any(token != " " for token in tokens):
                raise ValueError("open-vocabulary sample requires a non-empty text label")
            payload = dict(row.get("input") or {})
            if payload.get("kind") not in {"open_vocabulary_line", "open_vocabulary_handwriting_line"}:
                raise ValueError("open-vocabulary trainer requires normalized variable-width line input")
            image = OpenVocabularyLineVectorizer.image(payload)
            for token, segment, raw_width in _split_training_tokens(image, tokens):
                vectors[token].append(_resize_segment(segment, self.token_width, self.token_height))
                widths[token].append(raw_width)
            provenance = dict(row.get("provenance") or {})
            languages.add(str(provenance.get("language") or "und"))
            scripts.update(str(item) for item in provenance.get("scripts", []) if str(item))
        if len(vectors) < 2:
            raise ValueError("open-vocabulary model requires at least two learned graphemes")
        prototypes: dict[str, list[float]] = {}
        token_widths: dict[str, float] = {}
        samples_per_token: dict[str, int] = {}
        for token in sorted(vectors):
            samples = vectors[token]
            prototypes[token] = [round(sum(values) / len(values), 8) for values in zip(*samples)]
            token_widths[token] = round(sum(widths[token]) / len(widths[token]), 4)
            samples_per_token[token] = len(samples)
        all_widths = [value for values in widths.values() for value in values]
        median_width = sorted(all_widths)[len(all_widths) // 2]
        model = {
            "schema_version": 1,
            "model_type": "vishnu-open-vocabulary-segmental-sequence",
            "model_scope": "open_vocabulary_line_sequence",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "open_vocabulary": True,
            "lexicon_required": False,
            "page_segmentation_supported": True,
            "tokenizer": "vishnu-unicode-grapheme-v1",
            "token_width": self.token_width,
            "token_height": self.token_height,
            "median_source_token_width": float(median_width),
            "vocabulary": sorted(prototypes),
            "samples_per_token": samples_per_token,
            "mean_source_widths": token_widths,
            "prototypes": prototypes,
            "languages": sorted(languages),
            "scripts": sorted(scripts),
            "trained_by_vishnu": True,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        recognizer = VishnuOpenVocabularyRecognizer.from_model(model)
        eval_rows = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        truth: list[str] = []
        predictions: list[str] = []
        started = time.perf_counter()
        for row in eval_rows:
            truth.append(str(row.get("label") or ""))
            predictions.append(recognizer.predict_payload(dict(row.get("input") or {}))[0])
        metrics = _text_metrics(truth, predictions, (time.perf_counter() - started) * 1000.0)
        metrics["grapheme_vocabulary"] = float(len(prototypes))
        metrics["open_vocabulary"] = 1.0
        return output_dir, metrics


class VishnuOpenVocabularyRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        self._load(model)

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "VishnuOpenVocabularyRecognizer":
        instance = cls.__new__(cls)
        instance._load(model)
        return instance

    def _load(self, model: dict[str, Any]) -> None:
        if model.get("model_type") != "vishnu-open-vocabulary-segmental-sequence":
            raise ValueError("unsupported open-vocabulary Vishnu OCR artifact")
        self.model = model
        self.prototypes = {str(key): [float(v) for v in value] for key, value in model["prototypes"].items()}
        self.token_width = int(model["token_width"])
        self.token_height = int(model["token_height"])
        self.median_width = max(2.0, float(model.get("median_source_token_width") or 8.0))
        self.mean_widths = {str(k): float(v) for k, v in (model.get("mean_source_widths") or {}).items()}

    def _classify(self, segment: Image.Image) -> tuple[str, float]:
        vector = _resize_segment(segment, self.token_width, self.token_height)
        scores = sorted((_distance(vector, prototype), token) for token, prototype in self.prototypes.items())
        best_distance, token = scores[0]
        if len(scores) == 1:
            confidence = max(0.0, min(1.0, 1.0 - best_distance))
        else:
            second = scores[1][0]
            confidence = max(0.0, min(1.0, (second - best_distance) / max(second, 1e-9)))
        return token, confidence

    def _word_regions(self, image: Image.Image) -> list[Image.Image]:
        image = _crop_ink(image)
        if image.width <= 0:
            return []
        ink = _ink_columns(image)
        threshold = max(0.1, image.height * 0.0125)
        blank_runs: list[tuple[int, int]] = []
        start = None
        for index, value in enumerate(ink):
            if value <= threshold and start is None:
                start = index
            elif value > threshold and start is not None:
                blank_runs.append((start, index))
                start = None
        if start is not None:
            blank_runs.append((start, image.width))
        min_gap = max(3, int(round(self.median_width * 0.65)))
        gaps = [(a, b) for a, b in blank_runs if a > 0 and b < image.width and b - a >= min_gap]
        if not gaps:
            return [image]
        regions: list[Image.Image] = []
        left = 0
        for start, end in gaps:
            if start > left:
                region = _crop_ink(image.crop((left, 0, start, image.height)))
                if region.width > 0:
                    regions.append(region)
            left = end
        if left < image.width:
            region = _crop_ink(image.crop((left, 0, image.width, image.height)))
            if region.width > 0:
                regions.append(region)
        return regions

    def _decode_word(self, image: Image.Image) -> tuple[str, float]:
        image = _crop_ink(image)
        estimated = max(1, int(round(image.width / self.median_width)))
        max_tokens = max(1, min(256, len(self.prototypes) * 4, image.width))
        candidate_counts = sorted({max(1, min(max_tokens, estimated + delta)) for delta in (-2, -1, 0, 1, 2)})
        best: tuple[float, str, float] | None = None
        for count in candidate_counts:
            boundaries = _best_boundaries(image, count)
            tokens: list[str] = []
            confidences: list[float] = []
            cost = 0.0
            for start, end in zip(boundaries, boundaries[1:]):
                segment = image.crop((start, 0, max(start + 1, end), image.height))
                token, confidence = self._classify(segment)
                tokens.append(token)
                confidences.append(confidence)
                expected_width = max(1.0, self.mean_widths.get(token, self.median_width))
                width_penalty = abs((end - start) - expected_width) / expected_width
                cost += (1.0 - confidence) + 0.12 * width_penalty
            normalized_cost = cost / max(1, count)
            text = "".join(tokens)
            confidence = sum(confidences) / max(1, len(confidences))
            if best is None or normalized_cost < best[0]:
                best = (normalized_cost, text, confidence)
        if best is None:
            return "", 0.0
        return best[1], best[2]

    def predict_payload(self, payload: dict[str, Any]) -> tuple[str, float]:
        image = OpenVocabularyLineVectorizer.image(payload)
        return self.predict_image_object(image)

    def predict_image(self, image_bytes: bytes) -> tuple[str, float]:
        payload = OpenVocabularyLineVectorizer(height=self.token_height).payload(image_bytes)
        return self.predict_payload(payload)

    def predict_image_object(self, image: Image.Image) -> tuple[str, float]:
        words = self._word_regions(image.convert("L"))
        if not words:
            return "", 0.0
        decoded = [self._decode_word(word) for word in words]
        return " ".join(text for text, _ in decoded), sum(conf for _, conf in decoded) / len(decoded)


@dataclass(frozen=True)
class PageLineResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]

    def public(self) -> dict[str, Any]:
        return {"text": self.text, "confidence": self.confidence, "bbox": list(self.bbox)}


class VishnuPageSequenceRecognizer:
    """Deterministic page-to-lines segmentation over a qualified line model."""

    def __init__(self, line_model: VishnuOpenVocabularyRecognizer):
        self.line_model = line_model

    @staticmethod
    def _line_boxes(page: Image.Image) -> list[tuple[int, int, int, int]]:
        gray = page.convert("L")
        pixels = list(gray.getdata())
        row_ink = []
        for y in range(gray.height):
            row_ink.append(sum(1.0 - pixels[y * gray.width + x] / 255.0 for x in range(gray.width)))
        threshold = max(0.5, gray.width * 0.002)
        runs: list[tuple[int, int]] = []
        start = None
        for y, value in enumerate(row_ink):
            if value > threshold and start is None:
                start = y
            elif value <= threshold and start is not None:
                runs.append((start, y))
                start = None
        if start is not None:
            runs.append((start, gray.height))
        merged: list[tuple[int, int]] = []
        for start, end in runs:
            if merged and start - merged[-1][1] <= 2:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        boxes = []
        for top, bottom in merged:
            band = gray.crop((0, top, gray.width, bottom))
            bbox = ImageOps.invert(band).getbbox()
            if bbox:
                boxes.append((bbox[0], top, bbox[2], bottom))
        return boxes

    def recognize(self, page_bytes: bytes) -> dict[str, Any]:
        try:
            with Image.open(io.BytesIO(page_bytes)) as source:
                source.load()
                page = ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise OpenVocabularyPolicyError("page image is not readable") from exc
        lines: list[PageLineResult] = []
        for box in self._line_boxes(page):
            crop = page.crop(box)
            payload_buffer = io.BytesIO()
            crop.save(payload_buffer, format="PNG")
            text, confidence = self.line_model.predict_image(payload_buffer.getvalue())
            if text:
                lines.append(PageLineResult(text=text, confidence=confidence, bbox=box))
        return {
            "text": "\n".join(line.text for line in lines),
            "lines": [line.public() for line in lines],
            "line_count": len(lines),
            "model_scope": "page_segmentation_plus_open_vocabulary_line_sequence",
        }


class LineTextBaseline(Protocol):
    baseline_id: str

    def predict(self, image_bytes: bytes) -> str: ...


class Stage13OpenVocabularyCoordinator:
    """Governed Stage 13 train -> shadow -> owner approval -> activation path."""

    def __init__(
        self,
        *,
        content_models: ContentModelCoordinator,
        feedback: GovernedContentFeedbackStore,
        evidence_path: str | Path,
        vectorizer: OpenVocabularyLineVectorizer | None = None,
    ):
        self.content_models = content_models
        self.feedback = feedback
        self.evidence = ModelCycleEvidenceStore(evidence_path)
        self.vectorizer = vectorizer or OpenVocabularyLineVectorizer()

    def _prepare_samples(
        self,
        *,
        task: ContentModelTask,
        subtask: str,
        languages: Iterable[str] | None,
    ) -> list[dict[str, Any]]:
        rows = self.feedback.approved_samples(task, subtask=subtask, languages=languages)
        prepared = []
        kind = "open_vocabulary_line" if task is ContentModelTask.OCR else "open_vocabulary_handwriting_line"
        for row in rows:
            original = row.get("input")
            if not isinstance(original, dict):
                raise OpenVocabularyPolicyError("Stage 13 feedback input must contain an image payload")
            encoded = str(original.get("image_png_b64") or "")
            if not encoded:
                raise OpenVocabularyPolicyError("Stage 13 feedback requires image_png_b64")
            image_bytes = base64.b64decode(encoded, validate=True)
            payload = self.vectorizer.payload(image_bytes, kind=kind)
            provenance = dict(row.get("provenance") or {})
            language = str(provenance.get("language") or "und")
            tokens = UnicodeGraphemeTokenizer.tokenize(str(row.get("label") or ""))
            scripts = sorted(
                {
                    unicodedata.name(token[0], "UNKNOWN").split(" ")[0]
                    for token in tokens
                    if token != " " and token
                }
            )
            prepared.append(
                {
                    **row,
                    "input": payload,
                    "provenance": {
                        **provenance,
                        "language": language,
                        "scripts": scripts,
                        "stage13_open_vocabulary": True,
                    },
                }
            )
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
            raise ValueError("Stage 13 supports OCR or handwriting sequence models")
        prepared = self._prepare_samples(task=task, subtask=subtask, languages=languages)
        vocabulary = UnicodeGraphemeTokenizer.vocabulary(str(row.get("label") or "") for row in prepared)
        if len(vocabulary) < 2:
            raise ValueError("Stage 13 requires at least two learned graphemes")
        return self.content_models.train(
            task,
            prepared,
            VishnuSegmentalSequenceTrainer(task=task),
            dataset_name=dataset_name or f"vishnu-{subtask}-stage13-open-vocabulary",
            metadata={
                "stage": 13,
                "subtask": str(subtask),
                "languages": sorted({str(item) for item in (languages or ())}),
                "grapheme_vocabulary": list(vocabulary),
                "model_scope": "open_vocabulary_line_sequence",
                "open_vocabulary": True,
                "lexicon_required": False,
                "page_segmentation_supported": True,
                "trained_by_vishnu": True,
                "continuous_feedback": True,
                "requires_shadow_qualification": True,
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
        baseline: LineTextBaseline | None = None,
        max_cer_regression: float = 0.0,
        min_char_accuracy_delta: float = 0.0,
    ) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        task = ContentModelTask(str(model["task"]))
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING} or model["status"] != "candidate":
            raise ValueError("Stage 13 shadow qualification requires an OCR/handwriting candidate")
        rows = _read_jsonl(self._snapshot_for(model).test_path) or _read_jsonl(self._snapshot_for(model).validation_path)
        if not rows:
            raise ValueError("Stage 13 shadow qualification requires a held-out split")
        candidate = VishnuOpenVocabularyRecognizer(model["checkpoint_ref"])
        truth: list[str] = []
        candidate_predictions: list[str] = []
        baseline_predictions: list[str] = []
        candidate_start = time.perf_counter()
        for row in rows:
            truth.append(str(row.get("label") or ""))
            candidate_predictions.append(candidate.predict_payload(dict(row.get("input") or {}))[0])
        candidate_ms = (time.perf_counter() - candidate_start) * 1000.0
        baseline = baseline or TesseractLineBaseline()
        baseline_error = None
        baseline_start = time.perf_counter()
        try:
            for row in rows:
                encoded = str(dict(row.get("input") or {}).get("image_png_b64") or "")
                baseline_predictions.append(str(baseline.predict(base64.b64decode(encoded, validate=True)) or ""))
        except Exception as exc:
            baseline_error = f"baseline_unavailable:{exc.__class__.__name__}"
        baseline_ms = (time.perf_counter() - baseline_start) * 1000.0
        candidate_metrics = _text_metrics(truth, candidate_predictions, candidate_ms)
        if baseline_error is None and len(baseline_predictions) == len(truth):
            baseline_metrics = _text_metrics(truth, baseline_predictions, baseline_ms)
        else:
            baseline_metrics = _text_metrics(truth, [""] * len(truth), baseline_ms)
        reasons = list(self.content_models.evaluator.evaluate_metrics(task, candidate_metrics).reasons)
        if baseline_error:
            reasons.append(baseline_error)
        if candidate_metrics["cer"] > baseline_metrics["cer"] + float(max_cer_regression):
            reasons.append("candidate_cer_worse_than_baseline")
        char_delta = candidate_metrics["char_accuracy"] - baseline_metrics["char_accuracy"]
        if char_delta < float(min_char_accuracy_delta):
            reasons.append("candidate_char_accuracy_delta_below_requirement")
        created_at = _now()
        payload = {
            "model_id": model_id,
            "task": task.value,
            "baseline_id": str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            "records": len(rows),
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": {
                "cer": candidate_metrics["cer"] - baseline_metrics["cer"],
                "char_accuracy": char_delta,
                "avg_latency_ms": candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
            },
            "passed": not reasons,
            "reasons": reasons,
            "created_at": created_at,
        }
        evidence = ModelCycleEvidence(
            model_id=model_id,
            task=task.value,
            baseline_id=payload["baseline_id"],
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas=payload["deltas"],
            passed=not reasons,
            reasons=tuple(reasons),
            evidence_sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
        return self.evidence.record(evidence)

    def approve(self, model_id: str, *, owner_id: str) -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 13 model requires successful shadow qualification before owner approval")
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(self, model_id: str, *, owner_authorized: bool, actor: str = "release_controller") -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 13 model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(model_id, owner_authorized=owner_authorized, actor=actor)
