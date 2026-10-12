from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from PIL import Image, ImageOps

from file_intelligence.ocr import OcrUnavailable, TesseractOcrProvider
from training.content_models import (
    ContentDatasetSnapshot,
    ContentModelCoordinator,
    ContentModelEvaluator,
    ContentModelTask,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    file = Path(path)
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]


class OCRSamplePolicyError(ValueError):
    pass


class GlyphImageVectorizer:
    """Deterministic local raster normalizer for the first Vishnu OCR-family model.

    This model intentionally recognizes one isolated glyph at a time. It is not a
    full-page OCR engine and must not be routed as one until a broader trained
    model is separately qualified.
    """

    def __init__(self, width: int = 20, height: int = 20):
        self.width = max(8, min(int(width), 64))
        self.height = max(8, min(int(height), 64))

    def payload(self, image_bytes: bytes) -> dict[str, Any]:
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            raise OCRSamplePolicyError("OCR sample image bytes are required")
        try:
            with Image.open(io.BytesIO(bytes(image_bytes))) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("L")
        except Exception as exc:
            raise OCRSamplePolicyError("OCR sample is not a readable image") from exc

        image = ImageOps.autocontrast(image)
        inverted = ImageOps.invert(image)
        bbox = inverted.getbbox()
        if bbox is None:
            raise OCRSamplePolicyError("OCR sample image is blank")
        glyph = image.crop(bbox)
        max_w = max(1, self.width - 4)
        max_h = max(1, self.height - 4)
        glyph.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        canvas = Image.new("L", (self.width, self.height), 255)
        x = (self.width - glyph.width) // 2
        y = (self.height - glyph.height) // 2
        canvas.paste(glyph, (x, y))
        pixels = list(canvas.getdata())
        features = [round(1.0 - (float(value) / 255.0), 6) for value in pixels]
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=False)
        normalized = buffer.getvalue()
        return {
            "schema_version": 1,
            "kind": "isolated_glyph_raster",
            "width": self.width,
            "height": self.height,
            "features": features,
            "image_png_b64": base64.b64encode(normalized).decode("ascii"),
            "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        }

    def vector(self, image_bytes: bytes) -> list[float]:
        return [float(value) for value in self.payload(image_bytes)["features"]]


class GovernedOCRSampleCollector:
    """Fail-closed collector for owner-approved OCR/handwriting training samples."""

    ALLOWED_CONSENT = {"owner_provided", "licensed", "public_domain", "synthetic"}

    def __init__(self, vectorizer: GlyphImageVectorizer | None = None):
        self.vectorizer = vectorizer or GlyphImageVectorizer()

    def collect(self, samples: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in samples:
            label = str(raw.get("label") or "")
            if len(label) != 1:
                raise OCRSamplePolicyError("Stage 11 glyph samples require exactly one Unicode character label")
            source = str(raw.get("source_fingerprint") or "").strip()
            if not source:
                raise OCRSamplePolicyError("OCR sample requires source_fingerprint")
            consent = str(raw.get("consent_basis") or "").strip()
            if consent not in self.ALLOWED_CONSENT:
                raise OCRSamplePolicyError("OCR sample requires an approved explicit consent_basis")
            provenance = dict(raw.get("provenance") or {})
            if provenance.get("approved_for_training") is not True:
                raise OCRSamplePolicyError("OCR sample must be explicitly approved_for_training")
            license_name = str(provenance.get("license") or "").strip()
            if not license_name:
                raise OCRSamplePolicyError("OCR sample provenance requires a license or ownership basis")

            image_bytes = raw.get("image_bytes")
            if image_bytes is None and raw.get("image_png_b64"):
                try:
                    image_bytes = base64.b64decode(str(raw["image_png_b64"]), validate=True)
                except Exception as exc:
                    raise OCRSamplePolicyError("OCR sample base64 image is invalid") from exc
            payload = self.vectorizer.payload(bytes(image_bytes or b""))
            sample_hash = hashlib.sha256(
                (payload["normalized_sha256"] + "\0" + label).encode("utf-8")
            ).hexdigest()
            if sample_hash in seen:
                continue
            seen.add(sample_hash)
            accepted.append(
                {
                    "id": str(raw.get("id") or f"ocr-{sample_hash[:20]}"),
                    "input": payload,
                    "label": label,
                    "source_fingerprint": source,
                    "provenance": {
                        **provenance,
                        "sample_sha256": sample_hash,
                        "normalization": f"vishnu-glyph-{self.vectorizer.width}x{self.vectorizer.height}-v1",
                    },
                    "consent_basis": consent,
                }
            )
        if len(accepted) < 3:
            raise OCRSamplePolicyError("governed OCR dataset requires at least 3 unique approved samples")
        return accepted


class VishnuGlyphPrototypeTrainer:
    """A real local Vishnu-trained isolated-glyph prototype recognizer.

    The learned parameters are per-label mean raster vectors. This deliberately
    small first OCR-family model provides auditable training and evaluation
    without pretending to be a general page OCR model.
    """

    backend_id = "vishnu-glyph-prototype-v1"
    task = ContentModelTask.OCR

    @staticmethod
    def _vector(row: dict[str, Any]) -> list[float]:
        payload = row.get("input") or {}
        values = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(values, list) or not values:
            raise ValueError("glyph dataset row has no raster feature vector")
        return [float(value) for value in values]

    @staticmethod
    def _predict(model: dict[str, Any], vector: list[float]) -> tuple[str, float]:
        prototypes = model.get("prototypes") or {}
        if not prototypes:
            raise RuntimeError("glyph model has no learned prototypes")
        best_label = ""
        best_distance: float | None = None
        second_distance: float | None = None
        for label, prototype in prototypes.items():
            weights = [float(value) for value in prototype]
            if len(weights) != len(vector):
                raise ValueError("glyph vector shape does not match model")
            distance = sum((left - right) ** 2 for left, right in zip(vector, weights)) / len(vector)
            if best_distance is None or distance < best_distance:
                second_distance = best_distance
                best_distance = distance
                best_label = str(label)
            elif second_distance is None or distance < second_distance:
                second_distance = distance
        if best_distance is None:
            raise RuntimeError("glyph model could not score input")
        if second_distance is None:
            confidence = max(0.0, min(1.0, 1.0 - best_distance))
        else:
            margin = max(0.0, second_distance - best_distance)
            confidence = max(0.0, min(1.0, margin / max(second_distance, 1e-9)))
        return best_label, confidence

    @classmethod
    def _metrics(cls, model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float]:
        if not rows:
            return {"cer": 1.0, "wer": 1.0, "word_accuracy": 0.0, "char_accuracy": 0.0, "evaluation_records": 0.0}
        correct = 0
        for row in rows:
            predicted, _ = cls._predict(model, cls._vector(row))
            correct += int(predicted == str(row.get("label") or ""))
        accuracy = correct / len(rows)
        error = 1.0 - accuracy
        return {
            "cer": error,
            "wer": error,
            "word_accuracy": accuracy,
            "char_accuracy": accuracy,
            "evaluation_records": float(len(rows)),
        }

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("glyph trainer received wrong content model task")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("glyph train split is empty")
        sums: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        width = height = None
        for row in rows:
            payload = row.get("input") or {}
            if not isinstance(payload, dict) or payload.get("kind") != "isolated_glyph_raster":
                raise ValueError("glyph trainer requires isolated_glyph_raster inputs")
            vector = self._vector(row)
            label = str(row.get("label") or "")
            if len(label) != 1:
                raise ValueError("glyph trainer requires one-character labels")
            width = int(payload.get("width") or 0)
            height = int(payload.get("height") or 0)
            if width * height != len(vector):
                raise ValueError("glyph raster dimensions do not match feature vector")
            if label not in sums:
                sums[label] = [0.0] * len(vector)
                counts[label] = 0
            if len(sums[label]) != len(vector):
                raise ValueError("glyph training vectors must share one shape")
            sums[label] = [left + right for left, right in zip(sums[label], vector)]
            counts[label] += 1
        if len(sums) < 2:
            raise ValueError("glyph model requires at least two labels")
        prototypes = {
            label: [round(value / counts[label], 8) for value in values]
            for label, values in sorted(sums.items())
        }
        model = {
            "schema_version": 1,
            "model_type": "vishnu-isolated-glyph-prototype",
            "model_scope": "isolated_glyph_only",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "feature_width": int(width or 0),
            "feature_height": int(height or 0),
            "labels": sorted(prototypes),
            "samples_per_label": counts,
            "prototypes": prototypes,
            "created_at": _now(),
            "trained_by_vishnu": True,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(
            json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        evaluation_rows = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path) or rows
        return output_dir, self._metrics(model, evaluation_rows)


class VishnuGlyphRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        self.checkpoint_ref = Path(checkpoint_ref)
        self.model = json.loads((self.checkpoint_ref / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-isolated-glyph-prototype":
            raise ValueError("unsupported Vishnu OCR-family artifact")
        self.vectorizer = GlyphImageVectorizer(
            int(self.model["feature_width"]), int(self.model["feature_height"])
        )

    def predict_payload(self, payload: dict[str, Any]) -> tuple[str, float]:
        vector = [float(value) for value in payload.get("features") or []]
        return VishnuGlyphPrototypeTrainer._predict(self.model, vector)

    def predict_image(self, image_bytes: bytes) -> tuple[str, float]:
        return self.predict_payload(self.vectorizer.payload(image_bytes))


class GlyphBaseline(Protocol):
    baseline_id: str

    def predict(self, image_bytes: bytes) -> str: ...


class TesseractGlyphBaseline:
    """Current local OCR baseline used for shadow comparison, never labeled Vishnu-trained."""

    baseline_id = "tesseract-local-glyph"

    def __init__(self, provider: TesseractOcrProvider | None = None):
        self.provider = provider or TesseractOcrProvider(language="auto", orientation=False, psm=10)

    def predict(self, image_bytes: bytes) -> str:
        blocks = self.provider.extract(image_bytes, filename="shadow-glyph.png", access_class="owner")
        text = "".join(str(item.get("text") or "") for item in blocks).strip()
        return text[0] if text else ""


@dataclass(frozen=True)
class OCRBenchmarkResult:
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


class OCRShadowBenchmark:
    def __init__(self, *, max_cer_regression: float = 0.0, min_accuracy_delta: float = 0.0):
        self.max_cer_regression = float(max_cer_regression)
        self.min_accuracy_delta = float(min_accuracy_delta)
        self.evaluator = ContentModelEvaluator()

    @staticmethod
    def _metrics(expected: list[str], predicted: list[str], elapsed_ms: float) -> dict[str, float]:
        records = len(expected)
        correct = sum(int(left == right) for left, right in zip(expected, predicted))
        accuracy = (correct / records) if records else 0.0
        error = 1.0 - accuracy
        return {
            "cer": error,
            "wer": error,
            "word_accuracy": accuracy,
            "char_accuracy": accuracy,
            "records": float(records),
            "avg_latency_ms": (elapsed_ms / records) if records else 0.0,
        }

    def run(
        self,
        *,
        model_id: str,
        snapshot: ContentDatasetSnapshot,
        candidate: VishnuGlyphRecognizer,
        baseline: GlyphBaseline,
    ) -> OCRBenchmarkResult:
        rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path)
        if not rows:
            raise ValueError("shadow qualification requires a held-out split")
        expected: list[str] = []
        candidate_predictions: list[str] = []
        baseline_predictions: list[str] = []

        candidate_start = time.perf_counter()
        for row in rows:
            expected.append(str(row.get("label") or ""))
            prediction, _ = candidate.predict_payload(dict(row.get("input") or {}))
            candidate_predictions.append(prediction)
        candidate_ms = (time.perf_counter() - candidate_start) * 1000.0

        baseline_error: str | None = None
        baseline_start = time.perf_counter()
        try:
            for row in rows:
                payload = dict(row.get("input") or {})
                image_bytes = base64.b64decode(str(payload.get("image_png_b64") or ""), validate=True)
                baseline_predictions.append(str(baseline.predict(image_bytes) or "")[:1])
        except (OcrUnavailable, Exception) as exc:
            baseline_error = f"baseline_unavailable:{exc.__class__.__name__}"
        baseline_ms = (time.perf_counter() - baseline_start) * 1000.0

        candidate_metrics = self._metrics(expected, candidate_predictions, candidate_ms)
        if baseline_error is None and len(baseline_predictions) == len(expected):
            baseline_metrics = self._metrics(expected, baseline_predictions, baseline_ms)
        else:
            baseline_metrics = {
                "cer": 1.0,
                "wer": 1.0,
                "word_accuracy": 0.0,
                "char_accuracy": 0.0,
                "records": float(len(expected)),
                "avg_latency_ms": (baseline_ms / len(expected)) if expected else 0.0,
            }

        reasons: list[str] = []
        evaluation = self.evaluator.evaluate_metrics(ContentModelTask.OCR, candidate_metrics)
        reasons.extend(evaluation.reasons)
        if baseline_error:
            reasons.append(baseline_error)
        if candidate_metrics["cer"] > baseline_metrics["cer"] + self.max_cer_regression:
            reasons.append("candidate_cer_worse_than_baseline")
        accuracy_delta = candidate_metrics["word_accuracy"] - baseline_metrics["word_accuracy"]
        if accuracy_delta < self.min_accuracy_delta:
            reasons.append("candidate_accuracy_delta_below_requirement")
        deltas = {
            "cer": candidate_metrics["cer"] - baseline_metrics["cer"],
            "word_accuracy": accuracy_delta,
            "avg_latency_ms": candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
        }
        created_at = _now()
        evidence_payload = {
            "model_id": model_id,
            "task": ContentModelTask.OCR.value,
            "baseline_id": str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            "records": len(expected),
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": deltas,
            "passed": not reasons,
            "reasons": reasons,
            "created_at": created_at,
        }
        evidence_sha256 = hashlib.sha256(_canonical(evidence_payload).encode("utf-8")).hexdigest()
        return OCRBenchmarkResult(
            model_id=model_id,
            task=ContentModelTask.OCR.value,
            baseline_id=evidence_payload["baseline_id"],
            records=len(expected),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas=deltas,
            passed=not reasons,
            reasons=tuple(reasons),
            evidence_sha256=evidence_sha256,
            created_at=created_at,
        )


class ShadowQualificationStore:
    """Append-only shadow evidence used by the Stage 11 promotion controller."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_shadow_qualifications(
                    evidence_sha256 TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_ocr_shadow_model ON ocr_shadow_qualifications(model_id,created_at)"
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def record(self, result: OCRBenchmarkResult) -> dict[str, Any]:
        payload = result.public()
        with self._con() as con:
            con.execute(
                "INSERT OR IGNORE INTO ocr_shadow_qualifications VALUES(?,?,?,?,?)",
                (
                    result.evidence_sha256,
                    result.model_id,
                    int(result.passed),
                    result.created_at,
                    _canonical(payload),
                ),
            )
        return payload

    def latest(self, model_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                "SELECT evidence_json FROM ocr_shadow_qualifications WHERE model_id=? ORDER BY created_at DESC,evidence_sha256 DESC LIMIT 1",
                (model_id,),
            ).fetchone()
        return json.loads(row["evidence_json"]) if row else None


class OCRModelMaturationCoordinator:
    """Stage 11 governed train -> benchmark -> shadow -> owner approval boundary."""

    def __init__(
        self,
        content_models: ContentModelCoordinator,
        *,
        shadow_store_path: str | Path,
        collector: GovernedOCRSampleCollector | None = None,
        benchmark: OCRShadowBenchmark | None = None,
    ):
        self.content_models = content_models
        self.collector = collector or GovernedOCRSampleCollector()
        self.benchmark = benchmark or OCRShadowBenchmark()
        self.shadow = ShadowQualificationStore(shadow_store_path)

    def train_candidate(
        self,
        samples: Iterable[dict[str, Any]],
        *,
        dataset_name: str = "vishnu-ocr-glyph-v1",
    ) -> dict[str, Any]:
        governed = self.collector.collect(samples)
        return self.content_models.train(
            ContentModelTask.OCR,
            governed,
            VishnuGlyphPrototypeTrainer(),
            dataset_name=dataset_name,
            metadata={
                "stage": 11,
                "model_scope": "isolated_glyph_only",
                "full_page_ocr": False,
                "trained_by_vishnu": True,
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

    def shadow_qualify(self, model_id: str, *, baseline: GlyphBaseline | None = None) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        if model["task"] != ContentModelTask.OCR.value:
            raise ValueError("Stage 11 OCR maturation only accepts OCR candidates")
        if model["status"] != "candidate":
            raise ValueError("shadow qualification requires an evaluated candidate")
        result = self.benchmark.run(
            model_id=model_id,
            snapshot=self._snapshot_for(model),
            candidate=VishnuGlyphRecognizer(model["checkpoint_ref"]),
            baseline=baseline or TesseractGlyphBaseline(),
        )
        return self.shadow.record(result)

    def approve(self, model_id: str, *, owner_id: str) -> dict[str, Any]:
        evidence = self.shadow.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("OCR model requires successful shadow qualification before owner approval")
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(
        self,
        model_id: str,
        *,
        owner_authorized: bool,
        actor: str = "release_controller",
    ) -> dict[str, Any]:
        evidence = self.shadow.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("OCR model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(
            model_id,
            owner_authorized=owner_authorized,
            actor=actor,
        )
