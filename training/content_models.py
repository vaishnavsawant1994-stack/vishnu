from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Protocol
from uuid import uuid4

from training.artifact_store import FilesystemModelArtifactStore, ModelArtifactManifest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w@.+#/-]{2,}", str(text or "").casefold(), flags=re.UNICODE)[:10000]


class ContentModelTask(StrEnum):
    OCR = "ocr"
    HANDWRITING = "handwriting"
    LAYOUT = "layout"
    TABLE = "table"
    DOCUMENT_CLASSIFICATION = "document_classification"
    MULTIMODAL_VISUAL = "multimodal_visual"


class ContentModelStatus(StrEnum):
    TRAINED = "trained"
    EVALUATION_FAILED = "evaluation_failed"
    CANDIDATE = "candidate"
    OWNER_APPROVED = "owner_approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ContentDatasetSnapshot:
    snapshot_id: str
    task: ContentModelTask
    created_at: str
    root: str
    train_path: str
    validation_path: str
    test_path: str
    manifest_path: str
    records: int
    sha256: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["task"] = self.task.value
        value["contains_hidden_chain_of_thought"] = False
        value["automatic_publication"] = False
        return value


class ContentDatasetBuilder:
    """Build immutable, provenance-preserving datasets for specialized Vishnu models."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _split(source_fingerprint: str) -> str:
        bucket = int(hashlib.sha256(source_fingerprint.encode()).hexdigest()[:8], 16) % 100
        return "train" if bucket < 80 else "validation" if bucket < 90 else "test"

    def build(
        self,
        task: ContentModelTask | str,
        samples: Iterable[dict[str, Any]],
        *,
        dataset_name: str | None = None,
    ) -> ContentDatasetSnapshot:
        task = ContentModelTask(str(task))
        rows = []
        for sample in samples:
            source = str(sample.get("source_fingerprint") or "").strip()
            if not source:
                raise ValueError("content-model sample requires source_fingerprint")
            value = {
                "id": str(sample.get("id") or uuid4()),
                "input": sample.get("input"),
                "label": sample.get("label"),
                "source_fingerprint": source,
                "provenance": dict(sample.get("provenance") or {}),
                "consent_basis": str(sample.get("consent_basis") or "owner_provided"),
            }
            if value["input"] in (None, "") or value["label"] in (None, ""):
                raise ValueError("content-model sample requires input and label")
            rows.append(value)
        if len(rows) < 3:
            raise ValueError("content-model dataset requires at least 3 samples")
        rows.sort(key=lambda item: item["id"])
        digest = hashlib.sha256("".join(_canonical(item) + "\n" for item in rows).encode()).hexdigest()
        snapshot_id = f"content-ds-{task.value}-{digest[:20]}"
        root = self.root / snapshot_id
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if payload.get("dataset_sha256") != digest:
                raise RuntimeError("immutable content dataset digest mismatch")
            return ContentDatasetSnapshot(
                snapshot_id=snapshot_id,
                task=task,
                created_at=payload["created_at"],
                root=str(root),
                train_path=str(root / "train.jsonl"),
                validation_path=str(root / "validation.jsonl"),
                test_path=str(root / "test.jsonl"),
                manifest_path=str(manifest_path),
                records=len(rows),
                sha256=digest,
            )
        root.mkdir(parents=True, exist_ok=True)
        splits = {"train": [], "validation": [], "test": []}
        for row in rows:
            splits[self._split(row["source_fingerprint"])].append(row)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in splits["train"]:
            groups[row["source_fingerprint"]].append(row)
        ordered = sorted(groups.items())
        if len(ordered) >= 3 and not splits["validation"]:
            key, moved = ordered.pop()
            splits["validation"].extend(moved)
            splits["train"] = [r for r in splits["train"] if r["source_fingerprint"] != key]
        if len(ordered) >= 2 and not splits["test"]:
            key, moved = ordered.pop()
            splits["test"].extend(moved)
            splits["train"] = [r for r in splits["train"] if r["source_fingerprint"] != key]
        for name, values in splits.items():
            (root / f"{name}.jsonl").write_text(
                "".join(_canonical(item) + "\n" for item in values), encoding="utf-8"
            )
        manifest = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "task": task.value,
            "dataset_name": str(dataset_name or f"vishnu-{task.value}"),
            "created_at": _now(),
            "records": len(rows),
            "split_records": {key: len(value) for key, value in splits.items()},
            "dataset_sha256": digest,
            "split_strategy": "source_fingerprint_grouped_80_10_10",
            "contains_hidden_chain_of_thought": False,
            "automatic_publication": False,
            "immutable": True,
        }
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        return ContentDatasetSnapshot(
            snapshot_id,
            task,
            manifest["created_at"],
            str(root),
            str(root / "train.jsonl"),
            str(root / "validation.jsonl"),
            str(root / "test.jsonl"),
            str(manifest_path),
            len(rows),
            digest,
        )


@dataclass(frozen=True)
class ContentEvaluation:
    task: ContentModelTask
    passed: bool
    metrics: dict[str, float]
    reasons: tuple[str, ...]

    def public(self) -> dict[str, Any]:
        return {
            "task": self.task.value,
            "passed": self.passed,
            "metrics": self.metrics,
            "reasons": list(self.reasons),
        }


class ContentModelEvaluator:
    """Task-specific fail-closed evaluation thresholds."""

    RULES = {
        ContentModelTask.OCR: {"max": {"cer": 0.15}, "min": {"word_accuracy": 0.85}},
        ContentModelTask.HANDWRITING: {"max": {"cer": 0.25}, "min": {"word_accuracy": 0.70}},
        ContentModelTask.LAYOUT: {"min": {"f1": 0.85}},
        ContentModelTask.TABLE: {"min": {"cell_f1": 0.85}},
        ContentModelTask.DOCUMENT_CLASSIFICATION: {"min": {"accuracy": 0.85}},
        ContentModelTask.MULTIMODAL_VISUAL: {"min": {"accuracy": 0.85}},
    }

    def evaluate_metrics(self, task: ContentModelTask | str, metrics: dict[str, Any]) -> ContentEvaluation:
        task = ContentModelTask(str(task))
        clean = {str(key): float(value) for key, value in metrics.items() if isinstance(value, (int, float))}
        reasons = []
        rule = self.RULES[task]
        for key, floor in rule.get("min", {}).items():
            if key not in clean:
                reasons.append(f"missing_metric:{key}")
            elif clean[key] < floor:
                reasons.append(f"{key}_below_{floor}")
        for key, ceiling in rule.get("max", {}).items():
            if key not in clean:
                reasons.append(f"missing_metric:{key}")
            elif clean[key] > ceiling:
                reasons.append(f"{key}_above_{ceiling}")
        return ContentEvaluation(task, not reasons, clean, tuple(reasons))


class ContentTrainerBackend(Protocol):
    backend_id: str
    task: ContentModelTask

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]: ...


class NaiveBayesDocumentClassifierTrainer:
    """A real, locally trained Vishnu-owned document classifier with no ML dependency."""

    backend_id = "vishnu-stdlib-naive-bayes"
    task = ContentModelTask.DOCUMENT_CLASSIFICATION

    @staticmethod
    def _read(path: str) -> list[dict[str, Any]]:
        file = Path(path)
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]

    @staticmethod
    def _predict(model: dict[str, Any], text: str) -> str:
        tokens = _tokens(text)
        vocabulary = max(1, int(model["vocabulary_size"]))
        best = None
        for label, data in model["labels"].items():
            score = math.log(float(data["prior"]))
            denominator = int(data["token_total"]) + vocabulary
            counts = data["tokens"]
            for token in tokens:
                score += math.log((int(counts.get(token, 0)) + 1) / denominator)
            if best is None or score > best[0]:
                best = (score, label)
        if best is None:
            raise RuntimeError("classifier has no labels")
        return best[1]

    def train(self, snapshot: ContentDatasetSnapshot, output_dir: Path) -> tuple[Path, dict[str, float]]:
        if snapshot.task is not self.task:
            raise ValueError("document classifier trainer received wrong task")
        rows = self._read(snapshot.train_path)
        if not rows:
            raise ValueError("document classifier train split is empty")
        label_docs, token_counts, totals, vocabulary = Counter(), defaultdict(Counter), Counter(), set()
        for row in rows:
            label = str(row["label"])
            tokens = _tokens(str(row["input"]))
            label_docs[label] += 1
            token_counts[label].update(tokens)
            totals[label] += len(tokens)
            vocabulary.update(tokens)
        model = {
            "schema_version": 1,
            "model_type": "vishnu-multinomial-naive-bayes",
            "task": self.task.value,
            "dataset_snapshot_id": snapshot.snapshot_id,
            "dataset_sha256": snapshot.sha256,
            "vocabulary_size": len(vocabulary),
            "labels": {},
            "created_at": _now(),
        }
        for label in sorted(label_docs):
            model["labels"][label] = {
                "prior": label_docs[label] / sum(label_docs.values()),
                "token_total": totals[label],
                "tokens": dict(token_counts[label]),
            }
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "model.json"
        path.write_text(json.dumps(model, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        eval_rows = self._read(snapshot.validation_path) or self._read(snapshot.test_path) or rows
        correct = sum(self._predict(model, str(row["input"])) == str(row["label"]) for row in eval_rows)
        return output_dir, {"accuracy": correct / len(eval_rows), "evaluation_records": float(len(eval_rows))}


class ContentModelRegistry:
    """Owner-governed registry for Vishnu-owned specialized content model artifacts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_models(
                    model_id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    backend_id TEXT NOT NULL,
                    dataset_snapshot_id TEXT NOT NULL,
                    dataset_sha256 TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    checkpoint_ref TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    owner_approved_by TEXT,
                    activated_at TEXT,
                    parent_model_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_content_models_task_status
                    ON content_models(task,status,updated_at);
                """
            )

    def register(
        self,
        *,
        task: ContentModelTask,
        backend_id: str,
        snapshot: ContentDatasetSnapshot,
        artifact: ModelArtifactManifest,
        evaluation: ContentEvaluation,
        metrics: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        model_id = f"vishnu-{task.value}-{artifact.artifact_sha256[:16]}"
        status = ContentModelStatus.CANDIDATE.value if evaluation.passed else ContentModelStatus.EVALUATION_FAILED.value
        now = _now()
        with self._con() as con:
            con.execute(
                """INSERT OR REPLACE INTO content_models VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    model_id,
                    task.value,
                    backend_id,
                    snapshot.snapshot_id,
                    snapshot.sha256,
                    artifact.artifact_id,
                    artifact.artifact_sha256,
                    artifact.checkpoint_ref,
                    _canonical(metrics),
                    _canonical(evaluation.public()),
                    status,
                    now,
                    now,
                    None,
                    None,
                    None,
                    _canonical(metadata or {}),
                ),
            )
        return self.get(model_id)

    def get(self, model_id: str) -> dict | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM content_models WHERE model_id=?", (model_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metrics"] = json.loads(item.pop("metrics_json"))
        item["evaluation"] = json.loads(item.pop("evaluation_json"))
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def approve(self, model_id: str, *, owner_id: str) -> dict:
        owner_id = str(owner_id).strip()
        if not owner_id:
            raise ValueError("owner_id is required")
        current = self.get(model_id)
        if not current:
            raise KeyError(model_id)
        if current["status"] != ContentModelStatus.CANDIDATE.value:
            raise ValueError("content model must pass evaluation before owner approval")
        with self._con() as con:
            con.execute(
                "UPDATE content_models SET status=?,owner_approved_by=?,updated_at=? WHERE model_id=?",
                (ContentModelStatus.OWNER_APPROVED.value, owner_id, _now(), model_id),
            )
        return self.get(model_id)

    def activate(self, model_id: str, *, owner_authorized: bool, actor: str = "release_controller") -> dict:
        if not owner_authorized:
            raise PermissionError("content model activation requires explicit owner authorization")
        current = self.get(model_id)
        if not current:
            raise KeyError(model_id)
        if current["status"] != ContentModelStatus.OWNER_APPROVED.value:
            raise ValueError("content model must be owner approved before activation")
        now = _now()
        with self._con() as con:
            previous = con.execute(
                "SELECT model_id FROM content_models WHERE task=? AND status=? ORDER BY updated_at DESC LIMIT 1",
                (current["task"], ContentModelStatus.ACTIVE.value),
            ).fetchone()
            parent = None
            if previous and previous["model_id"] != model_id:
                parent = previous["model_id"]
                con.execute(
                    "UPDATE content_models SET status=?,updated_at=? WHERE model_id=?",
                    (ContentModelStatus.SUPERSEDED.value, now, parent),
                )
            metadata = {**current["metadata"], "activation_actor": str(actor or "release_controller")}
            con.execute(
                "UPDATE content_models SET status=?,activated_at=?,updated_at=?,parent_model_id=?,metadata_json=? WHERE model_id=?",
                (ContentModelStatus.ACTIVE.value, now, now, parent, _canonical(metadata), model_id),
            )
        return self.get(model_id)

    def active(self, task: ContentModelTask | str) -> dict | None:
        task = ContentModelTask(str(task))
        with self._con() as con:
            row = con.execute(
                "SELECT model_id FROM content_models WHERE task=? AND status=? ORDER BY updated_at DESC LIMIT 1",
                (task.value, ContentModelStatus.ACTIVE.value),
            ).fetchone()
        return self.get(row["model_id"]) if row else None


class VishnuDocumentClassifier:
    def __init__(self, checkpoint_ref: str | Path):
        self.model = json.loads((Path(checkpoint_ref) / "model.json").read_text(encoding="utf-8"))
        if self.model.get("model_type") != "vishnu-multinomial-naive-bayes":
            raise ValueError("unsupported Vishnu classifier artifact")

    def predict(self, text: str) -> str:
        return NaiveBayesDocumentClassifierTrainer._predict(self.model, text)


class ContentModelCoordinator:
    """Dataset -> train -> evaluate -> immutable artifact -> candidate registry boundary."""

    def __init__(
        self,
        *,
        datasets_root: str | Path,
        artifacts_root: str | Path,
        registry_path: str | Path,
        artifact_persistent: bool = False,
    ):
        self.datasets = ContentDatasetBuilder(datasets_root)
        self.artifacts = FilesystemModelArtifactStore(artifacts_root, persistent=artifact_persistent)
        self.registry = ContentModelRegistry(registry_path)
        self.evaluator = ContentModelEvaluator()

    def train(
        self,
        task: ContentModelTask | str,
        samples: Iterable[dict[str, Any]],
        backend: ContentTrainerBackend,
        *,
        dataset_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        task = ContentModelTask(str(task))
        if backend.task is not task:
            raise ValueError("trainer task does not match requested content model task")
        snapshot = self.datasets.build(task, samples, dataset_name=dataset_name)
        output = Path(self.artifacts.root) / "training" / f"{snapshot.snapshot_id}-{uuid4().hex[:8]}"
        checkpoint, metrics = backend.train(snapshot, output)
        evaluation = self.evaluator.evaluate_metrics(task, metrics)
        artifact = self.artifacts.stage(
            checkpoint,
            metadata={
                "task": task.value,
                "backend_id": backend.backend_id,
                "dataset_snapshot_id": snapshot.snapshot_id,
                "dataset_sha256": snapshot.sha256,
                "vishnu_owned_training_run": True,
            },
        )
        return self.registry.register(
            task=task,
            backend_id=backend.backend_id,
            snapshot=snapshot,
            artifact=artifact,
            evaluation=evaluation,
            metrics=metrics,
            metadata=metadata,
        )
