from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, HTTPException
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
    """Owner-only PWA surface for optional intelligence and training governance.

    This router deliberately has no provider-key mutation and no dataset upload
    endpoint. It operates on the same canonical services used by the desktop
    Owner AI surface and therefore cannot bypass Vishnu policy or execution
    authority.
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
        # PwaSessionMiddleware establishes current_trusted_request in hosted
        # operation. Compatibility/local test runtimes may omit pwa_sessions.
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
        return {
            'settings': settings.public(),
            'performance': [item.public() for item in performance.profiles()] if performance is not None else [],
            'training': store.stats(),
            'runtime': status.get('advanced_intelligence', {}),
            'model_output_authority': False,
            'automatic_publication': False,
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
        count = training_store().tombstone_source(body.source_type, body.source_id, body.reason)
        emit('owner.training_source.tombstoned', device_id=device_id, source_type=body.source_type, candidate_count=count)
        return {'ok': True, 'tombstoned': count, 'source_type': body.source_type}

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
        exported = exporter.export(dataset_name=body.dataset_name, limit=body.limit)
        emit('owner.training_dataset.exported', device_id=device_id, export_id=exported.export_id, records=exported.records)
        return {'ok': True, 'export': exported.public()}

    return router
