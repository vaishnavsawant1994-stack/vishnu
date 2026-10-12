from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np
from PIL import Image

from training.content_models import ContentDatasetSnapshot, ContentModelCoordinator, ContentModelTask
from training.continuous_content_models import (
    GovernedContentFeedbackStore,
    ModelCycleEvidence,
    ModelCycleEvidenceStore,
    _canonical,
    _now,
    _read_jsonl,
)
from training.document_vision import Stage15LayoutVectorizer, Stage15PolicyError, _macro_f1


TABLE_CELL_LABELS = ("body_cell", "header_cell", "merged_cell", "non_cell")


class TableCellBaseline(Protocol):
    baseline_id: str

    def predict(self, payload: dict[str, Any]) -> str: ...


class Stage15TableCellVectorizer:
    @staticmethod
    def features(payload: dict[str, Any]) -> np.ndarray:
        base = Stage15LayoutVectorizer.features(payload)
        image = Stage15LayoutVectorizer._decode(payload)
        array = 1.0 - np.asarray(
            image.resize((48, 48), Image.Resampling.BILINEAR), dtype=np.float64
        ) / 255.0
        row = np.mean(array, axis=1)
        col = np.mean(array, axis=0)
        extras = np.asarray(
            [
                float(np.max(row)),
                float(np.max(col)),
                float(np.mean(row > 0.20)),
                float(np.mean(col > 0.20)),
                float(np.mean(array[:6])),
                float(np.mean(array[-6:])),
                float(np.mean(array[:, :6])),
                float(np.mean(array[:, -6:])),
            ],
            dtype=np.float64,
        )
        return np.concatenate((base, extras))


class VishnuNeuralTableCellTrainer:
    task = ContentModelTask.TABLE
    backend_id = "vishnu-stage15-neural-table-cell-mlp-v1"

    def __init__(
        self,
        *,
        hidden_size: int = 40,
        epochs: int = 220,
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
        shifted = hidden @ w2 + b2
        shifted -= np.max(shifted, axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / np.maximum(np.sum(exp, axis=1, keepdims=True), 1e-12)

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not ContentModelTask.TABLE:
            raise ValueError("Stage 15 neural table trainer requires table task")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise ValueError("Stage 15 table train split is empty")
        labels = sorted({str(row.get("label") or "") for row in rows})
        if len(labels) < 2:
            raise ValueError("Stage 15 neural table model requires at least two labels")
        unsupported = [label for label in labels if label not in TABLE_CELL_LABELS]
        if unsupported:
            raise Stage15PolicyError(f"unsupported Stage 15 table labels: {unsupported}")
        index = {label: position for position, label in enumerate(labels)}
        x = np.stack(
            [Stage15TableCellVectorizer.features(dict(row.get("input") or {})) for row in rows]
        )
        y = np.asarray([index[str(row["label"])] for row in rows], dtype=np.int64)
        seed = int(snapshot.sha256[-16:], 16) % (2**32)
        rng = np.random.default_rng(seed)
        w1 = rng.normal(0.0, 0.18, size=(x.shape[1], self.hidden_size))
        b1 = np.zeros((1, self.hidden_size), dtype=np.float64)
        w2 = rng.normal(0.0, 0.18, size=(self.hidden_size, len(labels)))
        b2 = np.zeros((1, len(labels)), dtype=np.float64)
        for epoch in range(self.epochs):
            hidden = np.tanh(x @ w1 + b1)
            probabilities = self._predict_arrays(x, w1, b1, w2, b2)
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
            "model_type": "vishnu-stage15-neural-table-cell",
            "task": ContentModelTask.TABLE.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "labels": labels,
            "architecture": {
                "family": "visual_spatial_mlp",
                "hidden_size": self.hidden_size,
                "cell_structure": True,
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
            "neural_table_cell_classifier": True,
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
        recognizer = VishnuNeuralTableCellRecognizer.from_model(model)
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
            "cell_f1": _macro_f1(truth, predictions),
            "cell_accuracy": sum(int(a == b) for a, b in zip(truth, predictions))
            / max(1, len(truth)),
            "evaluation_records": float(len(truth)),
            "neural_table_cell_classifier": 1.0,
        }


class VishnuNeuralTableCellRecognizer:
    def __init__(self, checkpoint_ref: str | Path):
        self._load(json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8")))

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "VishnuNeuralTableCellRecognizer":
        value = cls.__new__(cls)
        value._load(model)
        return value

    def _load(self, model: dict[str, Any]) -> None:
        if model.get("model_type") != "vishnu-stage15-neural-table-cell":
            raise ValueError("unsupported Stage 15 Vishnu neural table artifact")
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
        vector = Stage15TableCellVectorizer.features(payload).reshape(1, -1)
        probabilities = VishnuNeuralTableCellTrainer._predict_arrays(
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
        return {
            "label": raw_label if accepted else "unknown",
            "raw_label": raw_label,
            "confidence": confidence,
            "accepted": accepted,
            "rejection_reason": None if accepted else "low_confidence",
        }


class Stage15TableCoordinator:
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
        subtask: str = "table_cells",
        languages: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.feedback.approved_samples(
            ContentModelTask.TABLE, subtask=subtask, languages=languages
        )
        prepared: list[dict[str, Any]] = []
        for row in rows:
            original = row.get("input")
            if not isinstance(original, dict) or not original.get("image_png_b64"):
                raise Stage15PolicyError("Stage 15 table feedback requires image_png_b64")
            label = str(row.get("label") or "")
            if label not in TABLE_CELL_LABELS:
                raise Stage15PolicyError(f"unsupported Stage 15 table label: {label}")
            prepared.append(
                {
                    **row,
                    "input": dict(original),
                    "provenance": {
                        **dict(row.get("provenance") or {}),
                        "stage15_table_structure": True,
                        "neural_table_cell_classifier": True,
                    },
                }
            )
        return prepared

    def train_candidate(
        self,
        *,
        subtask: str = "table_cells",
        languages: Iterable[str] | None = None,
        dataset_name: str | None = None,
    ) -> dict[str, Any]:
        return self.content_models.train(
            ContentModelTask.TABLE,
            self._prepare_samples(subtask=subtask, languages=languages),
            VishnuNeuralTableCellTrainer(),
            dataset_name=dataset_name or "vishnu-stage15-neural-table-cells",
            metadata={
                "stage": 15,
                "subtask": subtask,
                "labels_supported": list(TABLE_CELL_LABELS),
                "neural_table_cell_classifier": True,
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
        baseline: TableCellBaseline,
        min_cell_f1_delta: float = 0.0,
    ) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        if model["task"] != ContentModelTask.TABLE.value or model["status"] != "candidate":
            raise ValueError("Stage 15 table shadow qualification requires a table candidate")
        snapshot = self._snapshot_for(model)
        rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path)
        if not rows:
            raise ValueError("Stage 15 table shadow qualification requires a held-out split")
        candidate = VishnuNeuralTableCellRecognizer(model["checkpoint_ref"])
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
        candidate_metrics = {"cell_f1": candidate_f1}
        baseline_metrics = {"cell_f1": baseline_f1}
        reasons = list(
            self.content_models.evaluator.evaluate_metrics(
                ContentModelTask.TABLE, candidate_metrics
            ).reasons
        )
        delta = candidate_f1 - baseline_f1
        if delta < float(min_cell_f1_delta):
            reasons.append("candidate_table_cell_f1_delta_below_requirement")
        created_at = _now()
        deltas = {"cell_f1": delta}
        payload = {
            "model_id": model_id,
            "task": ContentModelTask.TABLE.value,
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
            task=ContentModelTask.TABLE.value,
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
                "Stage 15 table model requires successful shadow qualification before owner approval"
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
                "Stage 15 table model requires successful shadow qualification before activation"
            )
        return self.content_models.registry.activate(
            model_id, owner_authorized=owner_authorized, actor=actor
        )
