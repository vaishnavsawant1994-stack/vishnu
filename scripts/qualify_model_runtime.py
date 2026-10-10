from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.governance import GovernedAutoTrainingSettings
from training.local_runtime import LocalCheckpointRunner, LocalTransformersDeploymentBackend
from training.runtime_controls import BoundedLocalPeftTrainerBackend
from training.self_improvement import TrainingDatasetSnapshot, TrainingMethod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows), encoding='utf-8')


def _dataset(root: Path) -> TrainingDatasetSnapshot:
    rows = [
        {
            'id': f'qualification-{index:02d}',
            'instruction': f'Reply with exactly VISHNU_RUNTIME_{index:02d}',
            'response': f'VISHNU_RUNTIME_{index:02d}',
            'source_type': 'runtime_qualification_synthetic',
            'source_fingerprint': f'qualification-source-{index:02d}',
            'provenance': 'generated_by_runtime_qualification',
            'consent_basis': 'synthetic_non_user_data',
            'privacy_level': 'public',
            'provider_id': 'synthetic',
            'model_id': 'synthetic',
            'verifier_score': 1.0,
        }
        for index in range(12)
    ]
    canonical = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n' for row in rows)
    digest = sha256(canonical.encode('utf-8')).hexdigest()
    snapshot_id = f'runtime-qualification-{digest[:20]}'
    dataset_root = root / snapshot_id
    dataset_root.mkdir(parents=True, exist_ok=True)
    train, validation, test = rows[:8], rows[8:10], rows[10:]
    train_path = dataset_root / 'train.jsonl'
    validation_path = dataset_root / 'validation.jsonl'
    test_path = dataset_root / 'test.jsonl'
    _write_jsonl(train_path, train)
    _write_jsonl(validation_path, validation)
    _write_jsonl(test_path, test)
    manifest = {
        'schema_version': 1,
        'purpose': 'infrastructure_runtime_qualification_only',
        'synthetic_non_user_data': True,
        'records': len(rows),
        'dataset_sha256': digest,
        'automatic_publication': False,
        'promotion_evidence': False,
    }
    manifest_path = dataset_root / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
    return TrainingDatasetSnapshot(
        snapshot_id=snapshot_id,
        created_at=str(time.time()),
        dataset_name='vishnu-runtime-qualification',
        root=str(dataset_root),
        train_path=str(train_path),
        validation_path=str(validation_path),
        test_path=str(test_path),
        manifest_path=str(manifest_path),
        records=len(rows),
        train_records=len(train),
        validation_records=len(validation),
        test_records=len(test),
        sha256=digest,
    )


def main() -> int:
    data_dir = Path(os.getenv('PERSONAL_AI_DATA_DIR', str(Path.home() / '.personal_ai'))).expanduser().resolve()
    root = data_dir / 'model-runtime-qualification'
    root.mkdir(parents=True, exist_ok=True)
    evidence_path = root / 'qualification.json'
    base_model = str(os.getenv('VISHNU_QUALIFICATION_BASE_MODEL', 'hf-internal-testing/tiny-random-gpt2')).strip()
    backend = BoundedLocalPeftTrainerBackend()
    available, reason = backend.available()
    if not available:
        raise RuntimeError(reason or 'local training backend unavailable')

    snapshot = _dataset(root)
    settings = GovernedAutoTrainingSettings(
        enabled=False,
        backend_id='local_peft',
        base_model=base_model,
        method=TrainingMethod.FULL,
        min_approved_records=10,
        interval_seconds=3600,
        minimum_quality_score=0.80,
        minimum_improvement=0.0,
        require_safety_evaluation=True,
        require_shadow_evaluation=True,
        max_training_records=100,
        max_runtime_seconds=600,
        automatic_rollback=True,
        shadow_min_samples=20,
        shadow_min_pass_rate=0.90,
        shadow_min_quality_delta=0.0,
        hyperparameters={
            'num_train_epochs': 0.1,
            'per_device_train_batch_size': 2,
            'per_device_eval_batch_size': 2,
            'gradient_accumulation_steps': 1,
            'learning_rate': 5e-5,
            'logging_steps': 1,
            'max_length': 128,
        },
    )

    output_dir = root / 'trained-canary'
    started = time.time()
    artifact = backend.train(snapshot, settings, output_dir)
    candidate = SimpleNamespace(
        model_id=f'runtime-canary-{snapshot.sha256[:12]}',
        checkpoint_ref=artifact.checkpoint_ref,
        base_model=artifact.base_model,
        method=artifact.method,
    )
    runner = LocalCheckpointRunner(root / 'runner-state', persistent=False)
    inference = runner.generate(
        candidate,
        system='This is a synthetic runtime qualification. Reply briefly.',
        prompt='Say VISHNU_RUNTIME_READY.',
        max_new_tokens=8,
        temperature=0.0,
    )

    # Exercise the real deployment adapter in a completely isolated canary
    # state directory. This is not the Vishnu production registry and therefore
    # cannot create an owner-approved/active production model. We prove exact
    # checkpoint switching and switch-back behavior only.
    known_good_path = root / 'known-good-checkpoint'
    if known_good_path.exists():
        shutil.rmtree(known_good_path)
    shutil.copytree(Path(artifact.checkpoint_ref), known_good_path)
    known_good = SimpleNamespace(
        model_id=f'runtime-known-good-{snapshot.sha256[:12]}',
        checkpoint_ref=str(known_good_path),
        base_model=artifact.base_model,
        method=artifact.method,
    )
    deployment = LocalTransformersDeploymentBackend(runner, allow_ephemeral_activation=True)
    first = deployment.deploy(known_good)
    first_verified = deployment.running_checkpoint(first.deployment_ref) == known_good.checkpoint_ref
    second = deployment.deploy(candidate)
    second_verified = deployment.running_checkpoint(second.deployment_ref) == candidate.checkpoint_ref
    switched_back = deployment.deploy(known_good)
    switchback_verified = deployment.running_checkpoint(switched_back.deployment_ref) == known_good.checkpoint_ref

    elapsed = max(0.0, time.time() - started)
    checkpoint_present = Path(artifact.checkpoint_ref).exists()
    evidence = {
        'qualified': bool(
            checkpoint_present
            and isinstance(inference.get('content'), str)
            and first_verified
            and second_verified
            and switchback_verified
        ),
        'qualification_type': 'real_weight_training_loadable_inference_and_checkpoint_switchback',
        'real_weight_training': True,
        'loadable_inference': True,
        'real_backend_exact_checkpoint_proof': bool(first_verified and second_verified),
        'real_backend_switchback_proof': bool(switchback_verified),
        'production_controller_rollback_proof': False,
        'synthetic_non_user_data': True,
        'base_model': base_model,
        'training_method': artifact.method,
        'checkpoint_present': checkpoint_present,
        'backend_id': artifact.backend_id,
        'train_loss': artifact.metrics.get('train_loss'),
        'eval_loss': artifact.metrics.get('eval_loss'),
        'training_runtime_seconds': artifact.metrics.get('runtime_seconds'),
        'qualification_runtime_seconds': elapsed,
        'inference_latency_ms': inference.get('latency_ms'),
        'reply_excerpt': str(inference.get('content') or '')[:160],
        'promotion_attempted': False,
        'promotion_eligible': False,
        'owner_approval_bypassed': False,
        'automatic_activation': False,
        'production_model_claimed': False,
        'note': 'This canary proves real training, checkpoint inference and isolated exact-checkpoint switchback. It is not production-quality, promotion evidence, or production activation.',
    }
    temp = evidence_path.with_suffix('.tmp')
    temp.write_text(json.dumps(evidence, sort_keys=True, indent=2), encoding='utf-8')
    temp.replace(evidence_path)
    print(json.dumps({'event': 'trained_model_runtime.qualified', **evidence}, sort_keys=True), flush=True)
    return 0 if evidence['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
