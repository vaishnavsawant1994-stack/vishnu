from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Protocol
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


class TrainingMethod(StrEnum):
    LORA = 'lora'
    QLORA = 'qlora'
    FULL = 'full'


class TrainingJobStatus(StrEnum):
    QUEUED = 'queued'
    PREPARING = 'preparing'
    RUNNING = 'running'
    AWAITING_EVALUATION = 'awaiting_evaluation'
    PROMOTION_READY = 'promotion_ready'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class TrainedModelStatus(StrEnum):
    TRAINED = 'trained'
    EVALUATION_FAILED = 'evaluation_failed'
    PROMOTION_READY = 'promotion_ready'
    OWNER_APPROVED = 'owner_approved'
    ACTIVE = 'active'
    REJECTED = 'rejected'


@dataclass(frozen=True)
class AutoTrainingSettings:
    enabled: bool = False
    backend_id: str = 'local_peft'
    base_model: str = ''
    method: TrainingMethod = TrainingMethod.LORA
    min_approved_records: int = 100
    interval_seconds: int = 24 * 3600
    minimum_quality_score: float = .80
    minimum_improvement: float = 0.0
    require_safety_evaluation: bool = True
    require_shadow_evaluation: bool = True
    max_training_records: int = 10000

    def __post_init__(self) -> None:
        if not 10 <= int(self.min_approved_records) <= 1_000_000:
            raise ValueError('min_approved_records must be between 10 and 1000000')
        if not 3600 <= int(self.interval_seconds) <= 30 * 24 * 3600:
            raise ValueError('interval_seconds must be between 3600 and 2592000')
        if not 0 <= float(self.minimum_quality_score) <= 1:
            raise ValueError('minimum_quality_score must be between 0 and 1')
        if not 0 <= float(self.minimum_improvement) <= 1:
            raise ValueError('minimum_improvement must be between 0 and 1')
        if not 10 <= int(self.max_training_records) <= 1_000_000:
            raise ValueError('max_training_records must be between 10 and 1000000')

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value['method'] = self.method.value
        value['production_activation_automatic'] = False
        value['public_dataset_upload_automatic'] = False
        return value


class TrainingSettingsService:
    """Owner-controlled training settings stored separately from conversation data."""

    def __init__(self, path: str | Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        self._lock = threading.RLock()

    def snapshot(self) -> AutoTrainingSettings:
        with self._lock:
            raw: dict[str, Any] = {}
            if self.path.exists():
                try:
                    value = json.loads(self.path.read_text(encoding='utf-8'))
                    if isinstance(value, dict):
                        raw = value
                except Exception:
                    raw = {}
        try:
            method = TrainingMethod(str(raw.get('method', TrainingMethod.LORA.value)))
        except ValueError:
            method = TrainingMethod.LORA
        try:
            return AutoTrainingSettings(
                enabled=bool(raw.get('enabled', False)),
                backend_id=str(raw.get('backend_id', 'local_peft')).strip() or 'local_peft',
                base_model=str(raw.get('base_model', '')).strip(),
                method=method,
                min_approved_records=int(raw.get('min_approved_records', 100)),
                interval_seconds=int(raw.get('interval_seconds', 24 * 3600)),
                minimum_quality_score=float(raw.get('minimum_quality_score', .80)),
                minimum_improvement=float(raw.get('minimum_improvement', 0.0)),
                require_safety_evaluation=bool(raw.get('require_safety_evaluation', True)),
                require_shadow_evaluation=bool(raw.get('require_shadow_evaluation', True)),
                max_training_records=int(raw.get('max_training_records', 10000)),
            )
        except (TypeError, ValueError):
            return AutoTrainingSettings()

    def update(self, **values: Any) -> AutoTrainingSettings:
        allowed = set(AutoTrainingSettings.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'unsupported training setting(s): {sorted(unknown)}')
        current = self.snapshot().public()
        current.pop('production_activation_automatic', None)
        current.pop('public_dataset_upload_automatic', None)
        current.update(values)
        if 'method' in current:
            current['method'] = TrainingMethod(str(current['method']).strip().lower())
        candidate = AutoTrainingSettings(**current)
        payload = candidate.public()
        payload.pop('production_activation_automatic', None)
        payload.pop('public_dataset_upload_automatic', None)
        with self._lock:
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding='utf-8')
            temp.replace(self.path)
        if self.events is not None:
            self.events.emit('training.settings_updated', **candidate.public())
        return candidate


@dataclass(frozen=True)
class TrainingDatasetSnapshot:
    snapshot_id: str
    created_at: str
    dataset_name: str
    root: str
    train_path: str
    validation_path: str
    test_path: str
    manifest_path: str
    records: int
    train_records: int
    validation_records: int
    test_records: int
    sha256: str

    def public(self) -> dict[str, Any]:
        return {**asdict(self), 'contains_hidden_chain_of_thought': False, 'automatic_publication': False}


class TrainingDatasetSnapshotBuilder:
    """Create deterministic, source-grouped train/validation/test snapshots."""

    def __init__(self, store, root: str | Path) -> None:
        self.store = store
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _record(candidate) -> dict[str, Any]:
        return {
            'id': candidate.candidate_id,
            'instruction': candidate.prompt,
            'response': candidate.response,
            'source_type': candidate.source_type,
            'source_fingerprint': candidate.source_fingerprint,
            'provenance': candidate.provenance,
            'consent_basis': candidate.consent_basis,
            'privacy_level': candidate.privacy_level.value,
            'provider_id': candidate.provider_id,
            'model_id': candidate.model_id,
            'verifier_score': candidate.verifier_score,
        }

    @staticmethod
    def _split(source_fingerprint: str) -> str:
        bucket = int(sha256(source_fingerprint.encode('utf-8')).hexdigest()[:8], 16) % 100
        if bucket < 80:
            return 'train'
        if bucket < 90:
            return 'validation'
        return 'test'

    def build(self, *, dataset_name: str = 'vishnu-general', min_records: int = 10, limit: int = 10000) -> TrainingDatasetSnapshot:
        rows = self.store.approved(limit=limit)
        if len(rows) < int(min_records):
            raise ValueError(f'not enough approved training records: {len(rows)} < {int(min_records)}')
        records = sorted((self._record(row) for row in rows), key=lambda item: item['id'])
        canonical = ''.join(_json(item) + '\n' for item in records)
        digest = sha256(canonical.encode('utf-8')).hexdigest()
        snapshot_id = f'ds-{digest[:24]}'
        root = self.root / snapshot_id
        root.mkdir(parents=True, exist_ok=True)
        splits: dict[str, list[dict[str, Any]]] = {'train': [], 'validation': [], 'test': []}
        for item in records:
            splits[self._split(item['source_fingerprint'])].append(item)
        # Small but valid governed datasets may hash entirely into train. Move
        # whole source groups only, never individual records, to prevent source
        # leakage while ensuring evaluation splits exist when possible.
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in splits['train']:
            groups.setdefault(item['source_fingerprint'], []).append(item)
        if len(groups) >= 3:
            ordered_groups = sorted(groups.items(), key=lambda pair: pair[0])
            if not splits['validation']:
                fingerprint, moved = ordered_groups[-1]
                splits['validation'].extend(moved)
                splits['train'] = [item for item in splits['train'] if item['source_fingerprint'] != fingerprint]
                ordered_groups = ordered_groups[:-1]
            if not splits['test'] and ordered_groups:
                fingerprint, moved = ordered_groups[-1]
                splits['test'].extend(moved)
                splits['train'] = [item for item in splits['train'] if item['source_fingerprint'] != fingerprint]
        paths: dict[str, str] = {}
        for name, values in splits.items():
            path = root / f'{name}.jsonl'
            path.write_text(''.join(_json(item) + '\n' for item in values), encoding='utf-8')
            paths[name] = str(path)
        manifest = {
            'schema_version': 1,
            'snapshot_id': snapshot_id,
            'created_at': _now(),
            'dataset_name': str(dataset_name).strip() or 'vishnu-general',
            'records': len(records),
            'split_records': {key: len(value) for key, value in splits.items()},
            'dataset_sha256': digest,
            'selection': 'status=approved AND training_eligible=true',
            'split_strategy': 'source_fingerprint_grouped_80_10_10',
            'contains_hidden_chain_of_thought': False,
            'automatic_publication': False,
        }
        manifest_path = root / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        return TrainingDatasetSnapshot(
            snapshot_id=snapshot_id,
            created_at=manifest['created_at'],
            dataset_name=manifest['dataset_name'],
            root=str(root),
            train_path=paths['train'],
            validation_path=paths['validation'],
            test_path=paths['test'],
            manifest_path=str(manifest_path),
            records=len(records),
            train_records=len(splits['train']),
            validation_records=len(splits['validation']),
            test_records=len(splits['test']),
            sha256=digest,
        )


@dataclass(frozen=True)
class TrainingArtifact:
    checkpoint_ref: str
    backend_id: str
    base_model: str
    method: str
    metrics: dict[str, Any]


class TrainerBackend(Protocol):
    backend_id: str
    def available(self) -> tuple[bool, str | None]: ...
    def train(self, snapshot: TrainingDatasetSnapshot, settings: AutoTrainingSettings, output_dir: Path) -> TrainingArtifact: ...


class UnavailableTrainerBackend:
    backend_id = 'unavailable'
    def available(self) -> tuple[bool, str | None]:
        return False, 'no governed training backend is configured'
    def train(self, snapshot, settings, output_dir):
        raise RuntimeError('no governed training backend is configured')


class LocalPeftTrainerBackend:
    """Optional real local LoRA/QLoRA/full trainer.

    Heavy ML dependencies are imported only when training is actually used, so
    ordinary Vishnu installations remain lightweight. A missing dependency is
    reported as backend-unavailable rather than simulated success.
    """

    backend_id = 'local_peft'

    def available(self) -> tuple[bool, str | None]:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            import datasets  # noqa: F401
            import peft  # noqa: F401
        except Exception as exc:
            return False, f'optional ML dependency unavailable: {type(exc).__name__}'
        return True, None

    def train(self, snapshot: TrainingDatasetSnapshot, settings: AutoTrainingSettings, output_dir: Path) -> TrainingArtifact:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason or 'local training backend unavailable')
        if not settings.base_model:
            raise ValueError('base_model is required for local training')
        from datasets import load_dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
            DataCollatorForLanguageModeling, Trainer, TrainingArguments,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        files = {'train': snapshot.train_path}
        if snapshot.validation_records:
            files['validation'] = snapshot.validation_path
        dataset = load_dataset('json', data_files=files)
        tokenizer = AutoTokenizer.from_pretrained(settings.base_model, trust_remote_code=False)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        def tokenize(batch):
            texts = [
                f"### Instruction\n{instruction}\n\n### Response\n{response}{tokenizer.eos_token or ''}"
                for instruction, response in zip(batch['instruction'], batch['response'])
            ]
            return tokenizer(texts, truncation=True, max_length=2048)

        tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset['train'].column_names)
        model_kwargs: dict[str, Any] = {'trust_remote_code': False}
        if settings.method is TrainingMethod.QLORA:
            model_kwargs['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True)
        model = AutoModelForCausalLM.from_pretrained(settings.base_model, **model_kwargs)
        if settings.method in {TrainingMethod.LORA, TrainingMethod.QLORA}:
            if settings.method is TrainingMethod.QLORA:
                model = prepare_model_for_kbit_training(model)
            model = get_peft_model(model, LoraConfig(
                r=16,
                lora_alpha=32,
                lora_dropout=.05,
                bias='none',
                task_type=TaskType.CAUSAL_LM,
            ))
        args = TrainingArguments(
            output_dir=str(output_dir / 'runs'),
            num_train_epochs=1,
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=4,
            learning_rate=2e-4 if settings.method is not TrainingMethod.FULL else 2e-5,
            logging_steps=10,
            save_strategy='epoch',
            report_to=[],
            remove_unused_columns=False,
        )
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=tokenized['train'],
            eval_dataset=tokenized.get('validation'),
            data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        )
        train_result = trainer.train()
        metrics: dict[str, Any] = {'train_loss': float(getattr(train_result, 'training_loss', 0.0))}
        if 'validation' in tokenized and len(tokenized['validation']):
            evaluated = trainer.evaluate(tokenized['validation'])
            eval_loss = float(evaluated.get('eval_loss', math.inf))
            metrics['eval_loss'] = eval_loss
            metrics['quality_score'] = 0.0 if not math.isfinite(eval_loss) else 1.0 / (1.0 + max(0.0, eval_loss))
        checkpoint = output_dir / 'checkpoint'
        model.save_pretrained(str(checkpoint))
        tokenizer.save_pretrained(str(checkpoint))
        return TrainingArtifact(
            checkpoint_ref=str(checkpoint),
            backend_id=self.backend_id,
            base_model=settings.base_model,
            method=settings.method.value,
            metrics=metrics,
        )


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    quality_score: float
    baseline_quality_score: float | None
    safety_passed: bool
    shadow_passed: bool
    reasons: tuple[str, ...]
    metrics: dict[str, Any]


class ModelEvaluator(Protocol):
    def evaluate(self, artifact: TrainingArtifact, snapshot: TrainingDatasetSnapshot, settings: AutoTrainingSettings) -> EvaluationResult: ...


class FailClosedEvaluator:
    """Default when no candidate-serving evaluator is configured."""

    def evaluate(self, artifact, snapshot, settings) -> EvaluationResult:
        quality = float(artifact.metrics.get('quality_score', 0.0) or 0.0)
        return EvaluationResult(
            passed=False,
            quality_score=max(0.0, min(1.0, quality)),
            baseline_quality_score=None,
            safety_passed=False,
            shadow_passed=False,
            reasons=('candidate_safety_evaluator_not_configured',),
            metrics=dict(artifact.metrics),
        )


@dataclass(frozen=True)
class TrainingJob:
    job_id: str
    key: str
    status: TrainingJobStatus
    snapshot_id: str | None
    dataset_sha256: str | None
    backend_id: str
    base_model: str
    method: str
    model_id: str | None
    error_code: str | None
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        return {**asdict(self), 'status': self.status.value}


@dataclass(frozen=True)
class TrainedModel:
    model_id: str
    checkpoint_ref: str
    backend_id: str
    base_model: str
    method: str
    dataset_snapshot_id: str
    dataset_sha256: str
    status: TrainedModelStatus
    metrics: dict[str, Any]
    owner_approved_at: str | None
    activated_at: str | None
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        return {**asdict(self), 'status': self.status.value, 'automatic_activation': False}


class TrainingRegistry:
    """Persistent training-job and model-lineage registry."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self.connection:
            self.connection.executescript('''
                CREATE TABLE IF NOT EXISTS training_jobs(
                    job_id TEXT PRIMARY KEY, job_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                    snapshot_id TEXT, dataset_sha256 TEXT, backend_id TEXT NOT NULL,
                    base_model TEXT NOT NULL, method TEXT NOT NULL, model_id TEXT,
                    error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trained_models(
                    model_id TEXT PRIMARY KEY, checkpoint_ref TEXT NOT NULL UNIQUE,
                    backend_id TEXT NOT NULL, base_model TEXT NOT NULL, method TEXT NOT NULL,
                    dataset_snapshot_id TEXT NOT NULL, dataset_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL, metrics_json TEXT NOT NULL,
                    owner_approved_at TEXT, activated_at TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_trained_models_status ON trained_models(status, updated_at);
            ''')

    @staticmethod
    def _job(row: sqlite3.Row) -> TrainingJob:
        return TrainingJob(
            job_id=row['job_id'], key=row['job_key'], status=TrainingJobStatus(row['status']),
            snapshot_id=row['snapshot_id'], dataset_sha256=row['dataset_sha256'], backend_id=row['backend_id'],
            base_model=row['base_model'], method=row['method'], model_id=row['model_id'], error_code=row['error_code'],
            created_at=row['created_at'], updated_at=row['updated_at'],
        )

    @staticmethod
    def _model(row: sqlite3.Row) -> TrainedModel:
        return TrainedModel(
            model_id=row['model_id'], checkpoint_ref=row['checkpoint_ref'], backend_id=row['backend_id'],
            base_model=row['base_model'], method=row['method'], dataset_snapshot_id=row['dataset_snapshot_id'],
            dataset_sha256=row['dataset_sha256'], status=TrainedModelStatus(row['status']),
            metrics=json.loads(row['metrics_json'] or '{}'), owner_approved_at=row['owner_approved_at'],
            activated_at=row['activated_at'], created_at=row['created_at'], updated_at=row['updated_at'],
        )

    def create_job(self, *, key: str, backend_id: str, base_model: str, method: str) -> TrainingJob:
        existing = self.job_by_key(key)
        if existing is not None:
            return existing
        stamp = _now()
        job_id = f'train-{uuid4().hex[:20]}'
        with self._lock, self.connection:
            self.connection.execute(
                'INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, key, TrainingJobStatus.QUEUED.value, None, None, backend_id, base_model, method, None, None, stamp, stamp),
            )
        return self.get_job(job_id)

    def job_by_key(self, key: str) -> TrainingJob | None:
        with self._lock:
            row = self.connection.execute('SELECT * FROM training_jobs WHERE job_key=?', (str(key),)).fetchone()
        return None if row is None else self._job(row)

    def get_job(self, job_id: str) -> TrainingJob | None:
        with self._lock:
            row = self.connection.execute('SELECT * FROM training_jobs WHERE job_id=?', (str(job_id),)).fetchone()
        return None if row is None else self._job(row)

    def jobs(self, *, limit: int = 100) -> tuple[TrainingJob, ...]:
        with self._lock:
            rows = self.connection.execute('SELECT * FROM training_jobs ORDER BY created_at DESC LIMIT ?', (max(1, min(500, int(limit))),)).fetchall()
        return tuple(self._job(row) for row in rows)

    def update_job(self, job_id: str, status: TrainingJobStatus, *, snapshot=None, model_id=None, error_code=None) -> TrainingJob:
        stamp = _now()
        with self._lock, self.connection:
            self.connection.execute(
                '''UPDATE training_jobs SET status=?, snapshot_id=COALESCE(?,snapshot_id),
                   dataset_sha256=COALESCE(?,dataset_sha256), model_id=COALESCE(?,model_id),
                   error_code=?, updated_at=? WHERE job_id=?''',
                (status.value, getattr(snapshot, 'snapshot_id', None), getattr(snapshot, 'sha256', None), model_id, error_code, stamp, job_id),
            )
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def register_model(self, artifact: TrainingArtifact, snapshot: TrainingDatasetSnapshot) -> TrainedModel:
        model_id = f'model-{sha256((artifact.checkpoint_ref + snapshot.sha256).encode()).hexdigest()[:24]}'
        existing = self.get_model(model_id)
        if existing is not None:
            return existing
        stamp = _now()
        with self._lock, self.connection:
            self.connection.execute(
                'INSERT INTO trained_models VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (model_id, artifact.checkpoint_ref, artifact.backend_id, artifact.base_model, artifact.method,
                 snapshot.snapshot_id, snapshot.sha256, TrainedModelStatus.TRAINED.value, _json(artifact.metrics),
                 None, None, stamp, stamp),
            )
        return self.get_model(model_id)

    def get_model(self, model_id: str) -> TrainedModel | None:
        with self._lock:
            row = self.connection.execute('SELECT * FROM trained_models WHERE model_id=?', (str(model_id),)).fetchone()
        return None if row is None else self._model(row)

    def models(self, *, limit: int = 100) -> tuple[TrainedModel, ...]:
        with self._lock:
            rows = self.connection.execute('SELECT * FROM trained_models ORDER BY created_at DESC LIMIT ?', (max(1, min(500, int(limit))),)).fetchall()
        return tuple(self._model(row) for row in rows)

    def record_evaluation(self, model_id: str, result: EvaluationResult) -> TrainedModel:
        status = TrainedModelStatus.PROMOTION_READY if result.passed else TrainedModelStatus.EVALUATION_FAILED
        metrics = {**result.metrics, 'quality_score': result.quality_score, 'baseline_quality_score': result.baseline_quality_score,
                   'safety_passed': result.safety_passed, 'shadow_passed': result.shadow_passed, 'evaluation_reasons': list(result.reasons)}
        with self._lock, self.connection:
            self.connection.execute('UPDATE trained_models SET status=?,metrics_json=?,updated_at=? WHERE model_id=?',
                                    (status.value, _json(metrics), _now(), model_id))
        model = self.get_model(model_id)
        if model is None:
            raise KeyError(model_id)
        return model

    def approve_promotion(self, model_id: str, *, owner_id: str) -> TrainedModel:
        if str(owner_id) != 'owner':
            raise PermissionError('only the canonical owner may approve trained-model promotion')
        model = self.get_model(model_id)
        if model is None:
            raise KeyError(model_id)
        if model.status is not TrainedModelStatus.PROMOTION_READY:
            raise ValueError('model must pass evaluation before owner promotion approval')
        stamp = _now()
        with self._lock, self.connection:
            self.connection.execute('UPDATE trained_models SET status=?,owner_approved_at=?,updated_at=? WHERE model_id=?',
                                    (TrainedModelStatus.OWNER_APPROVED.value, stamp, stamp, model_id))
        return self.get_model(model_id)

    def confirm_activation(self, model_id: str, *, checkpoint_ref: str, actor: str = 'release_controller') -> TrainedModel:
        model = self.get_model(model_id)
        if model is None:
            raise KeyError(model_id)
        if model.status is not TrainedModelStatus.OWNER_APPROVED:
            raise ValueError('owner promotion approval is required before activation')
        if str(checkpoint_ref) != model.checkpoint_ref:
            raise ValueError('running checkpoint does not match owner-approved checkpoint')
        stamp = _now()
        with self._lock, self.connection:
            self.connection.execute('UPDATE trained_models SET status=?,activated_at=?,updated_at=? WHERE model_id=?',
                                    (TrainedModelStatus.ACTIVE.value, stamp, stamp, model_id))
        return self.get_model(model_id)

    def cancel_job(self, job_id: str) -> TrainingJob:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status in {TrainingJobStatus.COMPLETED, TrainingJobStatus.FAILED, TrainingJobStatus.CANCELLED}:
            return job
        return self.update_job(job_id, TrainingJobStatus.CANCELLED, error_code='owner_cancelled')

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class AutoTrainingCoordinator:
    """Dataset -> real trainer -> evaluation -> owner-promotion-ready pipeline."""

    def __init__(self, *, settings: TrainingSettingsService, candidates, snapshots: TrainingDatasetSnapshotBuilder,
                 registry: TrainingRegistry, backends: dict[str, TrainerBackend] | None = None,
                 evaluator: ModelEvaluator | None = None, output_root: str | Path, events=None) -> None:
        self.settings = settings
        self.candidates = candidates
        self.snapshots = snapshots
        self.registry = registry
        self.backends = dict(backends or {})
        self.evaluator = evaluator or FailClosedEvaluator()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.events = events
        self._lock = threading.RLock()

    def backend_status(self) -> dict[str, dict[str, Any]]:
        result = {}
        for backend_id, backend in self.backends.items():
            available, reason = backend.available()
            result[backend_id] = {'available': bool(available), 'reason': reason}
        return result

    def run_once(self, *, force: bool = False) -> TrainingJob | None:
        with self._lock:
            config = self.settings.snapshot()
            if not config.enabled and not force:
                return None
            backend = self.backends.get(config.backend_id)
            if backend is None:
                raise RuntimeError(f'configured training backend is unavailable: {config.backend_id}')
            available, reason = backend.available()
            if not available:
                raise RuntimeError(reason or f'training backend unavailable: {config.backend_id}')
            snapshot = self.snapshots.build(
                min_records=config.min_approved_records,
                limit=config.max_training_records,
            )
            key = sha256(f'{snapshot.sha256}|{config.backend_id}|{config.base_model}|{config.method.value}'.encode()).hexdigest()
            existing = self.registry.job_by_key(key)
            if existing is not None:
                return existing
            job = self.registry.create_job(key=key, backend_id=config.backend_id, base_model=config.base_model, method=config.method.value)
            try:
                job = self.registry.update_job(job.job_id, TrainingJobStatus.PREPARING, snapshot=snapshot)
                if self.events is not None:
                    self.events.emit('training.job_started', job_id=job.job_id, snapshot_id=snapshot.snapshot_id)
                job = self.registry.update_job(job.job_id, TrainingJobStatus.RUNNING)
                artifact = backend.train(snapshot, config, self.output_root / job.job_id)
                if not Path(artifact.checkpoint_ref).exists() and artifact.backend_id == LocalPeftTrainerBackend.backend_id:
                    raise RuntimeError('training backend returned a missing local checkpoint')
                model = self.registry.register_model(artifact, snapshot)
                job = self.registry.update_job(job.job_id, TrainingJobStatus.AWAITING_EVALUATION, model_id=model.model_id)
                evaluation = self.evaluator.evaluate(artifact, snapshot, config)
                model = self.registry.record_evaluation(model.model_id, evaluation)
                final_status = TrainingJobStatus.PROMOTION_READY if evaluation.passed else TrainingJobStatus.COMPLETED
                job = self.registry.update_job(job.job_id, final_status, model_id=model.model_id)
                if self.events is not None:
                    self.events.emit('training.job_completed', job_id=job.job_id, model_id=model.model_id,
                                     promotion_ready=evaluation.passed, production_activated=False)
                return job
            except Exception as exc:
                failed = self.registry.update_job(job.job_id, TrainingJobStatus.FAILED, error_code=type(exc).__name__)
                if self.events is not None:
                    self.events.emit('training.job_failed', job_id=failed.job_id, error_type=type(exc).__name__)
                raise

    def summary(self) -> dict[str, Any]:
        config = self.settings.snapshot()
        jobs = self.registry.jobs(limit=20)
        models = self.registry.models(limit=20)
        return {
            'settings': config.public(),
            'backends': self.backend_status(),
            'jobs': [item.public() for item in jobs],
            'models': [item.public() for item in models],
            'candidate_stats': self.candidates.stats(),
            'owner_promotion_required': True,
            'production_activation_automatic': False,
        }


class AutoTrainingRuntime:
    MIN_INTERVAL = 3600

    def __init__(self, coordinator: AutoTrainingCoordinator, *, events=None) -> None:
        self.coordinator = coordinator
        self.events = events
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycles = 0
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.coordinator.settings.snapshot().enabled

    def run_once(self):
        try:
            result = self.coordinator.run_once()
            self._cycles += 1
            self._last_error = None
            return result
        except ValueError as exc:
            # Not enough approved records is a normal no-op for an automatic
            # cadence, not a failed training attempt.
            if 'not enough approved training records' in str(exc):
                return None
            self._last_error = type(exc).__name__
            return None
        except Exception as exc:
            self._last_error = type(exc).__name__
            return None

    def _loop(self) -> None:
        while not self._stop.wait(max(self.MIN_INTERVAL, self.coordinator.settings.snapshot().interval_seconds)):
            self.run_once()

    def start(self) -> bool:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='vishnu-auto-training', daemon=True)
        self._thread.start()
        if self.events is not None:
            self.events.emit('training.auto_started', interval_seconds=self.coordinator.settings.snapshot().interval_seconds)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def status(self) -> dict[str, Any]:
        return {
            'enabled': self.enabled,
            'running': bool(self._thread and self._thread.is_alive()),
            'cycles': self._cycles,
            'last_error': self._last_error,
        }
