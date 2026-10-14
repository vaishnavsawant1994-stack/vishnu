from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from PIL import Image, ImageOps

from file_intelligence.ocr import OcrUnavailable, TesseractOcrProvider
from training.content_models import ContentDatasetSnapshot, ContentModelCoordinator, ContentModelTask


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    file = Path(path)
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]


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
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (lch != rch)))
        previous = current
    return previous[-1]


def _text_metrics(expected: list[str], predicted: list[str], elapsed_ms: float) -> dict[str, float]:
    if not expected:
        return {"cer": 1.0, "wer": 1.0, "word_accuracy": 0.0, "char_accuracy": 0.0, "records": 0.0, "avg_latency_ms": 0.0}
    char_edits = 0
    char_total = 0
    word_edits = 0
    word_total = 0
    exact = 0
    for truth, guess in zip(expected, predicted):
        char_edits += _levenshtein(truth, guess)
        char_total += max(1, len(truth))
        truth_words = truth.split()
        guess_words = guess.split()
        word_edits += _levenshtein("\u0000".join(truth_words), "\u0000".join(guess_words)) if len(truth_words) <= 1 and len(guess_words) <= 1 else _token_levenshtein(truth_words, guess_words)
        word_total += max(1, len(truth_words))
        exact += int(truth == guess)
    cer = min(1.0, char_edits / max(1, char_total))
    wer = min(1.0, word_edits / max(1, word_total))
    accuracy = exact / len(expected)
    return {
        "cer": cer,
        "wer": wer,
        "word_accuracy": accuracy,
        "char_accuracy": max(0.0, 1.0 - cer),
        "records": float(len(expected)),
        "avg_latency_ms": elapsed_ms / len(expected),
    }


def _token_levenshtein(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, ltok in enumerate(left, start=1):
        current = [i]
        for j, rtok in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ltok != rtok)))
        previous = current
    return previous[-1]


def _macro_f1(expected: list[str], predicted: list[str]) -> float:
    labels = sorted(set(expected) | set(predicted))
    if not labels:
        return 0.0
    values = []
    for label in labels:
        tp = sum(1 for truth, guess in zip(expected, predicted) if truth == label and guess == label)
        fp = sum(1 for truth, guess in zip(expected, predicted) if truth != label and guess == label)
        fn = sum(1 for truth, guess in zip(expected, predicted) if truth == label and guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        values.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(values) / len(values)


class FeedbackPolicyError(ValueError):
    pass


class GovernedContentFeedbackStore:
    """Durable quarantine -> review -> approved training feedback store.

    Feedback never becomes training data merely because it was captured. Every
    sample needs an approved consent basis, provenance and an explicit reviewer.
    """

    ALLOWED_CONSENT = {"owner_provided", "licensed", "public_domain", "synthetic"}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_model_feedback(
                    feedback_id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    subtask TEXT NOT NULL,
                    language TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    sample_sha256 TEXT NOT NULL UNIQUE,
                    input_json TEXT NOT NULL,
                    label_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    consent_basis TEXT NOT NULL,
                    correction_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    rejection_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_content_feedback_training
                    ON content_model_feedback(task,subtask,status,language,created_at);
                """
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def submit(
        self,
        *,
        task: ContentModelTask | str,
        subtask: str,
        language: str,
        source_fingerprint: str,
        input_payload: Any,
        label: Any,
        provenance: dict[str, Any],
        consent_basis: str,
        correction_kind: str = "human_correction",
    ) -> dict[str, Any]:
        task = ContentModelTask(str(task))
        subtask = str(subtask or "").strip()
        language = str(language or "und").strip() or "und"
        source = str(source_fingerprint or "").strip()
        consent = str(consent_basis or "").strip()
        if not subtask:
            raise FeedbackPolicyError("feedback subtask is required")
        if not source:
            raise FeedbackPolicyError("feedback source_fingerprint is required")
        if consent not in self.ALLOWED_CONSENT:
            raise FeedbackPolicyError("feedback requires an approved explicit consent_basis")
        provenance = dict(provenance or {})
        if not str(provenance.get("license") or provenance.get("ownership_basis") or "").strip():
            raise FeedbackPolicyError("feedback provenance requires a license or ownership basis")
        if input_payload in (None, "") or label in (None, ""):
            raise FeedbackPolicyError("feedback requires input and label")
        payload = {
            "task": task.value,
            "subtask": subtask,
            "language": language,
            "source_fingerprint": source,
            "input": input_payload,
            "label": label,
            "provenance": provenance,
            "consent_basis": consent,
        }
        sample_sha = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        feedback_id = f"feedback-{sample_sha[:24]}"
        with self._con() as con:
            con.execute(
                """INSERT OR IGNORE INTO content_model_feedback
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    feedback_id,
                    task.value,
                    subtask,
                    language,
                    source,
                    sample_sha,
                    _canonical(input_payload),
                    _canonical(label),
                    _canonical(provenance),
                    consent,
                    str(correction_kind or "human_correction"),
                    "pending",
                    _now(),
                    None,
                    None,
                    None,
                ),
            )
        return self.get(feedback_id)

    def get(self, feedback_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM content_model_feedback WHERE feedback_id=?", (feedback_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json"))
        item["label"] = json.loads(item.pop("label_json"))
        item["provenance"] = json.loads(item.pop("provenance_json"))
        return item

    def approve(self, feedback_id: str, *, reviewer: str) -> dict[str, Any]:
        reviewer = str(reviewer or "").strip()
        if not reviewer:
            raise FeedbackPolicyError("feedback approval requires reviewer identity")
        current = self.get(feedback_id)
        if not current:
            raise KeyError(feedback_id)
        if current["status"] not in {"pending", "approved"}:
            raise FeedbackPolicyError("rejected feedback cannot be approved without resubmission")
        with self._con() as con:
            con.execute(
                "UPDATE content_model_feedback SET status='approved',reviewed_at=?,reviewed_by=?,rejection_reason=NULL WHERE feedback_id=?",
                (_now(), reviewer, feedback_id),
            )
        return self.get(feedback_id)

    def reject(self, feedback_id: str, *, reviewer: str, reason: str) -> dict[str, Any]:
        reviewer = str(reviewer or "").strip()
        reason = str(reason or "").strip()
        if not reviewer or not reason:
            raise FeedbackPolicyError("feedback rejection requires reviewer and reason")
        if not self.get(feedback_id):
            raise KeyError(feedback_id)
        with self._con() as con:
            con.execute(
                "UPDATE content_model_feedback SET status='rejected',reviewed_at=?,reviewed_by=?,rejection_reason=? WHERE feedback_id=?",
                (_now(), reviewer, reason, feedback_id),
            )
        return self.get(feedback_id)

    def approved_samples(
        self,
        task: ContentModelTask | str,
        *,
        subtask: str | None = None,
        languages: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        task = ContentModelTask(str(task))
        params: list[Any] = [task.value]
        where = ["task=?", "status='approved'"]
        if subtask:
            where.append("subtask=?")
            params.append(str(subtask))
        selected_languages = tuple(sorted({str(item).strip() for item in (languages or ()) if str(item).strip()}))
        if selected_languages:
            where.append(f"language IN ({','.join('?' for _ in selected_languages)})")
            params.extend(selected_languages)
        with self._con() as con:
            rows = con.execute(
                "SELECT feedback_id FROM content_model_feedback WHERE " + " AND ".join(where) + " ORDER BY created_at,feedback_id",
                tuple(params),
            ).fetchall()
        samples = []
        for row in rows:
            item = self.get(row["feedback_id"])
            if not item:
                continue
            samples.append(
                {
                    "id": item["feedback_id"],
                    "input": item["input"],
                    "label": item["label"],
                    "source_fingerprint": item["source_fingerprint"],
                    "consent_basis": item["consent_basis"],
                    "provenance": {
                        **item["provenance"],
                        "feedback_id": item["feedback_id"],
                        "approved_for_training": True,
                        "reviewed_by": item["reviewed_by"],
                        "language": item["language"],
                        "subtask": item["subtask"],
                    },
                }
            )
        return samples

    def stats(self) -> dict[str, int]:
        with self._con() as con:
            rows = con.execute("SELECT status,COUNT(*) AS n FROM content_model_feedback GROUP BY status").fetchall()
        result = {"pending": 0, "approved": 0, "rejected": 0}
        result.update({str(row["status"]): int(row["n"]) for row in rows})
        return result


class SequenceRasterVectorizer:
    """Deterministic word/line raster vectorizer for narrow Stage 12 recognizers."""

    def __init__(self, width: int = 96, height: int = 24):
        self.width = max(24, min(int(width), 256))
        self.height = max(12, min(int(height), 64))

    def payload(self, image_bytes: bytes, *, kind: str = "word_line_raster") -> dict[str, Any]:
        try:
            with Image.open(io.BytesIO(bytes(image_bytes))) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise FeedbackPolicyError("feedback image is not readable") from exc
        image = ImageOps.autocontrast(image)
        inverted = ImageOps.invert(image)
        bbox = inverted.getbbox()
        if bbox is None:
            raise FeedbackPolicyError("feedback image is blank")
        content = image.crop(bbox)
        max_w, max_h = max(1, self.width - 4), max(1, self.height - 4)
        content.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        canvas = Image.new("L", (self.width, self.height), 255)
        canvas.paste(content, ((self.width - content.width) // 2, (self.height - content.height) // 2))
        flattened = canvas.get_flattened_data() if hasattr(canvas, "get_flattened_data") else canvas.getdata()
        features = [round(1.0 - (float(value) / 255.0), 6) for value in flattened]
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=False)
        normalized = buffer.getvalue()
        return {
            "schema_version": 1,
            "kind": str(kind),
            "width": self.width,
            "height": self.height,
            "features": features,
            "image_png_b64": base64.b64encode(normalized).decode("ascii"),
            "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        }


class VishnuSequencePrototypeTrainer:
    """Real local learned prototype recognizer for bounded word/line vocabularies.

    It supports Unicode labels, including multilingual and handwriting datasets,
    but it is deliberately not described as an open-vocabulary production OCR
    model. The artifact records this limitation.
    """

    def __init__(self, *, task: ContentModelTask, model_scope: str, backend_id: str):
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("sequence trainer supports OCR or handwriting only")
        self.task = task
        self.model_scope = str(model_scope)
        self.backend_id = str(backend_id)

    @staticmethod
    def _vector(row: dict[str, Any]) -> list[float]:
        payload = row.get("input") or {}
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features:
            raise ValueError("sequence row has no raster features")
        return [float(item) for item in features]

    @staticmethod
    def _predict(model: dict[str, Any], vector: list[float]) -> tuple[str, float]:
        best: tuple[float, str] | None = None
        second: float | None = None
        for label, prototype in (model.get("prototypes") or {}).items():
            weights = [float(item) for item in prototype]
            if len(weights) != len(vector):
                raise ValueError("sequence vector shape mismatch")
            distance = sum((a - b) ** 2 for a, b in zip(vector, weights)) / len(vector)
            if best is None or distance < best[0]:
                second = best[0] if best else second
                best = (distance, str(label))
            elif second is None or distance < second:
                second = distance
        if best is None:
            raise RuntimeError("sequence model has no prototypes")
        confidence = max(0.0, min(1.0, 1.0 - best[0])) if second is None else max(0.0, min(1.0, (second - best[0]) / max(second, 1e-9)))
        return best[1], confidence

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("sequence trainer task mismatch")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("sequence training split is empty")
        sums: dict[str, list[float]] = {}
        counts: Counter[str] = Counter()
        width = height = 0
        for row in rows:
            payload = row.get("input") or {}
            if not isinstance(payload, dict) or payload.get("kind") not in {"word_line_raster", "handwriting_line_raster"}:
                raise ValueError("sequence trainer requires normalized raster input")
            vector = self._vector(row)
            label = str(row.get("label") or "")
            if not label:
                raise ValueError("sequence trainer requires text labels")
            width, height = int(payload.get("width") or 0), int(payload.get("height") or 0)
            if width * height != len(vector):
                raise ValueError("sequence raster dimensions do not match vector")
            if label not in sums:
                sums[label] = [0.0] * len(vector)
            if len(sums[label]) != len(vector):
                raise ValueError("sequence vectors must share one shape")
            sums[label] = [left + right for left, right in zip(sums[label], vector)]
            counts[label] += 1
        if len(sums) < 2:
            raise ValueError("sequence model requires at least two distinct labels")
        prototypes = {label: [round(value / counts[label], 8) for value in vector] for label, vector in sorted(sums.items())}
        model = {
            "schema_version": 1,
            "model_type": "vishnu-sequence-raster-prototype",
            "model_scope": self.model_scope,
            "open_vocabulary": False,
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "feature_width": width,
            "feature_height": height,
            "labels": sorted(prototypes),
            "samples_per_label": dict(counts),
            "prototypes": prototypes,
            "created_at": _now(),
            "trained_by_vishnu": True,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        evaluation = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        expected, predicted = [], []
        started = time.perf_counter()
        for row in evaluation:
            expected.append(str(row["label"]))
            predicted.append(self._predict(model, self._vector(row))[0])
        metrics = _text_metrics(expected, predicted, (time.perf_counter() - started) * 1000.0)
        return output_dir, metrics


class VishnuSequenceRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        self.model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-sequence-raster-prototype":
            raise ValueError("unsupported Vishnu sequence model")

    def predict_payload(self, payload: dict[str, Any]) -> tuple[str, float]:
        vector = [float(item) for item in payload.get("features") or []]
        return VishnuSequencePrototypeTrainer._predict(self.model, vector)


class VishnuCentroidFeatureTrainer:
    """Simple learned centroid classifier for layout/table normalized features."""

    def __init__(self, *, task: ContentModelTask, backend_id: str, metric_name: str):
        if task not in {ContentModelTask.LAYOUT, ContentModelTask.TABLE}:
            raise ValueError("centroid feature trainer supports layout/table only")
        self.task = task
        self.backend_id = str(backend_id)
        self.metric_name = str(metric_name)

    @staticmethod
    def _vector(row: dict[str, Any]) -> list[float]:
        payload = row.get("input") or {}
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features:
            raise ValueError("feature row requires numeric features")
        return [float(item) for item in features]

    @staticmethod
    def _predict(model: dict[str, Any], vector: list[float]) -> str:
        best: tuple[float, str] | None = None
        for label, centroid in (model.get("centroids") or {}).items():
            weights = [float(item) for item in centroid]
            if len(weights) != len(vector):
                raise ValueError("feature vector shape mismatch")
            distance = sum((a - b) ** 2 for a, b in zip(vector, weights)) / len(vector)
            if best is None or distance < best[0]:
                best = (distance, str(label))
        if best is None:
            raise RuntimeError("feature model has no centroids")
        return best[1]

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("feature trainer task mismatch")
        rows = _read_jsonl(snapshot.train_path)
        sums: dict[str, list[float]] = {}
        counts: Counter[str] = Counter()
        for row in rows:
            vector = self._vector(row)
            label = str(row.get("label") or "")
            if label not in sums:
                sums[label] = [0.0] * len(vector)
            if len(sums[label]) != len(vector):
                raise ValueError("feature vectors must share one shape")
            sums[label] = [a + b for a, b in zip(sums[label], vector)]
            counts[label] += 1
        if len(sums) < 2:
            raise ValueError("feature model requires at least two labels")
        centroids = {label: [round(value / counts[label], 8) for value in vector] for label, vector in sorted(sums.items())}
        model = {
            "schema_version": 1,
            "model_type": "vishnu-centroid-feature-classifier",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "centroids": centroids,
            "labels": sorted(centroids),
            "trained_by_vishnu": True,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(json.dumps(model, sort_keys=True), encoding="utf-8")
        evaluation = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        expected = [str(row["label"]) for row in evaluation]
        predicted = [self._predict(model, self._vector(row)) for row in evaluation]
        f1 = _macro_f1(expected, predicted)
        return output_dir, {self.metric_name: f1, "accuracy": sum(int(a == b) for a, b in zip(expected, predicted)) / len(expected), "evaluation_records": float(len(expected))}


class VishnuFeatureClassifier:
    def __init__(self, checkpoint_ref: str | Path):
        self.model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-centroid-feature-classifier":
            raise ValueError("unsupported Vishnu feature model")

    def predict_payload(self, payload: dict[str, Any]) -> str:
        vector = [float(item) for item in payload.get("features") or []]
        return VishnuCentroidFeatureTrainer._predict(self.model, vector)


class TextBaseline(Protocol):
    baseline_id: str
    def predict(self, image_bytes: bytes) -> str: ...


class FeatureBaseline(Protocol):
    baseline_id: str
    def predict(self, payload: dict[str, Any]) -> str: ...


class TesseractLineBaseline:
    baseline_id = "tesseract-local-line"

    def __init__(self, provider: TesseractOcrProvider | None = None):
        self.provider = provider or TesseractOcrProvider(language="auto", orientation=False, psm=7)

    def predict(self, image_bytes: bytes) -> str:
        blocks = self.provider.extract(image_bytes, filename="shadow-line.png", access_class="owner")
        return " ".join(str(item.get("text") or "").strip() for item in blocks if str(item.get("text") or "").strip()).strip()


@dataclass(frozen=True)
class ModelCycleEvidence:
    model_id: str
    task: str
    baseline_id: str
    records: int
    candidate_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    deltas: dict[str, float]
    passed: bool
    reasons: tuple[str, ...]
    evidence_sha256: str
    created_at: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


class ModelCycleEvidenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_model_cycle_evidence(
                    evidence_sha256 TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_content_model_cycle_model
                    ON content_model_cycle_evidence(model_id,created_at);
                """
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def record(self, evidence: ModelCycleEvidence) -> dict[str, Any]:
        payload = evidence.public()
        with self._con() as con:
            con.execute(
                "INSERT OR IGNORE INTO content_model_cycle_evidence VALUES(?,?,?,?,?,?)",
                (evidence.evidence_sha256, evidence.model_id, evidence.task, int(evidence.passed), evidence.created_at, _canonical(payload)),
            )
        return payload

    def latest(self, model_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                "SELECT evidence_json FROM content_model_cycle_evidence WHERE model_id=? ORDER BY created_at DESC,evidence_sha256 DESC LIMIT 1",
                (model_id,),
            ).fetchone()
        return json.loads(row["evidence_json"]) if row else None


class ContinuousContentModelCoordinator:
    """Stage 12 feedback -> train -> benchmark -> shadow -> owner-gated promotion."""

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

    def train_sequence_candidate(
        self,
        *,
        task: ContentModelTask,
        subtask: str,
        languages: Iterable[str] | None = None,
        dataset_name: str | None = None,
    ) -> dict[str, Any]:
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING}:
            raise ValueError("sequence candidate requires OCR or handwriting task")
        samples = self.feedback.approved_samples(task, subtask=subtask, languages=languages)
        backend_id = "vishnu-word-line-prototype-v1" if task is ContentModelTask.OCR else "vishnu-handwriting-line-prototype-v1"
        scope = "closed_vocabulary_word_line" if task is ContentModelTask.OCR else "closed_vocabulary_handwriting_line"
        return self.content_models.train(
            task,
            samples,
            VishnuSequencePrototypeTrainer(task=task, model_scope=scope, backend_id=backend_id),
            dataset_name=dataset_name or f"vishnu-{subtask}-stage12",
            metadata={
                "stage": 12,
                "subtask": str(subtask),
                "languages": sorted({str(item) for item in (languages or ())}),
                "model_scope": scope,
                "open_vocabulary": False,
                "trained_by_vishnu": True,
                "continuous_feedback": True,
                "requires_shadow_qualification": True,
            },
        )

    def train_feature_candidate(
        self,
        *,
        task: ContentModelTask,
        subtask: str,
        dataset_name: str | None = None,
    ) -> dict[str, Any]:
        if task not in {ContentModelTask.LAYOUT, ContentModelTask.TABLE}:
            raise ValueError("feature candidate requires layout or table task")
        metric = "f1" if task is ContentModelTask.LAYOUT else "cell_f1"
        samples = self.feedback.approved_samples(task, subtask=subtask)
        return self.content_models.train(
            task,
            samples,
            VishnuCentroidFeatureTrainer(task=task, backend_id=f"vishnu-{task.value}-centroid-v1", metric_name=metric),
            dataset_name=dataset_name or f"vishnu-{subtask}-stage12",
            metadata={
                "stage": 12,
                "subtask": str(subtask),
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

    def shadow_sequence(
        self,
        model_id: str,
        *,
        baseline: TextBaseline | None = None,
        max_cer_regression: float = 0.0,
        min_accuracy_delta: float = 0.0,
    ) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        task = ContentModelTask(str(model["task"]))
        if task not in {ContentModelTask.OCR, ContentModelTask.HANDWRITING} or model["status"] != "candidate":
            raise ValueError("sequence shadow qualification requires an OCR/handwriting candidate")
        rows = _read_jsonl(self._snapshot_for(model).test_path) or _read_jsonl(self._snapshot_for(model).validation_path)
        if not rows:
            raise ValueError("shadow qualification requires a held-out split")
        recognizer = VishnuSequenceRecognizer(model["checkpoint_ref"])
        truth, candidate_predictions, baseline_predictions = [], [], []
        candidate_start = time.perf_counter()
        for row in rows:
            truth.append(str(row["label"]))
            candidate_predictions.append(recognizer.predict_payload(dict(row["input"]))[0])
        candidate_ms = (time.perf_counter() - candidate_start) * 1000.0
        baseline = baseline or TesseractLineBaseline()
        baseline_error = None
        baseline_start = time.perf_counter()
        try:
            for row in rows:
                image_bytes = base64.b64decode(str(dict(row["input"]).get("image_png_b64") or ""), validate=True)
                baseline_predictions.append(str(baseline.predict(image_bytes) or ""))
        except (OcrUnavailable, Exception) as exc:
            baseline_error = f"baseline_unavailable:{exc.__class__.__name__}"
        baseline_ms = (time.perf_counter() - baseline_start) * 1000.0
        candidate_metrics = _text_metrics(truth, candidate_predictions, candidate_ms)
        baseline_metrics = _text_metrics(truth, baseline_predictions, baseline_ms) if baseline_error is None and len(baseline_predictions) == len(truth) else _text_metrics(truth, [""] * len(truth), baseline_ms)
        reasons = []
        evaluation = self.content_models.evaluator.evaluate_metrics(task, candidate_metrics)
        reasons.extend(evaluation.reasons)
        if baseline_error:
            reasons.append(baseline_error)
        if candidate_metrics["cer"] > baseline_metrics["cer"] + float(max_cer_regression):
            reasons.append("candidate_cer_worse_than_baseline")
        accuracy_delta = candidate_metrics["word_accuracy"] - baseline_metrics["word_accuracy"]
        if accuracy_delta < float(min_accuracy_delta):
            reasons.append("candidate_accuracy_delta_below_requirement")
        return self._record_evidence(
            model_id=model_id,
            task=task.value,
            baseline_id=str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas={
                "cer": candidate_metrics["cer"] - baseline_metrics["cer"],
                "word_accuracy": accuracy_delta,
                "avg_latency_ms": candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
            },
            reasons=reasons,
        )

    def shadow_features(self, model_id: str, *, baseline: FeatureBaseline, min_metric_delta: float = 0.0) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        task = ContentModelTask(str(model["task"]))
        if task not in {ContentModelTask.LAYOUT, ContentModelTask.TABLE} or model["status"] != "candidate":
            raise ValueError("feature shadow qualification requires a layout/table candidate")
        rows = _read_jsonl(self._snapshot_for(model).test_path) or _read_jsonl(self._snapshot_for(model).validation_path)
        if not rows:
            raise ValueError("shadow qualification requires a held-out split")
        classifier = VishnuFeatureClassifier(model["checkpoint_ref"])
        truth = [str(row["label"]) for row in rows]
        candidate_predictions = [classifier.predict_payload(dict(row["input"])) for row in rows]
        baseline_predictions = [str(baseline.predict(dict(row["input"]))) for row in rows]
        metric_name = "f1" if task is ContentModelTask.LAYOUT else "cell_f1"
        candidate_f1 = _macro_f1(truth, candidate_predictions)
        baseline_f1 = _macro_f1(truth, baseline_predictions)
        candidate_metrics = {metric_name: candidate_f1, "accuracy": sum(int(a == b) for a, b in zip(truth, candidate_predictions)) / len(truth)}
        baseline_metrics = {metric_name: baseline_f1, "accuracy": sum(int(a == b) for a, b in zip(truth, baseline_predictions)) / len(truth)}
        reasons = list(self.content_models.evaluator.evaluate_metrics(task, candidate_metrics).reasons)
        delta = candidate_f1 - baseline_f1
        if delta < float(min_metric_delta):
            reasons.append("candidate_metric_delta_below_requirement")
        return self._record_evidence(
            model_id=model_id,
            task=task.value,
            baseline_id=str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas={metric_name: delta, "accuracy": candidate_metrics["accuracy"] - baseline_metrics["accuracy"]},
            reasons=reasons,
        )

    def _record_evidence(
        self,
        *,
        model_id: str,
        task: str,
        baseline_id: str,
        records: int,
        candidate_metrics: dict[str, float],
        baseline_metrics: dict[str, float],
        deltas: dict[str, float],
        reasons: list[str],
    ) -> dict[str, Any]:
        created_at = _now()
        payload = {
            "model_id": model_id,
            "task": task,
            "baseline_id": baseline_id,
            "records": records,
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": deltas,
            "passed": not reasons,
            "reasons": reasons,
            "created_at": created_at,
        }
        evidence = ModelCycleEvidence(
            model_id=model_id,
            task=task,
            baseline_id=baseline_id,
            records=records,
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
            raise ValueError("Stage 12 model requires successful shadow qualification before owner approval")
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(self, model_id: str, *, owner_authorized: bool, actor: str = "release_controller") -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 12 model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(model_id, owner_authorized=owner_authorized, actor=actor)

    def record_prediction_correction(
        self,
        *,
        model_id: str,
        task: ContentModelTask,
        subtask: str,
        language: str,
        source_fingerprint: str,
        input_payload: Any,
        predicted_label: Any,
        corrected_label: Any,
        provenance: dict[str, Any],
        consent_basis: str,
    ) -> dict[str, Any]:
        return self.feedback.submit(
            task=task,
            subtask=subtask,
            language=language,
            source_fingerprint=source_fingerprint,
            input_payload=input_payload,
            label=corrected_label,
            provenance={**dict(provenance or {}), "model_id": model_id, "predicted_label": predicted_label},
            consent_basis=consent_basis,
            correction_kind="prediction_correction",
        )
