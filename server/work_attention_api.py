from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from future_intelligence.work_orchestration.living_projection import LivingAgentWorkProjection
from future_intelligence.work_orchestration.review_attention import ReviewAwareWorkAttentionService
from security.request_context import current_trusted_request
from sensorium.live_work import SensoriumLiveWorkProjection, overlay_sensorium_living


def work_attention_router(runtime: dict, store) -> APIRouter:
    """Read-only owner attention projection; existing authorities own decisions."""
    router = APIRouter(prefix="/iphone/api/work/attention", tags=["work-attention"])
    service = ReviewAwareWorkAttentionService(runtime, store)
    registry = runtime["device_registry"]
    sensorium_live_work = runtime.get("sensorium_live_work")
    if sensorium_live_work is None and runtime.get("events") is not None:
        sensorium_live_work = SensoriumLiveWorkProjection(runtime["events"])
        runtime["sensorium_live_work"] = sensorium_live_work

    def require_owner():
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, "Trusted owner session required")
        if not registry.is_active(context.device_id):
            raise HTTPException(401, "Trusted device is revoked")
        if hasattr(registry, "authorize") and not registry.authorize(context.device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to inspect governed Work attention")
        return context

    @router.get("")
    def attention_list(limit: int = Query(default=100, ge=1, le=200)):
        context = require_owner()
        try:
            snapshot = service.summary(
                owner_id="owner",
                device_id=context.device_id,
                session_id=context.session_id,
                limit=limit,
            )
            work_snapshot = service.work_service.summary(work_order_limit=500)
            canonical_living = LivingAgentWorkProjection.project(work_snapshot, snapshot)
            sensorium_snapshot = sensorium_live_work.snapshot(limit=1) if sensorium_live_work is not None else None
            snapshot["living"] = overlay_sensorium_living(canonical_living, sensorium_snapshot)
            return snapshot
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/{attention_id}")
    def attention_detail(attention_id: str):
        context = require_owner()
        try:
            item = service.detail(
                attention_id,
                owner_id="owner",
                device_id=context.device_id,
                session_id=context.session_id,
            )
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        if item is None:
            raise HTTPException(404, "Attention item not found")
        return item

    return router
