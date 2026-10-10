from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from models.contracts import ModelRequest, RoutingCandidate
from models.performance_routing import attach_performance_routing
from training import (
    AutoTrainingCoordinator,
    EvaluationResult,
    ModelDeploymentController,
    TrainingArtifact,
    TrainingCandidateFactory,
    TrainingCandidateStore,
    TrainingDatasetSnapshotBuilder,
    TrainingJobStatus,
    TrainingRegistry,
    TrainingSettingsService,
    TrainedModelStatus,
)
from training.deployment import DeploymentResult


class _ProfileTracker:
    def profile(self, domain, provider_id, model_id):
        if provider_id == 'better':
            return SimpleNamespace(
                quality_score=1.0,
                success_rate=1.0,
                acceptance_rate=1.0,
                learning_influence=.5,
            )
        return SimpleNamespace(
            quality_score=0.0,
            success_rate=0.0,
            acceptance_rate=0.0,
            learning_influence=.5,
        )


class _RankRouter:
    def __init__(self):
        self._performance_routing_attached = False

    def _rank_request(self, request):
        return SimpleNamespace(policy_id='test'), (
            RoutingCandidate('worse', 'm1', .51, ('eligible',)),
            RoutingCandidate('better', 'm2', .50, ('eligible',)),
        )


def test_performance_learning_can_rerank_only_existing_eligible_candidates():
    router = _RankRouter()
    attach_performance_routing(router, _ProfileTracker(), enabled=lambda: True)
    _, ranked = router._rank_request(ModelRequest(prompt='x', metadata={'task_domain': 'coding'}))
    assert [row.provider_id for row in ranked] == ['better', 'worse']
    assert {row.provider_id for row in ranked} == {'better', 'worse'}
    assert max(abs(row.score - baseline) for row, baseline in zip(sorted(ranked, key=lambda r: r.provider_id), [.55, .46])) < 1e-9


def test_disabling_performance_learning_preserves_baseline_ranking():
    router = _RankRouter()
    attach_performance_routing(router, _ProfileTracker(), enabled=lambda: False)
    _, ranked = router._rank_request(ModelRequest(prompt='x', metadata={'task_domain': 'coding'}))
    assert [row.provider_id for row in ranked] == ['worse', 'better']
    assert [row.score for row in ranked] == [.51, .50]


def _approved_candidates(tmp_path: Path, count: int = 12):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    factory = TrainingCandidateFactory()
    for index in range(count):
        candidate = factory.create(
            source_type='explicit_owner_feedback',
            source_id=f'source-{index}',
            prompt=f'Instruction {index}',
            response=f'Response {index}',
            privacy_level='internal',
            provenance='owner accepted output',
            provider_id='self_hosted',
            model_id='base-model',
            verifier_score=.95,
        )
        store.save(candidate)
        store.approve(candidate.candidate_id)
    return store


def test_dataset_snapshot_split_has_no_source_leakage(tmp_path):
    store = _approved_candidates(tmp_path, 30)
    snapshot = TrainingDatasetSnapshotBuilder(store, tmp_path / 'datasets').build(min_records=10)

    def fingerprints(path):
        import json
        return {json.loads(line)['source_fingerprint'] for line in Path(path).read_text(encoding='utf-8').splitlines() if line}

    train = fingerprints(snapshot.train_path)
    validation = fingerprints(snapshot.validation_path)
    test = fingerprints(snapshot.test_path)
    assert snapshot.records == 30
    assert train
    assert validation
    assert test
    assert not (train & validation)
    assert not (train & test)
    assert not (validation & test)
    store.close()


class _Trainer:
    backend_id = 'fake'

    def available(self):
        return True, None

    def train(self, snapshot, settings, output_dir):
        checkpoint = Path(output_dir) / 'checkpoint'
        checkpoint.mkdir(parents=True, exist_ok=True)
        (checkpoint / 'weights.bin').write_bytes(b'qualified-test-artifact')
        return TrainingArtifact(
            checkpoint_ref=str(checkpoint),
            backend_id=self.backend_id,
            base_model=settings.base_model,
            method=settings.method.value,
            metrics={'quality_score': .95},
        )


class _Evaluator:
    def evaluate(self, artifact, snapshot, settings):
        return EvaluationResult(
            passed=True,
            quality_score=.95,
            baseline_quality_score=.80,
            safety_passed=True,
            shadow_passed=True,
            reasons=('evaluation_passed',),
            metrics={'quality_score': .95, 'shadow': .94},
        )


class _Deployment:
    backend_id = 'fake-deploy'

    def __init__(self):
        self.running = None

    def available(self):
        return True, None

    def deploy(self, model):
        self.running = model.checkpoint_ref
        return DeploymentResult(
            checkpoint_ref=model.checkpoint_ref,
            deployment_ref='deployment-1',
            metadata={'test': True},
        )

    def running_checkpoint(self, deployment_ref):
        return self.running


def test_real_training_lifecycle_requires_eval_owner_approval_and_exact_activation(tmp_path):
    store = _approved_candidates(tmp_path, 15)
    settings = TrainingSettingsService(tmp_path / 'settings.json')
    settings.update(
        enabled=True,
        backend_id='fake',
        base_model='owner-selected-base',
        method='lora',
        min_approved_records=10,
        require_safety_evaluation=True,
        require_shadow_evaluation=True,
    )
    registry = TrainingRegistry(tmp_path / 'registry.sqlite3')
    coordinator = AutoTrainingCoordinator(
        settings=settings,
        candidates=store,
        snapshots=TrainingDatasetSnapshotBuilder(store, tmp_path / 'snapshots'),
        registry=registry,
        backends={'fake': _Trainer()},
        evaluator=_Evaluator(),
        output_root=tmp_path / 'models',
    )

    job = coordinator.run_once()
    assert job is not None
    assert job.status is TrainingJobStatus.PROMOTION_READY
    model = registry.get_model(job.model_id)
    assert model is not None
    assert model.status is TrainedModelStatus.PROMOTION_READY

    with pytest.raises(PermissionError):
        registry.approve_promotion(model.model_id, owner_id='not-owner')
    approved = registry.approve_promotion(model.model_id, owner_id='owner')
    assert approved.status is TrainedModelStatus.OWNER_APPROVED

    backend = _Deployment()
    deployment = ModelDeploymentController(registry, backends={backend.backend_id: backend})
    active, result = deployment.deploy(approved.model_id, backend_id=backend.backend_id)
    assert result.checkpoint_ref == approved.checkpoint_ref
    assert active.status is TrainedModelStatus.ACTIVE
    assert active.activated_at

    store.close()
    registry.close()


def test_unconfigured_deployment_never_activates_owner_approved_model(tmp_path):
    store = _approved_candidates(tmp_path, 10)
    settings = TrainingSettingsService(tmp_path / 'settings.json')
    settings.update(enabled=True, backend_id='fake', base_model='base', min_approved_records=10)
    registry = TrainingRegistry(tmp_path / 'registry.sqlite3')
    coordinator = AutoTrainingCoordinator(
        settings=settings,
        candidates=store,
        snapshots=TrainingDatasetSnapshotBuilder(store, tmp_path / 'snapshots'),
        registry=registry,
        backends={'fake': _Trainer()},
        evaluator=_Evaluator(),
        output_root=tmp_path / 'models',
    )
    job = coordinator.run_once()
    model = registry.approve_promotion(job.model_id, owner_id='owner')
    controller = ModelDeploymentController(registry, backends={})
    with pytest.raises(RuntimeError, match='deployment backend unavailable'):
        controller.deploy(model.model_id, backend_id='missing')
    assert registry.get_model(model.model_id).status is TrainedModelStatus.OWNER_APPROVED
    store.close()
    registry.close()
