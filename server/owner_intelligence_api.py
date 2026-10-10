from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from security.request_context import current_trusted_request


class IntelligenceSettingsBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    mode: str | None = Field(default=None, max_length=32)
    auto_escalation: bool | None = None
    verification_enabled: bool | None = None
    training_capture: bool | None = None
    performance_learning: bool | None = None
    max_models: int | None = Field(default=None, ge=1, le=5)
    latency_preference: str | None = Field(default=None, max_length=32)
    max_cost_per_request: float | None = Field(default=None, gt=0, le=10000)


class AutoTrainingSettingsBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    backend_id: str | None = Field(default=None, min_length=1, max_length=80)
    base_model: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=40)
    min_approved_records: int | None = Field(default=None, ge=10, le=1_000_000)
    min_new_examples_since_last_training: int | None = Field(default=None, ge=0, le=1_000_000)
    interval_seconds: int | None = Field(default=None, ge=3600, le=2_592_000)
    max_training_cost: float | None = Field(default=None, gt=0, le=1_000_000)
    max_runtime_seconds: int | None = Field(default=None, ge=60, le=604_800)
    minimum_quality_score: float | None = Field(default=None, ge=0, le=1)
    minimum_improvement: float | None = Field(default=None, ge=0, le=1)
    require_safety_evaluation: bool | None = None
    require_shadow_evaluation: bool | None = None
    shadow_min_samples: int | None = Field(default=None, ge=1, le=100_000)
    shadow_min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    shadow_min_quality_delta: float | None = Field(default=None, ge=-1, le=1)
    automatic_rollback: bool | None = None
    max_training_records: int | None = Field(default=None, ge=10, le=1_000_000)
    hyperparameters: dict[str, Any] | None = None


class CandidateDecisionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(default='owner_or_policy_rejected', min_length=1, max_length=300)


class SourceTombstoneBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=1000)
    reason: str = Field(default='source_deleted_or_consent_revoked', min_length=1, max_length=300)


class DatasetExportBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_name: str = Field(default='vishnu-general', min_length=1, max_length=80)
    limit: int = Field(default=10000, ge=1, le=10000)


def owner_intelligence_router(runtime) -> APIRouter:
    """Owner-only surface for intelligence, training and safe self-improvement.

    This router can configure/trigger model training and implementation of an
    *already owner-approved* evolution handoff. It deliberately exposes no model
    activation, Body adoption, merge, deployment, provider-key mutation or
    approval-bypass endpoint.
    """

    router = APIRouter(prefix='/iphone/api/owner/intelligence', tags=['owner-intelligence'])
    registry = runtime['device_registry']
    events = runtime.get('events')

    def authenticate(device_id: str | None, token: str | None, scope: str = 'device:admin') -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, 'This browser is not trusted or its session was revoked')
        if not registry.is_active(device_id):
            raise HTTPException(401, 'This browser is not trusted or its session was revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, scope):
            raise HTTPException(403, f'This device is not permitted to use {scope}')
        return device_id

    def require_fresh_owner_verification(device_id: str) -> None:
        if runtime.get('pwa_sessions') is None:
            return
        context = current_trusted_request()
        ttl = int(getattr(runtime.get('agent_executor'), 'reauth_ttl_seconds', 300) or 300)
        ttl = max(30, min(ttl, 900))
        stamp = getattr(context, 'reauthenticated_at', None) if context is not None else None
        try:
            age = time.time() - float(stamp)
        except (TypeError, ValueError):
            age = ttl + 1
        if context is None or context.device_id != device_id or age < 0 or age > ttl:
            raise HTTPException(401, {
                'code': 'reauthentication_required',
                'message': 'Fresh owner verification is required for this data-governance action.',
            })

    def emit(name: str, **payload) -> None:
        if events is not None:
            events.emit(name, **payload)

    def settings_service():
        service = runtime.get('intelligence_settings')
        if service is None:
            raise HTTPException(503, 'intelligence settings unavailable')
        return service

    def training_store():
        store = runtime.get('training_candidate_store')
        if store is None:
            raise HTTPException(503, 'training candidate store unavailable')
        return store

    def training_coordinator():
        service = runtime.get('training_coordinator')
        if service is None:
            raise HTTPException(503, 'training coordinator unavailable')
        return service

    def training_registry():
        service = runtime.get('training_registry')
        if service is None:
            raise HTTPException(503, 'training registry unavailable')
        return service

    def public_job(service, job):
        serializer = getattr(service, 'public_job', None)
        return serializer(job) if callable(serializer) else job.public()

    def public_model(service, model):
        serializer = getattr(service, 'public_model', None)
        return serializer(model) if callable(serializer) else model.public()

    @router.get('/summary')
    def summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        settings = settings_service().snapshot()
        performance = runtime.get('model_performance')
        store = training_store()
        intelligence = runtime.get('intelligence') or runtime.get('models')
        status = intelligence.status() if intelligence is not None else {}
        coordinator = runtime.get('training_coordinator')
        auto_training = runtime.get('auto_training')
        shadow = runtime.get('shadow_qualification')
        code_runtime = runtime.get('automatic_code_evolution_runtime')
        deployment = runtime.get('model_deployment')
        return {
            'settings': settings.public(),
            'performance': [item.public() for item in performance.profiles()] if performance is not None else [],
            'training': store.stats(),
            'auto_training': coordinator.summary() if coordinator is not None else None,
            'auto_training_runtime': auto_training.status() if auto_training is not None else None,
            'shadow_qualification': shadow.status() if shadow is not None else {'backends': {}, 'authoritative': False},
            'code_evolution': code_runtime.status() if code_runtime is not None else {'available': False},
            'model_deployment': deployment.status() if deployment is not None else {'backends': {}},
            'runtime': status.get('advanced_intelligence', {}),
            'training_capture_default': True,
            'training_capture_is_approval': False,
            'model_output_authority': False,
            'automatic_publication': False,
            'automatic_model_activation': False,
            'automatic_code_adoption': False,
            'exact_machine_unlearning_claimed': False,
        }

    @router.patch('/settings')
    def update_settings(
        body: IntelligenceSettingsBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        values = body.model_dump(exclude_unset=True)
        try:
            snapshot = settings_service().update(**values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        emit('owner.intelligence.settings_updated', device_id=device_id, **snapshot.public())
        return {'ok': True, 'settings': snapshot.public()}

    @router.patch('/training/settings')
    def update_training_settings(
        body: AutoTrainingSettingsBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        service = runtime.get('training_settings')
        if service is None:
            raise HTTPException(503, 'training settings unavailable')
        try:
            snapshot = service.update(**body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        auto_runtime = runtime.get('auto_training')
        if auto_runtime is not None:
            if snapshot.enabled:
                auto_runtime.start()
            else:
                auto_runtime.stop()
        emit('owner.training.settings_updated', device_id=device_id, enabled=snapshot.enabled, backend_id=snapshot.backend_id)
        return {'ok': True, 'settings': snapshot.public(), 'runtime': auto_runtime.status() if auto_runtime is not None else None}

    @router.post('/training/run')
    def run_training(
        background: BackgroundTasks,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        coordinator = training_coordinator()
        background.add_task(coordinator.run_once, force=True)
        emit('owner.training.run_requested', device_id=device_id)
        return {
            'ok': True,
            'scheduled': True,
            'live_shadow_required_before_promotion': True,
            'production_activation_automatic': False,
        }

    @router.get('/training/jobs')
    def training_jobs(
        limit: int = 100,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        service = training_registry()
        return {'jobs': [public_job(service, job) for job in service.jobs(limit=limit)]}

    @router.post('/training/jobs/{job_id}/cancel')
    def cancel_training_job(
        job_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        service = training_registry()
        try:
            job = service.cancel_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, 'training job not found') from exc
        emit('owner.training.job_cancelled', device_id=device_id, job_id=job_id)
        return {'ok': True, 'job': public_job(service, job)}

    @router.get('/training/models')
    def trained_models(
        limit: int = 100,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        service = training_registry()
        return {'models': [public_model(service, model) for model in service.models(limit=limit)]}

    @router.get('/training/models/{model_id}/lineage')
    def trained_model_lineage(
        model_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        service = training_registry()
        governance = getattr(service, 'governance', None)
        if governance is None:
            raise HTTPException(503, 'training lineage unavailable')
        value = governance.lifecycle(model_id)
        if value is None:
            raise HTTPException(404, 'trained model not found')
        return {'model': value, 'exact_machine_unlearning_claimed': False}

    @router.post('/training/models/{model_id}/approve-promotion')
    def approve_model_promotion(
        model_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        service = training_registry()
        try:
            model = service.approve_promotion(model_id, owner_id='owner')
        except KeyError as exc:
            raise HTTPException(404, 'trained model not found') from exc
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit('owner.training.model_promotion_approved', device_id=device_id, model_id=model_id)
        return {
            'ok': True,
            'model': public_model(service, model),
            'activated': False,
            'message': 'Promotion approved. A configured release controller must deploy and prove the exact checkpoint before activation.',
        }

    @router.post('/evolution/candidates/{candidate_id}/implement')
    def implement_evolution_candidate(
        candidate_id: str,
        background: BackgroundTasks,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        automatic = runtime.get('automatic_code_evolution')
        if automatic is None:
            raise HTTPException(503, 'automatic code evolution is unavailable on this host')
        # This endpoint cannot approve an evolution candidate. The immutable
        # handoff must already exist from the separate owner approval flow.
        handoff = automatic.code_body.handoffs.get(candidate_id)
        if handoff is None:
            raise HTTPException(409, 'candidate has no owner-approved implementation handoff')
        existing = automatic.code_body.latest(candidate_id)
        if existing is not None:
            return {'ok': True, 'scheduled': False, 'run': existing.to_dict(), 'review_required': True, 'owner_adoption_required': True}
        background.add_task(automatic.run, candidate_id, runtime_epoch=int(runtime.get('code_worker_epoch', 0)))
        emit('owner.evolution.auto_implementation_requested', device_id=device_id, candidate_id=candidate_id)
        return {
            'ok': True,
            'scheduled': True,
            'candidate_id': candidate_id,
            'review_required': True,
            'owner_adoption_required': True,
            'automatic_merge': False,
            'automatic_deploy': False,
        }

    @router.post('/evolution/run-approved')
    def run_approved_evolution(
        background: BackgroundTasks,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        auto_runtime = runtime.get('automatic_code_evolution_runtime')
        if auto_runtime is None:
            raise HTTPException(503, 'automatic code evolution runtime unavailable')
        background.add_task(auto_runtime.run_once)
        emit('owner.evolution.auto_cycle_requested', device_id=device_id)
        return {'ok': True, 'scheduled': True, 'owner_approved_handoffs_only': True}

    @router.get('/training/candidates')
    def candidates(
        status: str | None = None,
        eligible: bool | None = None,
        limit: int = 100,
        offset: int = 0,
        include_content: bool = False,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        store = training_store()
        try:
            rows = store.list(status=status, eligible=eligible, limit=limit, offset=offset)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            'candidates': [store.public(row, include_content=include_content) for row in rows],
            'count': len(rows),
            'content_is_sanitized_candidate_data': True,
        }

    @router.post('/training/candidates/{candidate_id}/approve')
    def approve_candidate(
        candidate_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        store = training_store()
        try:
            candidate = store.approve(candidate_id)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        emit('owner.training_candidate.approved', device_id=device_id, candidate_id=candidate_id)
        return {'ok': True, 'candidate': store.public(candidate, include_content=True)}

    @router.post('/training/candidates/{candidate_id}/reject')
    def reject_candidate(
        candidate_id: str,
        body: CandidateDecisionBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        store = training_store()
        try:
            candidate = store.reject(candidate_id, body.reason)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        emit('owner.training_candidate.rejected', device_id=device_id, candidate_id=candidate_id)
        return {'ok': True, 'candidate': store.public(candidate, include_content=True)}

    @router.delete('/training/candidates/{candidate_id}')
    def tombstone_candidate(
        candidate_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        store = training_store()
        try:
            candidate = store.tombstone(candidate_id)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        emit('owner.training_candidate.tombstoned', device_id=device_id, candidate_id=candidate_id)
        return {'ok': True, 'candidate': store.public(candidate)}

    @router.post('/training/sources/tombstone')
    def tombstone_source(
        body: SourceTombstoneBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        store = training_store()
        fingerprint = store.source_fingerprint(body.source_type, body.source_id)
        count = store.tombstone_source(body.source_type, body.source_id, body.reason)
        service = training_registry()
        governance = getattr(service, 'governance', None)
        affected_models = []
        if governance is not None:
            affected_models = [item for item in governance.revoke_source(fingerprint, body.reason) if item]
        emit(
            'owner.training_source.tombstoned',
            device_id=device_id,
            source_type=body.source_type,
            candidate_count=count,
            affected_model_count=len(affected_models),
        )
        return {
            'ok': True,
            'tombstoned': count,
            'source_type': body.source_type,
            'source_fingerprint': fingerprint,
            'affected_trained_models': affected_models,
            'future_datasets_exclude_tombstoned_records': True,
            'exact_machine_unlearning_performed': False,
        }

    @router.post('/training/export')
    def export_dataset(
        body: DatasetExportBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        exporter = runtime.get('training_dataset_exporter')
        if exporter is None:
            raise HTTPException(503, 'training exporter unavailable')
        try:
            exported = exporter.export(dataset_name=body.dataset_name, limit=body.limit)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        emit('owner.training_dataset.exported', device_id=device_id, export_id=exported.export_id, records=exported.records)
        return {
            'ok': True,
            'export': exported.public(),
            'automatic_publication': False,
            'automatic_huggingface_publication': False,
        }

    return router
