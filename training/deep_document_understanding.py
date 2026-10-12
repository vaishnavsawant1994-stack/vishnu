from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Protocol

from training.content_models import (
    ContentDatasetSnapshot,
    ContentModelCoordinator,
    ContentModelTask,
)
from training.continuous_content_models import (
    GovernedContentFeedbackStore,
    ModelCycleEvidence,
    ModelCycleEvidenceStore,
    _canonical,
    _now,
    _read_jsonl,
)


class Stage16PolicyError(ValueError):
    pass


STAGE16_SUBTASKS = (
    "stage16_claim_type",
    "stage16_document_type",
    "stage16_entity_type",
    "stage16_field_type",
    "stage16_qa_support",
    "stage16_relation_type",
    "stage16_table_role",
)

STAGE16_MIN_F1 = {
    "stage16_document_type": 0.85,
    "stage16_entity_type": 0.85,
    "stage16_field_type": 0.85,
    "stage16_relation_type": 0.80,
    "stage16_claim_type": 0.80,
    "stage16_table_role": 0.80,
    "stage16_qa_support": 0.90,
}


def _tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        text = " ".join(str(value.get(key) or "") for key in ("text", "context", "candidate", "question"))
    else:
        text = str(value or "")
    return re.findall(r"[\w@.+#/%-]{2,}", text.casefold(), flags=re.UNICODE)[:12000]


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


class VishnuStage16SemanticTrainer:
    """Locally trained multi-head multinomial model for Stage 16 semantic subtasks."""

    task = ContentModelTask.DOCUMENT_CLASSIFICATION
    backend_id = "vishnu-stage16-multihead-semantic-nb-v1"

    @staticmethod
    def _head_for(row: dict[str, Any]) -> str:
        payload = row.get("input") or {}
        subtask = str(payload.get("subtask") or "") if isinstance(payload, dict) else ""
        if subtask not in STAGE16_SUBTASKS:
            raise Stage16PolicyError(f"unsupported Stage 16 semantic subtask: {subtask}")
        return subtask

    @staticmethod
    def _train_head(rows: list[dict[str, Any]]) -> dict[str, Any]:
        label_docs: Counter[str] = Counter()
        token_counts: dict[str, Counter[str]] = defaultdict(Counter)
        totals: Counter[str] = Counter()
        vocabulary: set[str] = set()
        for row in rows:
            label = str(row.get("label") or "").strip()
            if not label:
                raise Stage16PolicyError("Stage 16 semantic sample requires a label")
            tokens = _tokens(row.get("input"))
            label_docs[label] += 1
            token_counts[label].update(tokens)
            totals[label] += len(tokens)
            vocabulary.update(tokens)
        if len(label_docs) < 2:
            raise Stage16PolicyError("each Stage 16 semantic head requires at least two labels")
        total_docs = max(1, sum(label_docs.values()))
        return {
            "vocabulary_size": max(1, len(vocabulary)),
            "labels": {
                label: {
                    "prior": label_docs[label] / total_docs,
                    "token_total": int(totals[label]),
                    "tokens": dict(token_counts[label]),
                }
                for label in sorted(label_docs)
            },
        }

    @staticmethod
    def _scores(head: dict[str, Any], value: Any) -> list[tuple[float, str]]:
        tokens = _tokens(value)
        vocabulary = max(1, int(head.get("vocabulary_size") or 1))
        values: list[tuple[float, str]] = []
        for label, data in dict(head.get("labels") or {}).items():
            score = math.log(max(1e-12, float(data.get("prior") or 0.0)))
            denominator = int(data.get("token_total") or 0) + vocabulary
            counts = dict(data.get("tokens") or {})
            for token in tokens:
                score += math.log((int(counts.get(token, 0)) + 1) / max(1, denominator))
            values.append((score, str(label)))
        return sorted(values, key=lambda item: (-item[0], item[1]))

    @classmethod
    def _predict(cls, head: dict[str, Any], value: Any) -> dict[str, Any]:
        scores = cls._scores(head, value)
        if not scores:
            raise Stage16PolicyError("Stage 16 semantic head has no labels")
        top = scores[0][0]
        exp = [math.exp(max(-60.0, min(0.0, score - top))) for score, _ in scores]
        denominator = max(1e-12, sum(exp))
        alternatives = [
            {"label": label, "confidence": weight / denominator}
            for weight, (_, label) in zip(exp, scores)
        ]
        return {
            "label": alternatives[0]["label"],
            "confidence": float(alternatives[0]["confidence"]),
            "alternatives": alternatives[:3],
        }

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("Stage 16 semantic trainer requires document classification authority")
        rows = _read_jsonl(snapshot.train_path)
        if not rows:
            raise Stage16PolicyError("Stage 16 semantic train split is empty")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[self._head_for(row)].append(row)
        missing = sorted(set(STAGE16_SUBTASKS) - set(grouped))
        if missing:
            raise Stage16PolicyError(f"Stage 16 training is missing semantic heads: {missing}")
        heads = {subtask: self._train_head(grouped[subtask]) for subtask in STAGE16_SUBTASKS}
        model = {
            "schema_version": 1,
            "model_type": "vishnu-stage16-multihead-document-semantics",
            "task": ContentModelTask.DOCUMENT_CLASSIFICATION.value,
            "backend_id": self.backend_id,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "heads": heads,
            "subtasks": list(STAGE16_SUBTASKS),
            "trained_by_vishnu": True,
            "grounded_document_reasoning": True,
            "foundation_model": False,
            "created_at": _now(),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.json").write_text(json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        evaluation_rows = _read_jsonl(snapshot.validation_path) or _read_jsonl(snapshot.test_path)
        if not evaluation_rows:
            raise Stage16PolicyError("Stage 16 semantic model requires a held-out split")
        expected: list[str] = []
        predicted: list[str] = []
        by_head_truth: dict[str, list[str]] = defaultdict(list)
        by_head_pred: dict[str, list[str]] = defaultdict(list)
        for row in evaluation_rows:
            head = self._head_for(row)
            truth = str(row.get("label") or "")
            guess = str(self._predict(heads[head], row.get("input"))["label"])
            expected.append(truth)
            predicted.append(guess)
            by_head_truth[head].append(truth)
            by_head_pred[head].append(guess)
        metrics: dict[str, float] = {
            "accuracy": sum(int(a == b) for a, b in zip(expected, predicted)) / max(1, len(expected)),
            "macro_f1": _macro_f1(expected, predicted),
            "evaluation_records": float(len(expected)),
        }
        for subtask in STAGE16_SUBTASKS:
            truth = by_head_truth.get(subtask, [])
            guesses = by_head_pred.get(subtask, [])
            metrics[f"{subtask}_records"] = float(len(truth))
            metrics[f"{subtask}_f1"] = _macro_f1(truth, guesses) if truth else 0.0
            metrics[f"{subtask}_accuracy"] = sum(int(a == b) for a, b in zip(truth, guesses)) / max(1, len(truth)) if truth else 0.0
        return output_dir, metrics


class VishnuStage16SemanticModel:
    def __init__(self, checkpoint_ref: str | Path):
        self.model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-stage16-multihead-document-semantics":
            raise ValueError("unsupported Stage 16 semantic artifact")
        self.heads = dict(self.model.get("heads") or {})

    def predict(self, subtask: str, value: Any, *, reject_below: float = 0.0) -> dict[str, Any]:
        subtask = str(subtask)
        if subtask not in self.heads:
            raise Stage16PolicyError(f"Stage 16 artifact has no semantic head: {subtask}")
        result = VishnuStage16SemanticTrainer._predict(self.heads[subtask], value)
        threshold = max(0.0, min(1.0, float(reject_below)))
        accepted = float(result["confidence"]) >= threshold
        return {
            **result,
            "raw_label": result["label"],
            "label": result["label"] if accepted else "unknown",
            "accepted": accepted,
            "rejection_reason": None if accepted else "low_confidence",
        }


class SemanticBaseline(Protocol):
    baseline_id: str

    def predict(self, subtask: str, value: Any) -> str: ...


class Stage16DocumentUnderstandingCoordinator:
    """Stage 12 feedback -> Stage 9 registry -> shadow -> owner -> release-controller lifecycle."""

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

    def _prepare_samples(self, *, languages: Iterable[str] | None = None) -> list[dict[str, Any]]:
        rows = self.feedback.approved_samples(ContentModelTask.DOCUMENT_CLASSIFICATION, languages=languages)
        prepared: list[dict[str, Any]] = []
        for row in rows:
            provenance = dict(row.get("provenance") or {})
            subtask = str(provenance.get("subtask") or "")
            if subtask not in STAGE16_SUBTASKS:
                continue
            original = row.get("input")
            if isinstance(original, dict):
                payload = dict(original)
            else:
                payload = {"text": str(original or "")}
            payload["subtask"] = subtask
            if not _tokens(payload):
                raise Stage16PolicyError("Stage 16 semantic feedback requires text/context tokens")
            prepared.append({
                **row,
                "input": payload,
                "provenance": {
                    **provenance,
                    "stage16_deep_document_understanding": True,
                    "semantic_subtask": subtask,
                },
            })
        present = {str((row.get("input") or {}).get("subtask") or "") for row in prepared}
        missing = sorted(set(STAGE16_SUBTASKS) - present)
        if missing:
            raise Stage16PolicyError(f"Stage 16 approved feedback is missing semantic subtasks: {missing}")
        return prepared

    def train_candidate(self, *, languages: Iterable[str] | None = None, dataset_name: str | None = None) -> dict[str, Any]:
        samples = self._prepare_samples(languages=languages)
        return self.content_models.train(
            ContentModelTask.DOCUMENT_CLASSIFICATION,
            samples,
            VishnuStage16SemanticTrainer(),
            dataset_name=dataset_name or "vishnu-stage16-deep-document-semantics",
            metadata={
                "stage": 16,
                "subtasks": list(STAGE16_SUBTASKS),
                "deep_document_understanding": True,
                "cross_page_context": True,
                "semantic_tables": True,
                "claims_and_references": True,
                "grounded_document_qa": True,
                "semantic_document_comparison": True,
                "multi_document_linking": True,
                "trained_by_vishnu": True,
                "foundation_model": False,
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

    def shadow_qualify(self, model_id: str, *, baseline: SemanticBaseline, min_accuracy_delta: float = 0.0) -> dict[str, Any]:
        model = self.content_models.registry.get(model_id)
        if not model:
            raise KeyError(model_id)
        if model["task"] != ContentModelTask.DOCUMENT_CLASSIFICATION.value or int(dict(model.get("metadata") or {}).get("stage") or 0) != 16:
            raise ValueError("Stage 16 shadow qualification requires a Stage 16 semantic candidate")
        if model["status"] != "candidate":
            raise ValueError("Stage 16 shadow qualification requires candidate status")
        snapshot = self._snapshot_for(model)
        rows = _read_jsonl(snapshot.test_path) or _read_jsonl(snapshot.validation_path)
        if not rows:
            raise Stage16PolicyError("Stage 16 shadow qualification requires held-out records")
        candidate = VishnuStage16SemanticModel(model["checkpoint_ref"])
        truth: list[str] = []
        guesses: list[str] = []
        baseline_guesses: list[str] = []
        by_head_truth: dict[str, list[str]] = defaultdict(list)
        by_head_guess: dict[str, list[str]] = defaultdict(list)
        reasons: list[str] = []
        for row in rows:
            payload = dict(row.get("input") or {})
            subtask = str(payload.get("subtask") or "")
            if subtask not in STAGE16_SUBTASKS:
                raise Stage16PolicyError(f"held-out row has unsupported Stage 16 subtask: {subtask}")
            expected = str(row.get("label") or "")
            predicted = str(candidate.predict(subtask, payload, reject_below=0.0)["label"])
            baseline_value = str(baseline.predict(subtask, payload) or "unknown")
            truth.append(expected)
            guesses.append(predicted)
            baseline_guesses.append(baseline_value)
            by_head_truth[subtask].append(expected)
            by_head_guess[subtask].append(predicted)
        candidate_accuracy = sum(int(a == b) for a, b in zip(truth, guesses)) / max(1, len(truth))
        baseline_accuracy = sum(int(a == b) for a, b in zip(truth, baseline_guesses)) / max(1, len(truth))
        if candidate_accuracy < 0.85:
            reasons.append("stage16_accuracy_below_0.85")
        if candidate_accuracy - baseline_accuracy < float(min_accuracy_delta):
            reasons.append("stage16_accuracy_delta_below_requirement")
        candidate_metrics: dict[str, float] = {
            "accuracy": candidate_accuracy,
            "macro_f1": _macro_f1(truth, guesses),
        }
        for subtask, floor in STAGE16_MIN_F1.items():
            head_truth = by_head_truth.get(subtask, [])
            head_guess = by_head_guess.get(subtask, [])
            if not head_truth:
                reasons.append(f"missing_heldout_head:{subtask}")
                candidate_metrics[f"{subtask}_f1"] = 0.0
                continue
            value = _macro_f1(head_truth, head_guess)
            candidate_metrics[f"{subtask}_f1"] = value
            if value < floor:
                reasons.append(f"{subtask}_f1_below_{floor}")
        baseline_metrics = {
            "accuracy": baseline_accuracy,
            "macro_f1": _macro_f1(truth, baseline_guesses),
        }
        created_at = _now()
        deltas = {
            "accuracy": candidate_accuracy - baseline_accuracy,
            "macro_f1": candidate_metrics["macro_f1"] - baseline_metrics["macro_f1"],
        }
        payload = {
            "model_id": model_id,
            "task": ContentModelTask.DOCUMENT_CLASSIFICATION.value,
            "stage": 16,
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
            task="stage16_deep_document_understanding",
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
            raise ValueError("Stage 16 semantic model requires successful shadow qualification before owner approval")
        return self.content_models.registry.approve(model_id, owner_id=owner_id)

    def activate(self, model_id: str, *, owner_authorized: bool, actor: str = "release_controller") -> dict[str, Any]:
        evidence = self.evidence.latest(model_id)
        if not evidence or evidence.get("passed") is not True:
            raise ValueError("Stage 16 semantic model requires successful shadow qualification before activation")
        return self.content_models.registry.activate(model_id, owner_authorized=owner_authorized, actor=actor)

    def active_model(self) -> VishnuStage16SemanticModel:
        model = self.content_models.registry.active(ContentModelTask.DOCUMENT_CLASSIFICATION)
        if not model or int(dict(model.get("metadata") or {}).get("stage") or 0) < 16:
            raise Stage16PolicyError("no active Stage 16 semantic model")
        return VishnuStage16SemanticModel(model["checkpoint_ref"])
