from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from server.trained_model_runtime_api import trained_model_runtime_router
from training.artifact_store import (
    ArtifactPublishingTrainerBackend,
    ArtifactVerifiedDeploymentBackend,
    FilesystemModelArtifactStore,
)
from training.deployment import DeploymentResult
from training.production_pipeline import attach_production_model_pipeline
from training.self_improvement import TrainingArtifact


def _checkpoint(root: Path, text: str = 'weights') -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / 'config.json').write_text('{"model_type":"test"}', encoding='utf-8')
    (root / 'model.safetensors').write_text(text, encoding='utf-8')
    return root


class FakeTrainer:
    backend_id = 'local_peft'

    def __init__(self, checkpoint: Path):
        self.checkpoint = checkpoint

    def available(self):
        return True, None

    def estimate_cost(self, snapshot, settings):
        return 0.0

    def train(self, snapshot, settings, output_dir):
        return TrainingArtifact(
            checkpoint_ref=str(self.checkpoint),
            backend_id=self.backend_id,
            base_model='base/test',
            method='full',
            metrics={'quality_score': 1.0},
        )


class FakeDeploymentBackend:
    backend_id = 'local_transformers'

    def __init__(self):
        self.running = None

    def available(self):
        return True, None

    def deploy(self, model):
        self.running = str(model.checkpoint_ref)
        return DeploymentResult(
            checkpoint_ref=self.running,
            deployment_ref='fake:deployment',
            metadata={},
        )

    def running_checkpoint(self, deployment_ref):
        return self.running if deployment_ref == 'fake:deployment' else None


class FakeCoordinator:
    def __init__(self, backend):
        self.backends = {'local_peft': backend}

    def summary(self):
        return {'backends': {'local_peft': {'available': True, 'reason': None}}}


class FakeController:
    def __init__(self, backend):
        self.backends = {'local_transformers': backend}

    def status(self):
        return {
            'backends': {
                key: {'available': value.available()[0], 'reason': value.available()[1]}
                for key, value in self.backends.items()
            }
        }


class FakeShadow:
    def status(self):
        return {'backends': {'local_transformers': {'available': True, 'reason': None}}}


class FakeRunner:
    persistent = True

    def status(self):
        return {'available': True, 'persistent': True, 'active': False}


def test_artifact_store_is_content_addressed_and_detects_tampering(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    store = FilesystemModelArtifactStore(tmp_path / 'store', persistent=True)

    first = store.stage(source, metadata={'purpose': 'test'})
    second = store.stage(source, metadata={'purpose': 'different-metadata'})

    assert first.artifact_id == second.artifact_id
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.checkpoint_ref == second.checkpoint_ref
    assert store.verify(first.checkpoint_ref).artifact_sha256 == first.artifact_sha256

    Path(first.checkpoint_ref, 'model.safetensors').write_text('tampered', encoding='utf-8')
    with pytest.raises(RuntimeError, match='digest mismatch|inventory mismatch'):
        store.verify(first.checkpoint_ref)


def test_artifact_store_rejects_symlinks(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    outside = tmp_path / 'outside.bin'
    outside.write_text('outside', encoding='utf-8')
    try:
        (source / 'escape.bin').symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation is unavailable on this platform')
    store = FilesystemModelArtifactStore(tmp_path / 'store', persistent=True)
    with pytest.raises(ValueError, match='Symbolic|symbolic'):
        store.stage(source)


def test_training_backend_publishes_verified_immutable_checkpoint(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    store = FilesystemModelArtifactStore(tmp_path / 'store', persistent=True)
    backend = ArtifactPublishingTrainerBackend(FakeTrainer(source), store)
    snapshot = SimpleNamespace(snapshot_id='ds-test', sha256='a' * 64)

    artifact = backend.train(snapshot, SimpleNamespace(), tmp_path / 'output')

    assert Path(artifact.checkpoint_ref).parent.parent == store.root
    assert artifact.metrics['artifact_verified'] is True
    assert artifact.metrics['artifact_persistent'] is True
    assert store.verify(artifact.checkpoint_ref).artifact_sha256 == artifact.metrics['artifact_sha256']


def test_release_backend_fails_closed_without_persistent_artifacts(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    ephemeral = FilesystemModelArtifactStore(tmp_path / 'ephemeral', persistent=False)
    manifest = ephemeral.stage(source)
    backend = ArtifactVerifiedDeploymentBackend(FakeDeploymentBackend(), ephemeral)
    model = SimpleNamespace(checkpoint_ref=manifest.checkpoint_ref)

    ok, reason = backend.available()
    assert ok is False
    assert 'not declared persistent' in str(reason)
    with pytest.raises(RuntimeError, match='not declared persistent'):
        backend.deploy(model)


def test_release_backend_requires_managed_verified_artifact(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    store = FilesystemModelArtifactStore(tmp_path / 'store', persistent=True)
    manifest = store.stage(source)
    inner = FakeDeploymentBackend()
    backend = ArtifactVerifiedDeploymentBackend(inner, store)

    result = backend.deploy(SimpleNamespace(checkpoint_ref=manifest.checkpoint_ref))
    assert result.metadata['artifact_verified'] is True
    assert backend.running_checkpoint(result.deployment_ref) == manifest.checkpoint_ref

    unmanaged = _checkpoint(tmp_path / 'unmanaged')
    with pytest.raises(ValueError, match='not managed'):
        backend.deploy(SimpleNamespace(checkpoint_ref=str(unmanaged)))


def test_attach_pipeline_wraps_training_and_release_without_approval_authority(tmp_path):
    source = _checkpoint(tmp_path / 'source')
    trainer = FakeTrainer(source)
    release = FakeDeploymentBackend()
    coordinator = FakeCoordinator(trainer)
    controller = FakeController(release)
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'events': None,
        'training_coordinator': coordinator,
        'training_settings': SimpleNamespace(snapshot=lambda: SimpleNamespace(base_model='base/test')),
        'training_candidate_store': SimpleNamespace(stats=lambda: {'approved': 10}),
        'training_registry': SimpleNamespace(models=lambda limit=1: ()),
        'shadow_qualification': FakeShadow(),
        'model_deployment': controller,
        'trained_model_runtime': FakeRunner(),
        'trained_model_deployment_backend': release,
    }
    store = FilesystemModelArtifactStore(tmp_path / 'store', persistent=True)

    pipeline = attach_production_model_pipeline(runtime, artifact_store=store)

    assert isinstance(coordinator.backends['local_peft'], ArtifactPublishingTrainerBackend)
    assert isinstance(controller.backends['local_transformers'], ArtifactVerifiedDeploymentBackend)
    status = pipeline.status()
    assert status['owner_approval_required'] is True
    assert status['owner_approval_can_be_bypassed'] is False
    assert status['automatic_owner_approval'] is False
    assert status['automatic_activation'] is False
    assert 'trained_model_inference_key_not_configured' in status['blockers']
    assert 'model_release_token_not_configured' in status['blockers']


def test_runtime_router_exposes_production_readiness_endpoint(tmp_path):
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'trained_model_runtime': object(),
    }
    router = trained_model_runtime_router(runtime)
    paths = {route.path for route in router.routes}
    assert '/trained-model/production' in paths
