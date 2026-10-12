from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
from collections import defaultdict
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
from training.document_vision import _recognition_metrics


class Stage18TrainingPolicyError(ValueError):
    pass


STAGE18_SUBTASKS = (
    "stage18_chart_type",
    "stage18_diagram_type",
    "stage18_equation_role",
    "stage18_ui_element_type",
    "stage18_visual_qa_support",
)

STAGE18_MIN_F1 = {
    "stage18_chart_type": 0.85,
    "stage18_diagram_type": 0.80,
    "stage18_equation_role": 0.85,
    "stage18_ui_element_type": 0.85,
    "stage18_visual_qa_support": 0.90,
}

STAGE18_REAL_WORLD_TASKS = ("chart", "diagram", "equation", "ui")
STAGE18_CAPTURE_KINDS = ("scan", "photo", "screenshot", "handwriting")


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


def _heldout_rows(snapshot: ContentDatasetSnapshot) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in (snapshot.validation_path, snapshot.test_path):
        for row in _read_jsonl(path):
            identity = str(row.get("id") or "").strip() or hashlib.sha256(_canonical(row).encode("utf-8")).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            output.append(row)
    return output


def _tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        text = " ".join(
            str(value.get(key) or "")
            for key in ("text", "context", "candidate", "question", "caption", "ocr_text")
        )
    else:
        text = str(value or "")
    return re.findall(r"[\w@.+#/%-]{2,}", text.casefold(), flags=re.UNICODE)[:8000]


class Stage18VisualSemanticVectorizer:
    """Compact local image/text feature vector for governed Stage 18 heads."""

    HASH_BINS = 48
    VISUAL_FEATURES = 18

    @classmethod
    def _image_features(cls, payload: dict[str, Any]) -> np.ndarray:
        encoded = str(payload.get("image_png_b64") or "")
        if not encoded:
            values = payload.get("visual_features") or {}
            if isinstance(values, dict):
                keys = (
                    "ink_density", "horizontal_rules", "vertical_rules", "boxes", "bars",
                    "width", "height", "components", "color_variance",
                )
                raw = [float(values.get(key) or 0.0) for key in keys]
                raw.extend([0.0] * (cls.VISUAL_FEATURES - len(raw)))
                vector = np.asarray(raw[: cls.VISUAL_FEATURES], dtype=np.float64)
                scale = np.maximum(1.0, np.abs(vector))
                return vector / scale
            return np.zeros(cls.VISUAL_FEATURES, dtype=np.float64)
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
        except Exception as exc:
            raise Stage18TrainingPolicyError("Stage 18 visual sample image is unreadable") from exc
        image.thumbnail((128, 128), Image.Resampling.LANCZOS)
        array = np.asarray(image, dtype=np.float64) / 255.0
        gray = np.mean(array, axis=2)
        ink = gray < 0.78
        rows = np.mean(ink, axis=1)
        cols = np.mean(ink, axis=0)
        color_var = np.var(array, axis=(0, 1))
        values = np.asarray(
            [
                float(np.mean(ink)),
                float(np.mean(rows > 0.55)),
                float(np.mean(cols > 0.55)),
                float(np.var(rows)),
                float(np.var(cols)),
                float(np.mean(gray)),
                float(np.std(gray)),
                float(np.mean(array[:, :, 0])),
                float(np.mean(array[:, :, 1])),
                float(np.mean(array[:, :, 2])),
                float(color_var[0]),
                float(color_var[1]),
                float(color_var[2]),
                float(image.width / max(1, image.height)),
                float(np.mean(ink[: max(1, image.height // 3)])),
                float(np.mean(ink[image.height // 3 : max(image.height // 3 + 1, 2 * image.height // 3)])),
                float(np.mean(ink[max(0, 2 * image.height // 3) :])),
                float(np.mean(np.abs(np.diff(gray, axis=1)))) if image.width > 1 else 0.0,
            ],
            dtype=np.float64,
        )
        return values

    @classmethod
    def features(cls, payload: dict[str, Any]) -> np.ndarray:
        visual = cls._image_features(payload)
        text = np.zeros(cls.HASH_BINS, dtype=np.float64)
        for token in _tokens(payload):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % cls.HASH_BINS
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            text[index] += sign
        norm = float(np.linalg.norm(text))
        if norm > 0:
            text /= norm
        return np.concatenate((visual, text))


class VishnuStage18MultimodalTrainer:
    task = ContentModelTask.DOCUMENT_CLASSIFICATION
    backend_id = "vishnu-stage18-multimodal-centroid-v1"

    @staticmethod
    def _subtask(row: dict[str, Any]) -> str:
        payload = row.get("input") or {}
        subtask = str(payload.get("subtask") or "") if isinstance(payload, dict) else ""
        if subtask not in STAGE18_SUBTASKS:
            raise Stage18TrainingPolicyError(f"unsupported Stage 18 subtask: {subtask}")
        return subtask

    @staticmethod
    def _train_head(rows: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[np.ndarray]] = defaultdict(list)
        for row in rows:
            label = str(row.get("label") or "").strip()
            if not label:
                raise Stage18TrainingPolicyError("Stage 18 sample requires a label")
            grouped[label].append(Stage18VisualSemanticVectorizer.features(dict(row.get("input") or {})))
        if len(grouped) < 2:
            raise Stage18TrainingPolicyError("each Stage 18 head requires at least two labels")
        centroids: dict[str, list[float]] = {}
        for label, vectors in grouped.items():
            centroid = np.mean(np.stack(vectors), axis=0)
            norm = float(np.linalg.norm(centroid))
            if norm > 0:
                centroid = centroid / norm
            centroids[label] = centroid.round(9).tolist()
        return {"labels": sorted(centroids), "centroids": centroids}

    @staticmethod
    def _predict_head(head: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        vector = Stage18VisualSemanticVectorizer.features(payload)
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        scored: list[tuple[float, str]] = []
        for label, raw in dict(head.get("centroids") or {}).items():
            centroid = np.asarray(raw, dtype=np.float64)
            score = float(np.dot(vector, centroid))
            scored.append((score, str(label)))
        if not scored:
            raise Stage18TrainingPolicyError("Stage 18 head has no labels")
        scored.sort(key=lambda item: (-item[0], item[1]))
        top = scored[0][0]
        weights = [math.exp(max(-30.0, min(0.0, score - top)) * 4.0) for score, _ in scored]
        denominator = max(1e-12, sum(weights))
        alternatives = [
            {"label": label, "confidence": weight / denominator}
            for weight, (_, label) in zip(weights, scored)
        ]
        return {
            "label": alternatives[0]["label"],
            "confidence": float(alternatives[0]["confidence"]),
            "alternatives": alternatives[:3],
        }

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("Stage 18 trainer requires document-classification authority")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise Stage18TrainingPolicyError("Stage 18 train split is empty")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[self._subtask(row)].append(row)
        missing = sorted(set(STAGE18_SUBTASKS) - set(grouped))
        if missing:
            raise Stage18TrainingPolicyError(f"Stage 18 training is missing heads: {missing}")
        heads = {subtask: self._train_head(grouped[subtask]) for subtask in STAGE18_SUBTASKS}
        model = {
            "schema_version": 1,
            "model_type": "vishnu-stage18-multimodal-visual-semantics",
            "task": self.task.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "subtasks": list(STAGE18_SUBTASKS),
            "heads": heads,
            "architecture": {
                "family": "visual_text_centroid",
                "visual_features": Stage18VisualSemanticVectorizer.VISUAL_FEATURES,
                "hashed_text_features": Stage18VisualSemanticVectorizer.HASH_BINS,
                "stage15_layout_input": True,
                "stage16_semantic_context": True,
                "stage17_production_scope": True,
            },
            "trained_by_vishnu": True,
            "multimodal": True,
            "foundation_model": False,
            "real_world_corpus_qualified": False,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        evaluation = _heldout_rows(snapshot)
        if not evaluation:
            raise Stage18TrainingPolicyError("Stage 18 requires held-out validation/test records")
        by_truth: dict[str, list[str]] = defaultdict(list)
        by_pred: dict[str, list[str]] = defaultdict(list)
        truth: list[str] = []
        pred: list[str] = []
        for row in evaluation:
            subtask = self._subtask(row)
            expected = str(row.get("label") or "")
            guess = str(self._predict_head(heads[subtask], dict(row.get("input") or {}))["label"])
            truth.append(expected)
            pred.append(guess)
            by_truth[subtask].append(expected)
            by_pred[subtask].append(guess)
        metrics = {
            "accuracy": sum(int(a == b) for a, b in zip(truth, pred)) / max(1, len(truth)),
            "macro_f1": _macro_f1(truth, pred),
            "evaluation_records": float(len(truth)),
        }
        for subtask in STAGE18_SUBTASKS:
            values = by_truth.get(subtask, [])
            guesses = by_pred.get(subtask, [])
            metrics[f"{subtask}_records"] = float(len(values))
            metrics[f"{subtask}_f1"] = _macro_f1(values, guesses) if values else 0.0
        return output_dir, metrics


class VishnuStage18MultimodalModel:
    def __init__(self, checkpoint_ref: str | Path):
        self.model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-stage18-multimodal-visual-semantics":
            raise ValueError("unsupported Stage 18 multimodal artifact")
        self.heads = dict(self.model.get("heads") or {})

    def predict(self, subtask: str, payload: dict[str, Any], *, reject_below: float = 0.0) -> dict[str, Any]:
        if subtask not in self.heads:
            raise Stage18TrainingPolicyError(f"Stage 18 artifact has no head: {subtask}")
        result = VishnuStage18MultimodalTrainer._predict_head(self.heads[subtask], payload)
        threshold = max(0.0, min(1.0, float(reject_below)))
        accepted = float(result["confidence"]) >= threshold
        return {
            **result,
            "raw_label": result["label"],
            "label": result["label"] if accepted else "unknown",
            "accepted": accepted,
            "rejection_reason": None if accepted else "low_confidence",
        }


class VisualBaseline(Protocol):
    baseline_id: str

    def predict(self, subtask: str, payload: dict[str, Any]) -> str: ...


class Stage18MultimodalCoordinator:
    """Stage 12 feedback -> Stage 9 registry -> shadow -> owner -> release controller."""

    def __init__(self, *, content_models: ContentModelCoordinator, feedback: GovernedContentFeedbackStore, evidence_path: str | Path):
        self.content_models = content_models
        self.feedback = feedback
        self.evidence = ModelCycleEvidenceStore(evidence_path)

    def _prepare_samples(self, *, languages: Iterable[str] | None = None) -> list[dict[str, Any]]:
        rows = self.feedback.approved_samples(ContentModelTask.DOCUMENT_CLASSIFICATION, languages=languages)
        prepared: list[dict[str, Any]] = []
        for row in rows:
            provenance = dict(row.get("provenance") or {})
            subtask = str(provenance.get("subtask") or "")
            if subtask not in STAGE18_SUBTASKS:
                continue
            original = row.get("input")
            payload = dict(original) if isinstance(original, dict) else {"text": str(original or "")}
            payload["subtask"] = subtask
            if not _tokens(payload) and not payload.get("image_png_b64") and not payload.get("visual_features"):
                raise Stage18TrainingPolicyError("Stage 18 approved feedback requires visual or text evidence")
            prepared.append(
                {
                    **row,
                    "input": payload,
                    "provenance": {
                        **provenance,
                        "stage18_multimodal_visual_reasoning": True,
                        "semantic_subtask": subtask,
                    },
                }
            )
        present = {str((row.get("input") or {}).get("subtask") or "") for row in prepared}
        missing = sorted(set(STAGE18_SUBTASKS) - present)
        if missing:
            raise Stage18TrainingPolicyError(f"Stage 18 approved feedback is missing heads: {missing}")
        return prepared

    def train_candidate(self, *, languages: Iterable[str] | None = None, dataset_name: str | None = None) -> dict[str, Any]:
        return self.content_models.train(
            ContentModelTask.DOCUMENT_CLASSIFICATION,
            self._prepare_samples(languages=languages),
            VishnuStage18MultimodalTrainer(),
            dataset_name=dataset_name or "vishnu-stage18-multimodal-visual-semantics",
            metadata={
                "stage": 18,
                "subtasks": list(STAGE18_SUBTASKS),
                "charts": True,
                "diagrams": True,
                "equations": True,
                "figures": True,
                "ui_understanding": True,
                "grounded_visual_qa": True,
                "multimodal_evidence_graph": True,
                "trained_by_vishnu": True,
                "foundation_model": False,
                "real_world_corpus_qualified": False,
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

    def shadow_qualify(self, model_id: str, *, baseline: VisualBaseline, min_accuracy_delta: float = 0.0) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        if model["task"] != ContentModelTask.DOCUMENT_CLASSIFICATION.value or int(dict(model.get("metadata") or {}).get("stage") or 0) != 18:
            raise ValueError("Stage 18 shadow qualification requires a Stage 18 candidate")
        if model["status"] != "candidate":
            raise ValueError("Stage 18 shadow qualification requires candidate status")
        rows = _heldout_rows(self._snapshot_for(model))
        if not rows:
            raise Stage18TrainingPolicyError("Stage 18 shadow qualification requires held-out records")
        candidate = VishnuStage18MultimodalModel(model["checkpoint_ref"])
        truth: list[str] = []
        guesses: list[str] = []
        baseline_guesses: list[str] = []
        by_truth: dict[str, list[str]] = defaultdict(list)
        by_guess: dict[str, list[str]] = defaultdict(list)
        reasons: list[str] = []
        for row in rows:
            payload = dict(row.get("input") or {})
            subtask = str(payload.get("subtask") or "")
            if subtask not in STAGE18_SUBTASKS:
                raise Stage18TrainingPolicyError(f"held-out row has unsupported Stage 18 subtask: {subtask}")
            expected = str(row.get("label") or "")
            predicted = str(candidate.predict(subtask, payload, reject_below=0.0)["label"])
            baseline_value = str(baseline.predict(subtask, payload) or "unknown")
            truth.append(expected)
            guesses.append(predicted)
            baseline_guesses.append(baseline_value)
            by_truth[subtask].append(expected)
            by_guess[subtask].append(predicted)
        candidate_accuracy = sum(int(a == b) for a, b in zip(truth, guesses)) / max(1, len(truth))
        baseline_accuracy = sum(int(a == b) for a, b in zip(truth, baseline_guesses)) / max(1, len(truth))
        if candidate_accuracy < 0.85:
            reasons.append("stage18_accuracy_below_0.85")
        if candidate_accuracy - baseline_accuracy < float(min_accuracy_delta):
            reasons.append("stage18_accuracy_delta_below_requirement")
        candidate_metrics: dict[str, float] = {
            "accuracy": candidate_accuracy,
            "macro_f1": _macro_f1(truth, guesses),
        }
        for subtask, floor in STAGE18_MIN_F1.items():
            expected = by_truth.get(subtask, [])
            predicted = by_guess.get(subtask, [])
            if not expected:
                reasons.append(f"missing_heldout_head:{subtask}")
                candidate_metrics[f"{subtask}_f1"] = 0.0
                continue
            value = _macro_f1(expected, predicted)
            candidate_metrics[f"{subtask}_f1"] = value
            if value < floor:
                reasons.append(f"{subtask}_f1_below_{floor}")
        baseline_metrics = {
            "accuracy": baseline_accuracy,
            "macro_f1": _macro_f1(truth, baseline_guesses),
        }
        deltas = {
            "accuracy": candidate_accuracy - baseline_accuracy,
            "macro_f1": candidate_metrics["macro_f1"] - baseline_metrics["macro_f1"],
        }
        created_at = _now()
        payload = {
            "model_id": model_id,
            "stage": 18,
            "baseline_id": str(getattr(baseline, "baseline_id", baseline.__class__.__name__)),
            "records": len(rows),
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "deltas": deltas,
            "passed": not reasons,
            "reasons": sorted(set(reasons)),
            "created_at": created_at,
        }
        evidence = ModelCycleEvidence(
            model_id=model_id,
            task="stage18_multimodal_visual_reasoning",
            baseline_id=payload["baseline_id"],
            records=len(rows),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
            deltas=deltas,
            passed=not reasons,
            reasons=tuple(sorted(set(reasons))),
            evidence_sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
        return self.evidence.record(evidence)

    def approve(self, model_id: str, *, owner_id: str) -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 18 model requires successful shadow qualification before owner approval")
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(self, model_id: str, *, owner_authorized: bool, actor: str = "release_controller") -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 18 model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(model_id, owner_authorized=owner_authorized, actor=actor)

    def active_model(self) -> VishnuStage18MultimodalModel:
        model = self.content_models.registry.active(ContentModelTask.DOCUMENT_CLASSIFICATION)
        if not model or int(dict(model.get("metadata") or {}).get("stage") or 0) < 18:
            raise Stage18TrainingPolicyError("no active Stage 18 multimodal model")
        return VishnuStage18MultimodalModel(model["checkpoint_ref"])


@dataclass(frozen=True)
class Stage18RealWorldQualificationReport:
    qualified: bool
    records: int
    source_groups: int
    capture_counts: dict[str, int]
    recognition_metrics: dict[str, dict[str, float]]
    visual_metrics: dict[str, dict[str, float]]
    reasons: tuple[str, ...]
    evidence_sha256: str
    created_at: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        value["real_world_corpus_qualified"] = self.qualified
        value["synthetic_evidence_can_qualify"] = False
        return value


class Stage18RealWorldMultimodalQualifier:
    """Fail-closed real-world authority for OCR plus visual-reasoning evidence."""

    def __init__(
        self,
        *,
        min_source_groups: int = 8,
        max_calibration_error: float = 0.20,
        min_rejection_accuracy: float = 0.80,
        min_visual_accuracy: float = 0.80,
    ):
        self.min_source_groups = max(6, int(min_source_groups))
        self.max_calibration_error = max(0.0, min(1.0, float(max_calibration_error)))
        self.min_rejection_accuracy = max(0.0, min(1.0, float(min_rejection_accuracy)))
        self.min_visual_accuracy = max(0.0, min(1.0, float(min_visual_accuracy)))

    @staticmethod
    def _classification_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
        if not rows:
            return {"records": 0.0, "accuracy": 0.0, "rejection_accuracy": 0.0, "calibration_error": 1.0}
        exact = rejection = 0
        bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for row in rows:
            correct = str(row.get("truth") or "") == str(row.get("prediction") or "")
            exact += int(correct)
            accepted = bool(row.get("accepted", bool(row.get("prediction"))))
            should_accept = bool(row.get("should_accept", True))
            rejection += int(accepted == should_accept)
            confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
            bins[min(9, int(confidence * 10.0))].append((confidence, 1.0 if correct else 0.0))
        calibration = 0.0
        for values in bins.values():
            weight = len(values) / len(rows)
            calibration += weight * abs(
                sum(item[0] for item in values) / len(values)
                - sum(item[1] for item in values) / len(values)
            )
        return {
            "records": float(len(rows)),
            "accuracy": exact / len(rows),
            "rejection_accuracy": rejection / len(rows),
            "calibration_error": float(calibration),
        }

    def qualify(self, records: Iterable[dict[str, Any]]) -> Stage18RealWorldQualificationReport:
        rows = [dict(row) for row in records]
        reasons: list[str] = []
        captures = {name: 0 for name in STAGE18_CAPTURE_KINDS}
        split_sources: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}
        valid: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            provenance = dict(row.get("provenance") or {})
            if provenance.get("real_world") is not True:
                reasons.append(f"record_{index}:real_world_provenance_required")
                continue
            if provenance.get("synthetic") is True or provenance.get("simulated") is True:
                reasons.append(f"record_{index}:synthetic_or_simulated_evidence_forbidden")
                continue
            source = str(row.get("source_fingerprint") or "").strip()
            consent = str(row.get("consent_basis") or "").strip()
            license_basis = str(provenance.get("license") or provenance.get("ownership_basis") or "").strip()
            capture = str(provenance.get("capture_kind") or row.get("capture_kind") or "").strip()
            split = str(row.get("split") or "test").strip().lower()
            if not source:
                reasons.append(f"record_{index}:source_fingerprint_required")
                continue
            if consent not in {"owner_provided", "licensed", "public_domain"}:
                reasons.append(f"record_{index}:real_world_consent_required")
                continue
            if not license_basis:
                reasons.append(f"record_{index}:license_or_ownership_basis_required")
                continue
            if capture not in captures:
                reasons.append(f"record_{index}:unsupported_capture_kind")
                continue
            if split not in split_sources:
                reasons.append(f"record_{index}:invalid_split")
                continue
            captures[capture] += 1
            split_sources[split].add(source)
            valid.append(row)
        for name, count in captures.items():
            if count <= 0:
                reasons.append(f"missing_capture_kind:{name}")
        sources = set().union(*split_sources.values())
        if len(sources) < self.min_source_groups:
            reasons.append(f"source_groups_below_{self.min_source_groups}")
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
            if split_sources[left] & split_sources[right]:
                reasons.append(f"source_group_leakage:{left}:{right}")

        recognition_metrics: dict[str, dict[str, float]] = {}
        for task, cer_floor, word_floor in (("ocr", 0.15, 0.85), ("handwriting", 0.25, 0.70)):
            task_rows = [row for row in valid if str(row.get("task") or "") == task]
            metrics = _recognition_metrics(task_rows)
            recognition_metrics[task] = metrics
            if not task_rows:
                reasons.append(f"missing_real_world_{task}_records")
                continue
            if metrics["cer"] > cer_floor:
                reasons.append(f"{task}_cer_above_{cer_floor}")
            if metrics["word_accuracy"] < word_floor:
                reasons.append(f"{task}_word_accuracy_below_{word_floor}")
            if metrics["rejection_accuracy"] < self.min_rejection_accuracy:
                reasons.append(f"{task}_rejection_accuracy_below_{self.min_rejection_accuracy}")
            if metrics["calibration_error"] > self.max_calibration_error:
                reasons.append(f"{task}_calibration_error_above_{self.max_calibration_error}")

        visual_metrics: dict[str, dict[str, float]] = {}
        for task in STAGE18_REAL_WORLD_TASKS:
            task_rows = [row for row in valid if str(row.get("task") or "") == task]
            metrics = self._classification_metrics(task_rows)
            visual_metrics[task] = metrics
            if not task_rows:
                reasons.append(f"missing_real_world_{task}_records")
                continue
            if metrics["accuracy"] < self.min_visual_accuracy:
                reasons.append(f"{task}_accuracy_below_{self.min_visual_accuracy}")
            if metrics["rejection_accuracy"] < self.min_rejection_accuracy:
                reasons.append(f"{task}_rejection_accuracy_below_{self.min_rejection_accuracy}")
            if metrics["calibration_error"] > self.max_calibration_error:
                reasons.append(f"{task}_calibration_error_above_{self.max_calibration_error}")

        created_at = _now()
        payload = {
            "records": len(valid),
            "source_groups": len(sources),
            "capture_counts": captures,
            "recognition_metrics": recognition_metrics,
            "visual_metrics": visual_metrics,
            "reasons": sorted(set(reasons)),
            "created_at": created_at,
            "synthetic_evidence_can_qualify": False,
        }
        return Stage18RealWorldQualificationReport(
            qualified=not reasons,
            records=len(valid),
            source_groups=len(sources),
            capture_counts=captures,
            recognition_metrics=recognition_metrics,
            visual_metrics=visual_metrics,
            reasons=tuple(sorted(set(reasons))),
            evidence_sha256=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            created_at=created_at,
        )
