from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.home_state_projection import project_home_state
from security.request_context import current_trusted_request
from server.content_ingestion_api import content_ingestion_router


def runtime_state_router(runtime):
    """Authenticated runtime projection plus the canonical production content-ingestion surface."""
    router = APIRouter(tags=['runtime-state'])
    registry = runtime['device_registry']
    authority = runtime['events'].runtime_state

    def require_owner():
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not registry.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(context.device_id, 'ai:chat'):
            raise HTTPException(403, 'This device is not permitted to observe runtime state')
        return context

    @router.get('/iphone/api/runtime-state')
    def snapshot():
        require_owner()
        # Home receives only the presentation-safe projection. Runtime reason/context,
        # prompts, tool payloads, memory/knowledge contents, and credentials stay server-side.
        return project_home_state(authority.snapshot()).as_dict()

    # This child router is already mounted anywhere runtime_state_router is mounted,
    # keeping web/PWA/mobile/desktop on one trusted-owner content-ingestion API.
    router.include_router(content_ingestion_router(runtime))
    return router
