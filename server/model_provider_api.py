from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from server.agent_workforce_api import agent_workforce_router
from server.sensorium_api import sensorium_router


class ProviderCredentialBody(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    api_key: str = Field(min_length=16, max_length=4096)
    model: str | None = Field(default=None, max_length=200)


class ProviderModelBody(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class IntelligenceSettingsBody(BaseModel):
    enabled: bool | None = None
    mode: str | None = Field(default=None, max_length=32)
    auto_escalation: bool | None = None
    verification_enabled: bool | None = None
    training_capture: bool | None = None
    performance_learning: bool | None = None
    max_models: int | None = Field(default=None, ge=1, le=5)
    latency_preference: str | None = Field(default=None, max_length=32)
    max_cost_per_request: float | None = Field(default=None, gt=0, le=10000)


class TrainingDecisionBody(BaseModel):
    reason: str = Field(default='owner_or_policy_rejected', min_length=1, max_length=300)


class TrainingSourceTombstoneBody(BaseModel):
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=1000)
    reason: str = Field(default='source_deleted_or_consent_revoked', min_length=1, max_length=300)


class TrainingExportBody(BaseModel):
    dataset_name: str = Field(default='vishnu-general', min_length=1, max_length=80)
    limit: int = Field(default=10000, ge=1, le=10000)


class WorkProposalBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    sensitivity: str = Field(default='internal', max_length=40)
    context: str = Field(default='', max_length=16000)
    execution_id: str | None = Field(default=None, max_length=200)
    attempt_id: str | None = Field(default=None, max_length=200)


def model_provider_router(runtime) -> APIRouter:
    router = APIRouter(prefix='/owner/ai', tags=['owner-ai'])

    def local_only(request: Request):
        host = request.client.host if request.client else ''
        if host not in {'127.0.0.1', '::1'}:
            raise HTTPException(403, 'Local owner operation')

    def models():
        value = runtime.get('models') if runtime else None
        if value is None:
            raise HTTPException(503, 'model router unavailable')
        return value

    def intelligence_settings():
        value = runtime.get('intelligence_settings') if runtime else None
        if value is None:
            raise HTTPException(503, 'intelligence settings unavailable')
        return value

    def training_store():
        value = runtime.get('training_candidate_store') if runtime else None
        if value is None:
            raise HTTPException(503, 'training candidate store unavailable')
        return value

    @router.get('/status')
    def status(request: Request):
        local_only(request)
        return models().status()

    @router.get('/providers')
    def providers(request: Request):
        local_only(request)
        service = models()
        return {
            'providers': [provider.public() for provider in service.providers.values()],
            'default_provider': service.primary,
            'fallback_providers': list(service.fallbacks),
            'privacy_mode': getattr(service, 'owner_privacy', None),
            'policies': [policy.policy_id for policy in getattr(service, 'policies', ()).all()] if hasattr(service, 'policies') else [],
        }

    @router.post('/providers/test')
    def test_provider(body: ProviderCredentialBody, request: Request):
        local_only(request)
        try:
            return models().test_owner_provider(body.provider_id, body.api_key)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post('/providers/connect')
    def connect_provider(body: ProviderCredentialBody, request: Request):
        local_only(request)
        if not body.model:
            raise HTTPException(422, 'model is required when connecting a provider')
        try:
            return models().connect_owner_provider(body.provider_id, body.api_key, body.model)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get('/providers/{provider_id}/models')
    def provider_models(provider_id: str, request: Request):
        local_only(request)
        try:
            return models().owner_provider_models(provider_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.patch('/providers/{provider_id}/model')
    def provider_model(provider_id: str, body: ProviderModelBody, request: Request):
        local_only(request)
        try:
            return models().set_owner_provider_model(provider_id, body.model)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post('/providers/{provider_id}/default')
    def provider_default(provider_id: str, request: Request):
        local_only(request)
        try:
            return models().set_default_provider(provider_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete('/providers/{provider_id}')
    def disconnect_provider(provider_id: str, request: Request):
        local_only(request)
        try:
            return models().disconnect_owner_provider(provider_id)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get('/intelligence')
    def intelligence_status(request: Request):
        local_only(request)
        settings = intelligence_settings().snapshot()
        performance = runtime.get('model_performance') if runtime else None
        store = training_store()
        return {
            'settings': settings.public(),
            'performance': [profile.public() for profile in performance.profiles()] if performance is not None else [],
            'training': store.stats(),
            'runtime': models().status().get('advanced_intelligence', {}),
            'model_output_authority': False,
        }

    @router.patch('/intelligence')
    def update_intelligence(body: IntelligenceSettingsBody, request: Request):
        local_only(request)
        values = body.model_dump(exclude_unset=True)
        try:
            snapshot = intelligence_settings().update(**values)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return snapshot.public()

    @router.get('/training/stats')
    def training_stats(request: Request):
        local_only(request)
        return training_store().stats()

    @router.get('/training/candidates')
    def training_candidates(
        request: Request,
        status: str | None = None,
        eligible: bool | None = None,
        limit: int = 200,
        offset: int = 0,
        include_content: bool = False,
    ):
        local_only(request)
        try:
            rows = training_store().list(status=status, eligible=eligible, limit=limit, offset=offset)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            'candidates': [training_store().public(row, include_content=include_content) for row in rows],
            'count': len(rows),
            'content_is_sanitized_candidate_data': True,
        }

    @router.post('/training/candidates/{candidate_id}/approve')
    def approve_training_candidate(candidate_id: str, request: Request):
        local_only(request)
        try:
            candidate = training_store().approve(candidate_id)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return training_store().public(candidate, include_content=True)

    @router.post('/training/candidates/{candidate_id}/reject')
    def reject_training_candidate(candidate_id: str, body: TrainingDecisionBody, request: Request):
        local_only(request)
        try:
            candidate = training_store().reject(candidate_id, body.reason)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        return training_store().public(candidate, include_content=True)

    @router.delete('/training/candidates/{candidate_id}')
    def tombstone_training_candidate(candidate_id: str, request: Request):
        local_only(request)
        try:
            candidate = training_store().tombstone(candidate_id)
        except KeyError as exc:
            raise HTTPException(404, 'training candidate not found') from exc
        return training_store().public(candidate, include_content=False)

    @router.post('/training/sources/tombstone')
    def tombstone_training_source(body: TrainingSourceTombstoneBody, request: Request):
        local_only(request)
        count = training_store().tombstone_source(body.source_type, body.source_id, body.reason)
        return {'tombstoned': count, 'source_type': body.source_type}

    @router.post('/training/export')
    def export_training_dataset(body: TrainingExportBody, request: Request):
        local_only(request)
        exporter = runtime.get('training_dataset_exporter') if runtime else None
        if exporter is None:
            raise HTTPException(503, 'training exporter unavailable')
        exported = exporter.export(dataset_name=body.dataset_name, limit=body.limit)
        return exported.public()

    @router.get('/work/{work_order_id}/intelligence')
    def work_intelligence(work_order_id: str, request: Request):
        local_only(request)
        service = runtime.get('worker_intelligence') if runtime else None
        if service is None:
            raise HTTPException(503, 'worker intelligence unavailable')
        assignment = service.store.get_intelligence_assignment(work_order_id)
        if assignment is None:
            try:
                assignment = service.ensure_assignment(work_order_id)
            except KeyError as exc:
                raise HTTPException(404, 'work order not found') from exc
        return {
            'assignment': assignment,
            'handoffs': service.store.list_model_handoffs(work_order_id),
        }

    @router.post('/work/{work_order_id}/propose')
    def work_propose(work_order_id: str, body: WorkProposalBody, request: Request):
        local_only(request)
        service = runtime.get('worker_intelligence') if runtime else None
        if service is None:
            raise HTTPException(503, 'worker intelligence unavailable')
        try:
            response = service.invoke(
                work_order_id,
                body.prompt,
                execution_id=body.execution_id,
                attempt_id=body.attempt_id,
                sensitivity=body.sensitivity,
                context=body.context,
            )
        except KeyError as exc:
            raise HTTPException(404, 'work order not found') from exc
        return {
            'request_id': response.request_id,
            'provider': response.provider_id,
            'model': response.model_id,
            'content': response.content,
            'usage': response.usage.__dict__,
            'model_output_authority': False,
        }

    # Workforce lives under the already loopback-only Owner AI surface on the
    # desktop control server. Hosted/PWA registration uses the same router with
    # its trusted owner-session boundary rather than weakening this one.
    router.include_router(agent_workforce_router(runtime, prefix='/agents', require_loopback=True))
    router.include_router(sensorium_router(runtime))
    return router
