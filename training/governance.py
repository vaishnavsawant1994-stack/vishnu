from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import platform
from pathlib import Path
import sqlite3
import sys
import threading
import time
from typing import Any, Protocol
from uuid import uuid4

from training.deployment import ModelDeploymentController as BaseModelDeploymentController
from training.self_improvement import (
    AutoTrainingCoordinator as BaseAutoTrainingCoordinator,
    AutoTrainingSettings,
    EvaluationResult,
    LocalPeftTrainerBackend as BaseLocalPeftTrainerBackend,
    TrainedModelStatus,
    TrainingArtifact,
    TrainingDatasetSnapshot,
    TrainingDatasetSnapshotBuilder as BaseTrainingDatasetSnapshotBuilder,
    TrainingJobStatus,
    TrainingMethod,
    TrainingRegistry as BaseTrainingRegistry,
    TrainingSettingsService as BaseTrainingSettingsService,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


@dataclass(frozen=True)
class GovernedAutoTrainingSettings(AutoTrainingSettings):
    """Owner-governed scheduler controls layered over the trainer settings."""

    min_new_examples_since_last_training: int = 25
    max_training_cost: float | None = None
    max_runtime_seconds: int = 6 * 3600
    automatic_rollback: bool = True
    shadow_min_samples: int = 20
    shadow_min_pass_rate: float = 0.90
    shadow_min_quality_delta: float = 0.0
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= int(self.min_new_examples_since_last_training) <= 1_000_000:
            raise ValueError('min_new_examples_since_last_training must be between 0 and 1000000')
        if self.max_training_cost is not None and not 0 < float(self.max_training_cost) <= 1_000_000:
            raise ValueError('max_training_cost must be a positive number or null')
        if not 60 <= int(self.max_runtime_seconds) <= 7 * 24 * 3600:
            raise ValueError('max_runtime_seconds must be between 60 and 604800')
        if not 1 <= int(self.shadow_min_samples) <= 100_000:
            raise ValueError('shadow_min_samples must be between 1 and 100000')
        if not 0 <= float(self.shadow_min_pass_rate) <= 1:
            raise ValueError('shadow_min_pass_rate must be between 0 and 1')
        if not -1 <= float(self.shadow_min_quality_delta) <= 1:
            raise ValueError('shadow_min_quality_delta must be between -1 and 1')
        if not isinstance(self.hyperparameters, dict):
            raise ValueError('hyperparameters must be an object')
        if len(self.hyperparameters) > 100:
            raise ValueError('hyperparameters has too many entries')

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value['method'] = self.method.value
        value['production_activation_automatic'] = False
        value['public_dataset_upload_automatic'] = False
        value['full_from_scratch_training_available'] = False
        value['future_training_methods'] = ['continued_pretraining', 'foundation_pretraining']
        return value


class GovernedTrainingSettingsService(BaseTrainingSettingsService):
    """Persistent owner settings including scheduler, cost and shadow gates."""

    def snapshot(self) -> GovernedAutoTrainingSettings:
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
            return GovernedAutoTrainingSettings(
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
                min_new_examples_since_last_training=int(raw.get('min_new_examples_since_last_training', 25)),
                max_training_cost=(None if raw.get('max_training_cost') in (None, '') else float(raw.get('max_training_cost'))),
                max_runtime_seconds=int(raw.get('max_runtime_seconds', 6 * 3600)),
                automatic_rollback=bool(raw.get('automatic_rollback', True)),
                shadow_min_samples=int(raw.get('shadow_min_samples', 20)),
                shadow_min_pass_rate=float(raw.get('shadow_min_pass_rate', .90)),
                shadow_min_quality_delta=float(raw.get('shadow_min_quality_delta', 0.0)),
                hyperparameters=dict(raw.get('hyperparameters') or {}),
            )
        except (TypeError, ValueError):
            return GovernedAutoTrainingSettings()

    def update(self, **values: Any) -> GovernedAutoTrainingSettings:
        allowed = set(GovernedAutoTrainingSettings.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'unsupported training setting(s): {sorted(unknown)}')
        current = self.snapshot().public()
        for key in (
            'production_activation_automatic', 'public_dataset_upload_automatic',
            'full_from_scratch_training_available', 'future_training_methods',
        ):
            current.pop(key, None)
        current.update(values)
        current['method'] = TrainingMethod(str(current.get('method', TrainingMethod.LORA.value)).strip().lower())
        candidate = GovernedAutoTrainingSettings(**current)
        payload = candidate.public()
        for key in (
            'production_activation_automatic', 'public_dataset_upload_automatic',
            'full_from_scratch_training_available', 'future_training_methods',
        ):
            payload.pop(key, None)
        with self._lock:
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding='utf-8')
            temp.replace(self.path)
        if self.events is not None:
            self.events.emit('training.settings_updated', **candidate.public())
        return candidate


class GovernedTrainingDatasetSnapshotBuilder(BaseTrainingDatasetSnapshotBuilder):
    """Create immutable deterministic source-grouped dataset versions."""

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)

    def build(self, *, dataset_name: str = 'vishnu-general', min_records: int = 10, limit: int = 10000) -> TrainingDatasetSnapshot:
        rows = self.store.approved(limit=limit)
        if len(rows) < int(min_records):
            raise ValueError(f'not enough approved training records: {len(rows)} < {int(min_records)}')
        records = sorted((self._record(row) for row in rows), key=lambda item: item['id'])
        canonical = ''.join(self._canonical(item) + '\n' for item in records)
        digest = sha256(canonical.encode('utf-8')).hexdigest()
        snapshot_id = f'ds-{digest[:24]}'
        root = self.root / snapshot_id
        manifest_path = root / 'manifest.json'
        train_path = root / 'train.jsonl'
        validation_path = root / 'validation.jsonl'
        test_path = root / 'test.jsonl'

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('dataset_sha256') != digest:
                raise RuntimeError('immutable dataset snapshot digest mismatch')
            split_records = manifest.get('split_records') or {}
            return TrainingDatasetSnapshot(
                snapshot_id=snapshot_id,
                created_at=str(manifest['created_at']),
                dataset_name=str(manifest['dataset_name']),
                root=str(root),
                train_path=str(train_path),
                validation_path=str(validation_path),
                test_path=str(test_path),
                manifest_path=str(manifest_path),
                records=int(manifest['records']),
                train_records=int(split_records.get('train', 0)),
                validation_records=int(split_records.get('validation', 0)),
                test_records=int(split_records.get('test', 0)),
                sha256=digest,
            )

        root.mkdir(parents=True, exist_ok=True)
        splits: dict[str, list[dict[str, Any]]] = {'train': [], 'validation': [], 'test': []}
        for item in records:
            splits[self._split(item['source_fingerprint'])].append(item)
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in splits['train']:
            groups.setdefault(item['source_fingerprint'], []).append(item)
        if len(groups) >= 3:
            ordered = sorted(groups.items(), key=lambda pair: pair[0])
            if not splits['validation']:
                fingerprint, moved = ordered[-1]
                splits['validation'].extend(moved)
                splits['train'] = [item for item in splits['train'] if item['source_fingerprint'] != fingerprint]
                ordered = ordered[:-1]
            if not splits['test'] and ordered:
                fingerprint, moved = ordered[-1]
                splits['test'].extend(moved)
                splits['train'] = [item for item in splits['train'] if item['source_fingerprint'] != fingerprint]

        for path, values in ((train_path, splits['train']), (validation_path, splits['validation']), (test_path, splits['test'])):
            temp = path.with_suffix(path.suffix + '.tmp')
            temp.write_text(''.join(self._canonical(item) + '\n' for item in values), encoding='utf-8')
            temp.replace(path)
        manifest = {
            'schema_version': 2,
            'snapshot_id': snapshot_id,
            'created_at': _now(),
            'dataset_name': str(dataset_name).strip() or 'vishnu-general',
            'records': len(records),
            'split_records': {key: len(value) for key, value in splits.items()},
            'dataset_sha256': digest,
            'candidate_ids_sha256': sha256('\n'.join(item['id'] for item in records).encode()).hexdigest(),
            'selection': 'status=approved AND training_eligible=true',
            'split_strategy': 'source_fingerprint_grouped_80_10_10',
            'contains_hidden_chain_of_thought': False,
            'automatic_publication': False,
            'immutable': True,
        }
        temp_manifest = manifest_path.with_suffix('.tmp')
        temp_manifest.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        temp_manifest.replace(manifest_path)
        return TrainingDatasetSnapshot(
            snapshot_id=snapshot_id,
            created_at=manifest['created_at'],
            dataset_name=manifest['dataset_name'],
            root=str(root),
            train_path=str(train_path),
            validation_path=str(validation_path),
            test_path=str(test_path),
            manifest_path=str(manifest_path),
            records=len(records),
            train_records=len(splits['train']),
            validation_records=len(splits['validation']),
            test_records=len(splits['test']),
            sha256=digest,
        )


class TrainingGovernanceLedger:
    """Durable source→dataset→job→model lineage and shadow evidence."""

    MODEL_STATES = {
        'training', 'trained', 'evaluation_failed', 'shadow', 'candidate',
        'approved', 'active', 'superseded', 'rolled_back', 'rejected',
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self.connection:
            self.connection.executescript('''
                CREATE TABLE IF NOT EXISTS dataset_versions(
                    snapshot_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                    records INTEGER NOT NULL, manifest_path TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_members(
                    snapshot_id TEXT NOT NULL, candidate_id TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id,candidate_id)
                );
                CREATE INDEX IF NOT EXISTS idx_dataset_source ON dataset_members(source_fingerprint,snapshot_id);
                CREATE TABLE IF NOT EXISTS governed_training_jobs(
                    job_id TEXT PRIMARY KEY, snapshot_id TEXT, status TEXT NOT NULL,
                    started_at TEXT, ended_at TEXT, backend_id TEXT NOT NULL, base_model TEXT NOT NULL,
                    training_method TEXT NOT NULL, hyperparameters_json TEXT NOT NULL,
                    logs_json TEXT NOT NULL, artifact_ref TEXT, estimated_cost REAL,
                    resource_json TEXT NOT NULL, failure_reason TEXT, reproducibility_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_lifecycle(
                    model_id TEXT PRIMARY KEY, model_version TEXT NOT NULL, base_model TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL, training_job_id TEXT, checkpoint_ref TEXT NOT NULL,
                    training_method TEXT NOT NULL, evaluation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, status TEXT NOT NULL, promotion_state TEXT NOT NULL,
                    deployment_state TEXT NOT NULL, rollback_parent TEXT, lineage_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_model_lifecycle_status ON model_lifecycle(status,updated_at);
                CREATE TABLE IF NOT EXISTS shadow_observations(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL, passed INTEGER NOT NULL,
                    quality_score REAL NOT NULL, baseline_quality_score REAL NOT NULL,
                    latency_ms REAL, estimated_cost REAL NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_shadow_model ON shadow_observations(model_id,created_at);
                CREATE TABLE IF NOT EXISTS source_revocations(
                    source_fingerprint TEXT PRIMARY KEY, revoked_at TEXT NOT NULL, reason TEXT NOT NULL
                );
            ''')

    @staticmethod
    def snapshot_members(snapshot: TrainingDatasetSnapshot) -> tuple[dict[str, str], ...]:
        rows: list[dict[str, str]] = []
        for path in (snapshot.train_path, snapshot.validation_path, snapshot.test_path):
            file = Path(path)
            if not file.exists():
                continue
            for line in file.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get('id') and item.get('source_fingerprint'):
                    rows.append({'candidate_id': str(item['id']), 'source_fingerprint': str(item['source_fingerprint'])})
        return tuple(rows)

    def register_dataset(self, snapshot: TrainingDatasetSnapshot) -> None:
        members = self.snapshot_members(snapshot)
        with self._lock, self.connection:
            self.connection.execute(
                'INSERT OR IGNORE INTO dataset_versions VALUES(?,?,?,?,?)',
                (snapshot.snapshot_id, snapshot.sha256, snapshot.created_at, snapshot.records, snapshot.manifest_path),
            )
            for item in members:
                self.connection.execute(
                    'INSERT OR IGNORE INTO dataset_members VALUES(?,?,?)',
                    (snapshot.snapshot_id, item['candidate_id'], item['source_fingerprint']),
                )

    def latest_dataset_members(self) -> set[str]:
        with self._lock:
            row = self.connection.execute(
                '''SELECT snapshot_id FROM governed_training_jobs
                   WHERE status='completed' AND snapshot_id IS NOT NULL
                   ORDER BY ended_at DESC LIMIT 1'''
            ).fetchone()
            if row is None:
                return set()
            rows = self.connection.execute('SELECT candidate_id FROM dataset_members WHERE snapshot_id=?', (row['snapshot_id'],)).fetchall()
        return {str(item['candidate_id']) for item in rows}

    def start_job(self, job, snapshot: TrainingDatasetSnapshot, settings: GovernedAutoTrainingSettings) -> None:
        self.register_dataset(snapshot)
        with self._lock, self.connection:
            self.connection.execute(
                '''INSERT OR REPLACE INTO governed_training_jobs
                   (job_id,snapshot_id,status,started_at,ended_at,backend_id,base_model,training_method,
                    hyperparameters_json,logs_json,artifact_ref,estimated_cost,resource_json,failure_reason,reproducibility_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    job.job_id, snapshot.snapshot_id, 'training', _now(), None,
                    settings.backend_id, settings.base_model, settings.method.value,
                    _json(settings.hyperparameters), _json([{'at': _now(), 'stage': 'started'}]),
                    None, None, _json({}), None,
                    _json({
                        'python': sys.version.split()[0], 'platform': platform.platform(),
                        'dataset_sha256': snapshot.sha256, 'backend_id': settings.backend_id,
                        'base_model': settings.base_model, 'method': settings.method.value,
                        'hyperparameters': settings.hyperparameters,
                    }),
                ),
            )

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        artifact_ref: str | None = None,
        estimated_cost: float | None = None,
        resource: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock, self.connection:
            current = self.connection.execute('SELECT logs_json FROM governed_training_jobs WHERE job_id=?', (job_id,)).fetchone()
            existing_logs = json.loads(current['logs_json'] or '[]') if current else []
            existing_logs.extend(logs or [])
            existing_logs.append({'at': _now(), 'stage': status})
            self.connection.execute(
                '''UPDATE governed_training_jobs SET status=?,ended_at=?,artifact_ref=?,estimated_cost=?,
                   resource_json=?,failure_reason=?,logs_json=? WHERE job_id=?''',
                (status, _now(), artifact_ref, estimated_cost, _json(resource or {}), failure_reason, _json(existing_logs), job_id),
            )

    def upsert_model(self, model, *, job_id: str | None = None, status: str = 'trained', evaluation: dict[str, Any] | None = None) -> None:
        if status not in self.MODEL_STATES:
            raise ValueError('unsupported model lifecycle status')
        with self._lock, self.connection:
            existing = self.connection.execute('SELECT model_version,created_at,training_job_id FROM model_lifecycle WHERE model_id=?', (model.model_id,)).fetchone()
            if existing is None:
                count = int(self.connection.execute('SELECT COUNT(*) FROM model_lifecycle').fetchone()[0]) + 1
                version = f'v{count}'
                created = model.created_at
                stored_job = job_id
            else:
                version = str(existing['model_version'])
                created = str(existing['created_at'])
                stored_job = job_id or existing['training_job_id']
            self.connection.execute(
                '''INSERT OR REPLACE INTO model_lifecycle
                   (model_id,model_version,base_model,snapshot_id,training_job_id,checkpoint_ref,training_method,
                    evaluation_json,created_at,status,promotion_state,deployment_state,rollback_parent,lineage_json,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    model.model_id, version, model.base_model, model.dataset_snapshot_id, stored_job,
                    model.checkpoint_ref, model.method, _json(evaluation or model.metrics), created, status,
                    'shadow_required' if status == 'shadow' else ('eligible' if status == 'candidate' else 'not_eligible'),
                    'inactive', None,
                    _json({'base_model': model.base_model, 'dataset_versions': [model.dataset_snapshot_id], 'training_job': stored_job}),
                    _now(),
                ),
            )

    def bind_model_job(self, model_id: str, job_id: str) -> None:
        with self._lock, self.connection:
            self.connection.execute('UPDATE model_lifecycle SET training_job_id=?,updated_at=? WHERE model_id=?', (job_id, _now(), model_id))

    def lifecycle(self, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute('SELECT * FROM model_lifecycle WHERE model_id=?', (model_id,)).fetchone()
        if row is None:
            return None
        value = dict(row)
        value['evaluation'] = json.loads(value.pop('evaluation_json') or '{}')
        value['lineage'] = json.loads(value.pop('lineage_json') or '{}')
        return value

    def models(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self.connection.execute('SELECT * FROM model_lifecycle ORDER BY created_at DESC LIMIT ?', (max(1, min(500, int(limit))),)).fetchall()
        return tuple(self.lifecycle(str(row['model_id'])) for row in rows if row is not None)

    def mark_model(self, model_id: str, *, status: str, promotion_state: str | None = None, deployment_state: str | None = None, rollback_parent: str | None = None) -> None:
        if status not in self.MODEL_STATES:
            raise ValueError('unsupported model lifecycle status')
        with self._lock, self.connection:
            self.connection.execute(
                '''UPDATE model_lifecycle SET status=?,promotion_state=COALESCE(?,promotion_state),
                   deployment_state=COALESCE(?,deployment_state),rollback_parent=COALESCE(?,rollback_parent),updated_at=?
                   WHERE model_id=?''',
                (status, promotion_state, deployment_state, rollback_parent, _now(), model_id),
            )

    def record_evaluation(self, model_id: str, result: EvaluationResult) -> None:
        lifecycle = self.lifecycle(model_id)
        if lifecycle is None:
            return
        status = 'shadow' if result.passed else 'evaluation_failed'
        with self._lock, self.connection:
            self.connection.execute(
                '''UPDATE model_lifecycle SET status=?,promotion_state=?,evaluation_json=?,updated_at=? WHERE model_id=?''',
                (status, 'shadow_required' if result.passed else 'blocked', _json({
                    **dict(result.metrics), 'passed': result.passed, 'quality_score': result.quality_score,
                    'baseline_quality_score': result.baseline_quality_score, 'safety_passed': result.safety_passed,
                    'shadow_passed': result.shadow_passed, 'reasons': list(result.reasons),
                }), _now(), model_id),
            )

    def record_shadow(
        self,
        model_id: str,
        *,
        request_id: str,
        passed: bool,
        quality_score: float,
        baseline_quality_score: float,
        latency_ms: float | None = None,
        estimated_cost: float = 0.0,
    ) -> dict[str, Any]:
        lifecycle = self.lifecycle(model_id)
        if lifecycle is None:
            raise KeyError(model_id)
        if lifecycle['status'] not in {'shadow', 'candidate'}:
            raise ValueError('model is not eligible for shadow qualification')
        fingerprint = sha256(str(request_id).encode('utf-8', errors='replace')).hexdigest()
        with self._lock, self.connection:
            self.connection.execute(
                '''INSERT INTO shadow_observations
                   (model_id,request_fingerprint,passed,quality_score,baseline_quality_score,latency_ms,estimated_cost,created_at)
                   VALUES(?,?,?,?,?,?,?,?)''',
                (model_id, fingerprint, int(bool(passed)), float(quality_score), float(baseline_quality_score), latency_ms, max(0.0, float(estimated_cost)), _now()),
            )
        return self.shadow_summary(model_id)

    def shadow_summary(self, model_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                '''SELECT COUNT(*) AS samples, COALESCE(SUM(passed),0) AS passes,
                   AVG(quality_score-baseline_quality_score) AS quality_delta,
                   AVG(latency_ms) AS latency_ms, AVG(estimated_cost) AS estimated_cost
                   FROM shadow_observations WHERE model_id=?''',
                (model_id,),
            ).fetchone()
        samples = int(row['samples'] or 0)
        passes = int(row['passes'] or 0)
        return {
            'samples': samples,
            'pass_rate': passes / samples if samples else 0.0,
            'quality_delta': float(row['quality_delta'] or 0.0),
            'latency_ms': None if row['latency_ms'] is None else float(row['latency_ms']),
            'estimated_cost': float(row['estimated_cost'] or 0.0),
            'authoritative': False,
        }

    def qualify_shadow(self, model_id: str, settings: GovernedAutoTrainingSettings) -> bool:
        summary = self.shadow_summary(model_id)
        passed = (
            summary['samples'] >= settings.shadow_min_samples
            and summary['pass_rate'] >= settings.shadow_min_pass_rate
            and summary['quality_delta'] >= settings.shadow_min_quality_delta
        )
        if passed:
            self.mark_model(model_id, status='candidate', promotion_state='eligible')
        return passed

    def active_model(self) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute("SELECT model_id FROM model_lifecycle WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
        return None if row is None else self.lifecycle(str(row['model_id']))

    def affected_models_for_source(self, source_fingerprint: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self.connection.execute(
                '''SELECT DISTINCT ml.model_id FROM model_lifecycle ml
                   JOIN dataset_members dm ON dm.snapshot_id=ml.snapshot_id
                   WHERE dm.source_fingerprint=?''',
                (str(source_fingerprint),),
            ).fetchall()
        return tuple(self.lifecycle(str(row['model_id'])) for row in rows if row is not None)

    def revoke_source(self, source_fingerprint: str, reason: str) -> tuple[dict[str, Any], ...]:
        with self._lock, self.connection:
            self.connection.execute(
                'INSERT OR REPLACE INTO source_revocations VALUES(?,?,?)',
                (str(source_fingerprint), _now(), str(reason)),
            )
        return self.affected_models_for_source(source_fingerprint)

    def job_public(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute('SELECT * FROM governed_training_jobs WHERE job_id=?', (str(job_id),)).fetchone()
        if row is None:
            return None
        value = dict(row)
        for source, target in (
            ('hyperparameters_json', 'hyperparameters'), ('logs_json', 'logs'),
            ('resource_json', 'resource'), ('reproducibility_json', 'reproducibility'),
        ):
            value[target] = json.loads(value.pop(source) or ('[]' if target == 'logs' else '{}'))
        return value

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class GovernedTrainingRegistry(BaseTrainingRegistry):
    """Legacy-compatible registry plus authoritative lifecycle/lineage ledger."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        path = Path(path)
        self.governance = TrainingGovernanceLedger(path.with_name(path.stem + '-governance.sqlite3'))

    def register_model(self, artifact: TrainingArtifact, snapshot: TrainingDatasetSnapshot):
        model = super().register_model(artifact, snapshot)
        self.governance.upsert_model(model, status='trained')
        return model

    def record_evaluation(self, model_id: str, result: EvaluationResult):
        model = super().record_evaluation(model_id, result)
        self.governance.record_evaluation(model_id, result)
        return model

    def approve_promotion(self, model_id: str, *, owner_id: str):
        lifecycle = self.governance.lifecycle(model_id)
        if lifecycle is None or lifecycle['status'] != 'candidate' or lifecycle['promotion_state'] != 'eligible':
            raise ValueError('model must complete live shadow qualification before owner promotion approval')
        model = super().approve_promotion(model_id, owner_id=owner_id)
        self.governance.mark_model(model_id, status='approved', promotion_state='owner_approved')
        return model

    def confirm_activation(self, model_id: str, *, checkpoint_ref: str, actor: str = 'release_controller'):
        previous = self.governance.active_model()
        model = super().confirm_activation(model_id, checkpoint_ref=checkpoint_ref, actor=actor)
        if previous and previous['model_id'] != model_id:
            self.governance.mark_model(previous['model_id'], status='superseded', deployment_state='inactive')
        self.governance.mark_model(
            model_id,
            status='active',
            promotion_state='adopted',
            deployment_state='active',
            rollback_parent=(previous['model_id'] if previous else None),
        )
        return model

    def public_job(self, job) -> dict[str, Any]:
        governance = self.governance.job_public(job.job_id)
        return {**job.public(), 'governance': governance}

    def public_model(self, model) -> dict[str, Any]:
        lifecycle = self.governance.lifecycle(model.model_id)
        shadow = self.governance.shadow_summary(model.model_id) if lifecycle and lifecycle['status'] in {'shadow', 'candidate'} else None
        return {**model.public(), 'lifecycle': lifecycle, 'shadow': shadow}

    def close(self) -> None:
        self.governance.close()
        super().close()


class GovernedLocalPeftTrainerBackend(BaseLocalPeftTrainerBackend):
    """Local GPU backend with explicit zero external-compute cost estimate."""

    def estimate_cost(self, snapshot: TrainingDatasetSnapshot, settings: GovernedAutoTrainingSettings) -> float:
        return 0.0


class GovernedAutoTrainingCoordinator(BaseAutoTrainingCoordinator):
    """Scheduler-aware dataset→train→evaluate→shadow pipeline."""

    def _estimated_cost(self, backend, snapshot, config: GovernedAutoTrainingSettings) -> float | None:
        estimator = getattr(backend, 'estimate_cost', None)
        if callable(estimator):
            value = estimator(snapshot, config)
            return None if value is None else max(0.0, float(value))
        return None

    def run_once(self, *, force: bool = False):
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
            snapshot = self.snapshots.build(min_records=config.min_approved_records, limit=config.max_training_records)
            governance = getattr(self.registry, 'governance', None)
            if governance is not None:
                governance.register_dataset(snapshot)
                previous = governance.latest_dataset_members()
                current = {item['candidate_id'] for item in governance.snapshot_members(snapshot)}
                new_examples = len(current - previous) if previous else len(current)
                if previous and not force and new_examples < config.min_new_examples_since_last_training:
                    return None
            estimate = self._estimated_cost(backend, snapshot, config)
            if config.max_training_cost is not None:
                if estimate is None:
                    raise RuntimeError('training backend cannot prove cost within owner maximum')
                if estimate > config.max_training_cost:
                    raise RuntimeError('estimated training cost exceeds owner maximum')

            key = sha256(f'{snapshot.sha256}|{config.backend_id}|{config.base_model}|{config.method.value}|{_json(config.hyperparameters)}'.encode()).hexdigest()
            existing = self.registry.job_by_key(key)
            if existing is not None:
                return existing
            job = self.registry.create_job(key=key, backend_id=config.backend_id, base_model=config.base_model, method=config.method.value)
            started = time.monotonic()
            if governance is not None:
                governance.start_job(job, snapshot, config)
            try:
                job = self.registry.update_job(job.job_id, TrainingJobStatus.PREPARING, snapshot=snapshot)
                if self.events is not None:
                    self.events.emit('training.job_started', job_id=job.job_id, snapshot_id=snapshot.snapshot_id)
                job = self.registry.update_job(job.job_id, TrainingJobStatus.RUNNING)
                artifact = backend.train(snapshot, config, self.output_root / job.job_id)
                elapsed = time.monotonic() - started
                if elapsed > config.max_runtime_seconds:
                    raise RuntimeError('training exceeded owner maximum runtime')
                if not Path(artifact.checkpoint_ref).exists() and artifact.backend_id == BaseLocalPeftTrainerBackend.backend_id:
                    raise RuntimeError('training backend returned a missing local checkpoint')
                model = self.registry.register_model(artifact, snapshot)
                if governance is not None:
                    governance.bind_model_job(model.model_id, job.job_id)
                job = self.registry.update_job(job.job_id, TrainingJobStatus.AWAITING_EVALUATION, model_id=model.model_id)
                evaluation = self.evaluator.evaluate(artifact, snapshot, config)
                model = self.registry.record_evaluation(model.model_id, evaluation)
                job = self.registry.update_job(job.job_id, TrainingJobStatus.COMPLETED, model_id=model.model_id)
                if governance is not None:
                    actual_cost = artifact.metrics.get('estimated_cost', estimate) if isinstance(artifact.metrics, dict) else estimate
                    resource = artifact.metrics.get('resource', {}) if isinstance(artifact.metrics, dict) else {}
                    governance.finish_job(
                        job.job_id,
                        status='completed',
                        artifact_ref=artifact.checkpoint_ref,
                        estimated_cost=None if actual_cost is None else float(actual_cost),
                        resource=resource if isinstance(resource, dict) else {},
                        logs=[{'at': _now(), 'stage': 'evaluation', 'passed': evaluation.passed, 'reasons': list(evaluation.reasons)}],
                    )
                if self.events is not None:
                    self.events.emit(
                        'training.job_completed', job_id=job.job_id, model_id=model.model_id,
                        evaluation_passed=evaluation.passed, live_shadow_required=bool(evaluation.passed),
                        promotion_ready=False, production_activated=False,
                    )
                return job
            except Exception as exc:
                failed = self.registry.update_job(job.job_id, TrainingJobStatus.FAILED, error_code=type(exc).__name__)
                if governance is not None:
                    governance.finish_job(failed.job_id, status='failed', failure_reason=type(exc).__name__)
                if self.events is not None:
                    self.events.emit('training.job_failed', job_id=failed.job_id, error_type=type(exc).__name__)
                raise

    def summary(self) -> dict[str, Any]:
        value = super().summary()
        if hasattr(self.registry, 'public_job'):
            value['jobs'] = [self.registry.public_job(item) for item in self.registry.jobs(limit=20)]
        if hasattr(self.registry, 'public_model'):
            value['models'] = [self.registry.public_model(item) for item in self.registry.models(limit=20)]
        value['shadow_qualification_required_before_promotion'] = True
        value['full_from_scratch_training_available'] = False
        return value


@dataclass(frozen=True)
class ShadowResult:
    passed: bool
    quality_score: float
    baseline_quality_score: float
    latency_ms: float | None = None
    estimated_cost: float = 0.0


class ShadowModelBackend(Protocol):
    backend_id: str
    def available(self) -> tuple[bool, str | None]: ...
    def evaluate_shadow(self, model, request, authoritative_response) -> ShadowResult: ...


class ShadowQualificationRuntime:
    """Non-authoritative real-request shadow qualification when a backend exists."""

    def __init__(self, registry: GovernedTrainingRegistry, settings: GovernedTrainingSettingsService, *, backends: dict[str, ShadowModelBackend] | None = None, events=None) -> None:
        self.registry = registry
        self.settings = settings
        self.backends = dict(backends or {})
        self.events = events
        self._observations = 0
        self._last_error: str | None = None

    def backend_status(self) -> dict[str, Any]:
        result = {}
        for key, backend in self.backends.items():
            ok, reason = backend.available()
            result[key] = {'available': bool(ok), 'reason': reason}
        return result

    def observe_request(self, request, authoritative_response, verification=None, strategy=None) -> None:
        # Sensitive/private requests are never sent to a shadow backend unless a
        # future backend is explicitly local and the owner policy permits it.
        if str(getattr(request, 'sensitivity', '')).strip().lower() in {'private', 'sensitive', 'secret', 'restricted'}:
            return
        candidates = [item for item in self.registry.governance.models(limit=20) if item and item['status'] == 'shadow']
        if not candidates or not self.backends:
            return
        model_info = candidates[0]
        model = self.registry.get_model(model_info['model_id'])
        if model is None:
            return
        for backend in self.backends.values():
            ok, _ = backend.available()
            if not ok:
                continue
            try:
                result = backend.evaluate_shadow(model, request, authoritative_response)
                self.registry.governance.record_shadow(
                    model.model_id,
                    request_id=str(getattr(request, 'request_id', uuid4().hex)),
                    passed=result.passed,
                    quality_score=result.quality_score,
                    baseline_quality_score=result.baseline_quality_score,
                    latency_ms=result.latency_ms,
                    estimated_cost=result.estimated_cost,
                )
                qualified = self.registry.governance.qualify_shadow(model.model_id, self.settings.snapshot())
                self._observations += 1
                self._last_error = None
                if self.events is not None:
                    self.events.emit('training.shadow_observed', model_id=model.model_id, qualified=qualified, authoritative=False)
            except Exception as exc:
                self._last_error = type(exc).__name__
            break

    def record_observation(self, model_id: str, **values) -> dict[str, Any]:
        summary = self.registry.governance.record_shadow(model_id, **values)
        qualified = self.registry.governance.qualify_shadow(model_id, self.settings.snapshot())
        return {**summary, 'qualified': qualified}

    def status(self) -> dict[str, Any]:
        return {
            'backends': self.backend_status(),
            'observations': self._observations,
            'last_error': self._last_error,
            'authoritative': False,
            'promotion_requires_sufficient_shadow_evidence': True,
        }


class GovernedModelDeploymentController(BaseModelDeploymentController):
    """Owner/release deployment boundary with exact-checkpoint rollback lineage."""

    def rollback(self, active_model_id: str, *, backend_id: str, actor: str = 'release_controller'):
        active = self.registry.governance.lifecycle(active_model_id)
        if active is None or active['status'] != 'active':
            raise ValueError('rollback source must be the active governed model')
        parent_id = active.get('rollback_parent')
        if not parent_id:
            raise ValueError('active model has no known-good rollback parent')
        parent = self.registry.get_model(parent_id)
        if parent is None:
            raise KeyError(parent_id)
        backend = self.backends.get(str(backend_id))
        if backend is None:
            raise RuntimeError(f'deployment backend unavailable: {backend_id}')
        available, reason = backend.available()
        if not available:
            raise RuntimeError(reason or f'deployment backend unavailable: {backend_id}')
        # Rollback is still a release-controller action. It does not grant the
        # trained model or evaluator authority to activate itself.
        result = backend.deploy(parent)
        running = backend.running_checkpoint(result.deployment_ref)
        if str(running or '') != str(parent.checkpoint_ref):
            raise RuntimeError('rollback backend could not prove the known-good checkpoint is running')
        with self.registry._lock, self.registry.connection:
            self.registry.connection.execute(
                'UPDATE trained_models SET status=?,activated_at=?,updated_at=? WHERE model_id=?',
                (TrainedModelStatus.ACTIVE.value, _now(), _now(), parent.model_id),
            )
        self.registry.governance.mark_model(active_model_id, status='rolled_back', deployment_state='inactive')
        self.registry.governance.mark_model(parent.model_id, status='active', promotion_state='adopted', deployment_state='active')
        if self.events is not None:
            self.events.emit('training.model_rolled_back', from_model=active_model_id, to_model=parent.model_id, actor=actor)
        return self.registry.get_model(parent.model_id), result

    def status(self) -> dict[str, Any]:
        value = super().status()
        value['rollback_supported'] = True
        value['rollback_requires_release_controller'] = True
        return value
