from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from training.artifact_store import (
    ArtifactPublishingTrainerBackend,
    ArtifactVerifiedDeploymentBackend,
    build_model_artifact_store,
)
from training.self_improvement import TrainedModelStatus


def _configured(name: str) -> bool:
    return bool(str(os.getenv(name, '') or '').strip())


def _lifecycle_public(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in ('status', 'promotion_state', 'deployment_state', 'rollback_parent')
        if key in value
    }


class ProductionModelPipeline:
    """Readiness/orchestration surface for the governed model release chain.

    This class deliberately has no owner-approval method and no direct model
    activation method. It composes the existing training, evaluation, shadow,
    owner approval and release-controller boundaries without becoming a second
    source of authority. ``status`` is safe for the unauthenticated health
    surface: local paths, raw job records and secret values are never returned.
    """

    def __init__(self, runtime: dict, artifact_store) -> None:
        self.runtime = runtime
        self.artifact_store = artifact_store

    def _registry(self):
        return self.runtime.get('training_registry')

    def _latest_model(self):
        registry = self._registry()
        if registry is None:
            return None
        values = registry.models(limit=1)
        return values[0] if values else None

    def model_status(self, model_id: str) -> dict[str, Any]:
        registry = self._registry()
        if registry is None:
            raise RuntimeError('training registry is unavailable')
        model = registry.get_model(model_id)
        if model is None:
            raise KeyError(model_id)
        governance = getattr(registry, 'governance', None)
        lifecycle = None if governance is None else governance.lifecycle(model_id)
        artifact: dict[str, Any]
        try:
            manifest = self.artifact_store.verify(model.checkpoint_ref)
            artifact = {
                'managed': True,
                'verified': True,
                'artifact_id': manifest.artifact_id,
                'artifact_sha256': manifest.artifact_sha256,
                'persistent': bool(self.artifact_store.persistent),
            }
        except Exception as exc:
            artifact = {
                'managed': bool(getattr(self.artifact_store, 'is_managed', lambda value: False)(model.checkpoint_ref)),
                'verified': False,
                'persistent': bool(self.artifact_store.persistent),
                'reason': type(exc).__name__,
            }
        return {
            'model_id': model.model_id,
            'status': model.status.value,
            'artifact': artifact,
            'lifecycle': _lifecycle_public(lifecycle),
            'owner_approved': model.status in {TrainedModelStatus.OWNER_APPROVED, TrainedModelStatus.ACTIVE},
            'active': model.status is TrainedModelStatus.ACTIVE,
            'automatic_owner_approval': False,
            'automatic_activation': False,
        }

    def _training_public(self, coordinator, config) -> dict[str, Any] | None:
        if coordinator is None:
            return None
        registry = self._registry()
        jobs = registry.jobs(limit=20) if registry is not None and hasattr(registry, 'jobs') else ()
        models = registry.models(limit=20) if registry is not None and hasattr(registry, 'models') else ()
        method = getattr(config, 'method', None)
        return {
            'enabled': bool(getattr(config, 'enabled', False)) if config is not None else False,
            'backend_id': str(getattr(config, 'backend_id', '') or '') if config is not None else '',
            'base_model_configured': bool(str(getattr(config, 'base_model', '') or '').strip()) if config is not None else False,
            'method': getattr(method, 'value', str(method or '')),
            'backends': coordinator.backend_status() if hasattr(coordinator, 'backend_status') else {},
            'recent_job_count': len(jobs),
            'recent_model_count': len(models),
        }

    def status(self) -> dict[str, Any]:
        coordinator = self.runtime.get('training_coordinator')
        shadow = self.runtime.get('shadow_qualification')
        deployment = self.runtime.get('model_deployment')
        runner = self.runtime.get('trained_model_runtime')
        settings = self.runtime.get('training_settings')
        candidates = self.runtime.get('training_candidate_store')

        training_config = settings.snapshot() if settings is not None else None
        candidate_stats = candidates.stats() if candidates is not None and hasattr(candidates, 'stats') else {}
        shadow_status = shadow.status() if shadow is not None else {'backends': {}}
        deployment_status = deployment.status() if deployment is not None else {'backends': {}}
        runtime_status = runner.status() if runner is not None else {'available': False, 'persistent': False}
        artifact_status = dict(self.artifact_store.status())
        artifact_status.pop('root', None)

        blockers: list[str] = []
        if coordinator is None:
            blockers.append('training_coordinator_unavailable')
        if training_config is None:
            blockers.append('training_settings_unavailable')
        elif not str(training_config.base_model or '').strip():
            blockers.append('base_model_not_configured')
        if not bool(artifact_status.get('persistent')):
            blockers.append('artifact_store_not_persistent')
        if not bool(runtime_status.get('available')):
            blockers.append('trained_model_runtime_unavailable')
        if not bool(runtime_status.get('persistent')):
            blockers.append('trained_model_runtime_not_persistent')

        shadow_backends = dict(shadow_status.get('backends') or {})
        if not any(bool(item.get('available')) for item in shadow_backends.values() if isinstance(item, dict)):
            blockers.append('shadow_backend_unavailable')
        deployment_backends = dict(deployment_status.get('backends') or {})
        if not any(bool(item.get('available')) for item in deployment_backends.values() if isinstance(item, dict)):
            blockers.append('deployment_backend_unavailable')
        if not _configured('VISHNU_TRAINED_MODEL_API_KEY'):
            blockers.append('trained_model_inference_key_not_configured')
        if not _configured('VISHNU_MODEL_RELEASE_TOKEN'):
            blockers.append('model_release_token_not_configured')

        latest = self._latest_model()
        latest_status = None
        if latest is not None:
            try:
                latest_status = self.model_status(latest.model_id)
            except Exception:
                latest_status = {'model_id': latest.model_id, 'status': latest.status.value, 'artifact': {'verified': False}}

        return {
            'schema_version': 1,
            'artifact_store': artifact_status,
            'training': self._training_public(coordinator, training_config),
            'candidate_stats': candidate_stats,
            'shadow': shadow_status,
            'deployment': deployment_status,
            'runtime': runtime_status,
            'latest_model': latest_status,
            'inference_api_key_configured': _configured('VISHNU_TRAINED_MODEL_API_KEY'),
            'release_token_configured': _configured('VISHNU_MODEL_RELEASE_TOKEN'),
            'infrastructure_ready': not blockers,
            'blockers': blockers,
            'owner_approval_required': True,
            'owner_approval_can_be_bypassed': False,
            'automatic_owner_approval': False,
            'automatic_activation': False,
            'production_model_claimed': bool(latest_status and latest_status.get('active') and not blockers),
        }

    def run_training(self, *, force: bool = False) -> dict[str, Any] | None:
        coordinator = self.runtime.get('training_coordinator')
        if coordinator is None:
            raise RuntimeError('training coordinator is unavailable')
        job = coordinator.run_once(force=force)
        if job is None:
            return None
        registry = self._registry()
        public_job = registry.public_job(job) if registry is not None and hasattr(registry, 'public_job') else job.public()
        model = None if not getattr(job, 'model_id', None) else self.model_status(job.model_id)
        return {
            'job': public_job,
            'model': model,
            'stopped_before_owner_approval': True,
            'automatic_owner_approval': False,
            'automatic_activation': False,
        }

    def assert_release_ready(self, model_id: str) -> dict[str, Any]:
        status = self.model_status(model_id)
        if not bool(self.artifact_store.persistent):
            raise RuntimeError('production release requires a persistent model artifact store')
        if not bool(status['artifact'].get('verified')):
            raise RuntimeError('production release requires a verified immutable model artifact')
        if not status['owner_approved']:
            raise ValueError('owner promotion approval is required before production release')
        return status


def attach_production_model_pipeline(runtime: dict, *, artifact_store=None) -> ProductionModelPipeline:
    """Attach durable artifact publication and release verification once."""

    existing = runtime.get('production_model_pipeline')
    if existing is not None:
        return existing
    settings = runtime.get('settings')
    data_dir = Path(getattr(settings, 'data_dir', '.'))
    store = artifact_store or build_model_artifact_store(data_dir)

    coordinator = runtime.get('training_coordinator')
    if coordinator is None or not hasattr(coordinator, 'backends'):
        raise RuntimeError('governed training coordinator is unavailable')
    for backend_id, backend in tuple(coordinator.backends.items()):
        if isinstance(backend, ArtifactPublishingTrainerBackend):
            continue
        coordinator.backends[backend_id] = ArtifactPublishingTrainerBackend(backend, store)

    controller = runtime.get('model_deployment')
    release_backend = runtime.get('trained_model_deployment_backend')
    if controller is not None and release_backend is not None:
        verified = ArtifactVerifiedDeploymentBackend(release_backend, store)
        controller.backends[verified.backend_id] = verified
        runtime['trained_model_deployment_backend'] = verified

    pipeline = ProductionModelPipeline(runtime, store)
    runtime['model_artifact_store'] = store
    runtime['production_model_pipeline'] = pipeline
    events = runtime.get('events')
    if events is not None:
        events.emit(
            'training.production_pipeline_attached',
            artifact_store='filesystem',
            artifact_persistent=bool(store.persistent),
            owner_approval_required=True,
            automatic_activation=False,
        )
    return pipeline
