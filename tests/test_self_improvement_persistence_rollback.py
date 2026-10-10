from __future__ import annotations

from pathlib import Path

from models.performance import ModelPerformanceTracker, PerformanceObservation
from server.owner_intelligence_api import owner_intelligence_router
from training import (
    AutoTrainingCoordinator,
    EvaluationResult,
    ModelDeploymentController,
    TrainingArtifact,
    TrainingCandidateFactory,
    TrainingCandidateStore,
    TrainingDatasetSnapshotBuilder,
    TrainingRegistry,
    TrainingSettingsService,
)
from training.deployment import DeploymentResult


class _Trainer:
    backend_id = 'fake'

    def available(self):
        return True, None

    def estimate_cost(self, snapshot, settings):
        return 0.0

    def train(self, snapshot, settings, output_dir):
        checkpoint = Path(output_dir) / 'checkpoint'
        checkpoint.mkdir(parents=True, exist_ok=True)
        (checkpoint / 'adapter.bin').write_bytes(snapshot.sha256.encode('ascii'))
        return TrainingArtifact(
            checkpoint_ref=str(checkpoint),
            backend_id=self.backend_id,
            base_model=settings.base_model,
            method=settings.method.value,
            metrics={'estimated_cost': 0.0, 'quality_score': .95},
        )


class _Evaluator:
    def evaluate(self, artifact, snapshot, settings):
        return EvaluationResult(
            passed=True,
            quality_score=.95,
            baseline_quality_score=.85,
            safety_passed=True,
            shadow_passed=True,
            reasons=('evaluation_passed',),
            metrics={'quality_score': .95},
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
            deployment_ref=f'deploy:{model.model_id}',
            metadata={'test': True},
        )

    def running_checkpoint(self, deployment_ref):
        return self.running


def _add_approved(store, start, count):
    factory = TrainingCandidateFactory()
    for index in range(start, start + count):
        candidate = factory.create(
            source_type='explicit_owner_feedback',
            source_id=f'source-{index}',
            prompt=f'question {index}',
            response=f'answer {index}',
            provenance=f'owner-feedback:{index}',
            verifier_score=.95,
        )
        store.save(candidate)
        store.approve(candidate.candidate_id)


def _qualify_and_approve(registry, settings, model_id):
    registry.governance.record_shadow(
        model_id,
        request_id=f'shadow:{model_id}',
        passed=True,
        quality_score=.96,
        baseline_quality_score=.90,
    )
    assert registry.governance.qualify_shadow(model_id, settings.snapshot()) is True
    return registry.approve_promotion(model_id, owner_id='owner')


def test_training_settings_candidates_registry_and_performance_survive_restart(tmp_path):
    candidate_path = tmp_path / 'candidates.sqlite3'
    store = TrainingCandidateStore(candidate_path)
    _add_approved(store, 0, 1)
    candidate_id = store.approved()[0].candidate_id
    store.close()
    reopened_store = TrainingCandidateStore(candidate_path)
    assert reopened_store.get(candidate_id) is not None
    assert reopened_store.get(candidate_id).status.value == 'approved'
    reopened_store.close()

    settings_path = tmp_path / 'training-settings.json'
    settings = TrainingSettingsService(settings_path)
    settings.update(
        enabled=True,
        backend_id='local_peft',
        base_model='example/base',
        min_approved_records=10,
        min_new_examples_since_last_training=7,
        max_runtime_seconds=1234,
        hyperparameters={'learning_rate': 0.0002},
    )
    restarted_settings = TrainingSettingsService(settings_path).snapshot()
    assert restarted_settings.enabled is True
    assert restarted_settings.min_new_examples_since_last_training == 7
    assert restarted_settings.max_runtime_seconds == 1234
    assert restarted_settings.hyperparameters == {'learning_rate': 0.0002}

    performance_path = tmp_path / 'performance.sqlite3'
    tracker = ModelPerformanceTracker(path=performance_path)
    tracker.record(PerformanceObservation(
        task_domain='coding',
        task_complexity='high',
        specialist_role='reviewer',
        provider_id='provider',
        model_id='model',
        success=True,
        verifier_score=.9,
    ))
    tracker.close()
    restarted_tracker = ModelPerformanceTracker(path=performance_path)
    profile = restarted_tracker.profile(
        'coding', 'provider', 'model', task_complexity='high', specialist_role='reviewer'
    )
    assert profile is not None
    assert profile.samples == 1
    restarted_tracker.close()

    registry_path = tmp_path / 'registry.sqlite3'
    registry = TrainingRegistry(registry_path)
    job = registry.create_job(key='restart-key', backend_id='fake', base_model='base', method='lora')
    registry.close()
    restarted_registry = TrainingRegistry(registry_path)
    assert restarted_registry.get_job(job.job_id) is not None
    assert restarted_registry.get_job(job.job_id).key == 'restart-key'
    restarted_registry.close()


def test_known_good_model_can_be_rolled_back_through_release_controller(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _add_approved(store, 0, 10)
    settings = TrainingSettingsService(tmp_path / 'settings.json')
    settings.update(
        enabled=True,
        backend_id='fake',
        base_model='base-model',
        min_approved_records=10,
        min_new_examples_since_last_training=1,
        shadow_min_samples=1,
        shadow_min_pass_rate=.9,
    )
    registry = TrainingRegistry(tmp_path / 'registry.sqlite3')
    coordinator = AutoTrainingCoordinator(
        settings=settings,
        candidates=store,
        snapshots=TrainingDatasetSnapshotBuilder(store, tmp_path / 'datasets'),
        registry=registry,
        backends={'fake': _Trainer()},
        evaluator=_Evaluator(),
        output_root=tmp_path / 'models',
    )
    backend = _Deployment()
    controller = ModelDeploymentController(registry, backends={backend.backend_id: backend})

    first_job = coordinator.run_once()
    first = _qualify_and_approve(registry, settings, first_job.model_id)
    first_active, _ = controller.deploy(first.model_id, backend_id=backend.backend_id)
    assert registry.governance.lifecycle(first_active.model_id)['status'] == 'active'

    _add_approved(store, 10, 1)
    second_job = coordinator.run_once()
    second = _qualify_and_approve(registry, settings, second_job.model_id)
    second_active, _ = controller.deploy(second.model_id, backend_id=backend.backend_id)
    second_lifecycle = registry.governance.lifecycle(second_active.model_id)
    assert second_lifecycle['status'] == 'active'
    assert second_lifecycle['rollback_parent'] == first.model_id
    assert registry.governance.lifecycle(first.model_id)['status'] == 'superseded'

    rolled_back, result = controller.rollback(second.model_id, backend_id=backend.backend_id)
    assert rolled_back.model_id == first.model_id
    assert result.checkpoint_ref == first.checkpoint_ref
    assert backend.running == first.checkpoint_ref
    assert registry.governance.lifecycle(second.model_id)['status'] == 'rolled_back'
    assert registry.governance.lifecycle(first.model_id)['status'] == 'active'
    registry.close()
    store.close()


def test_owner_controls_register_training_lineage_and_evolution_api_routes():
    router = owner_intelligence_router({'device_registry': object()})
    paths = {route.path for route in router.routes}
    assert '/iphone/api/owner/intelligence/summary' in paths
    assert '/iphone/api/owner/intelligence/settings' in paths
    assert '/iphone/api/owner/intelligence/training/settings' in paths
    assert '/iphone/api/owner/intelligence/training/run' in paths
    assert '/iphone/api/owner/intelligence/training/jobs' in paths
    assert '/iphone/api/owner/intelligence/training/models' in paths
    assert '/iphone/api/owner/intelligence/training/models/{model_id}/lineage' in paths
    assert '/iphone/api/owner/intelligence/training/models/{model_id}/approve-promotion' in paths
    assert '/iphone/api/owner/intelligence/training/candidates' in paths
    assert '/iphone/api/owner/intelligence/training/sources/tombstone' in paths
    assert '/iphone/api/owner/intelligence/training/export' in paths
    assert '/iphone/api/owner/intelligence/evolution/run-approved' in paths
