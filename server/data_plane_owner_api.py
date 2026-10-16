from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from data_plane.runtime import get_data_plane
from security.request_context import current_trusted_request


class DataPlaneSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    default_policy: Literal['device_only', 'progress_only', 'sync_everywhere', 'on_demand']


def data_plane_owner_router(runtime):
    """Owner-safe view and limited settings for Vishnu's canonical Data Plane."""
    router = APIRouter(prefix='/iphone/api/data-plane', tags=['data-plane-owner'])
    registry = runtime['device_registry']

    def require_owner(scope: str):
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not registry.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if context.auth_type == 'native' and (context.scopes is None or scope not in context.scopes):
            raise HTTPException(403, f'This native session is not scoped for {scope}')
        if not registry.authorize(context.device_id, scope):
            raise HTTPException(403, f'This device is not permitted to use {scope}')
        return context

    def manager():
        value = get_data_plane(runtime)
        if value is None:
            raise HTTPException(503, 'Local-first storage authority is unavailable')
        return value

    @router.get('/overview')
    def overview():
        require_owner('device:read')
        data = manager()
        details = data.diagnostics()
        return {
            'settings': data.settings(),
            'counts': {
                'items': int(details.get('items', 0)),
                'locations': int(details.get('locations', 0)),
                'pending_events': int(details.get('events', 0)),
                'conflicts': int(details.get('conflicts', 0)),
            },
            'providers': [
                {
                    'provider_id': item.get('provider_id'),
                    'label': item.get('label') or item.get('provider_id'),
                    'available': bool(item.get('available')),
                    'configured': bool(item.get('configured')),
                    'enabled': bool(item.get('enabled')),
                    'effective': bool(item.get('available')),
                    'reason': item.get('reason'),
                }
                for item in data.provider_inventory()
            ],
        }

    @router.put('/settings')
    def update_settings(body: DataPlaneSettingsUpdate):
        require_owner('device:admin')
        data = manager()
        try:
            # This is the default for newly governed objects. Existing object
            # residency is unchanged and requires its owning domain's migration flow.
            return {'settings': data.update_settings(default_policy=body.default_policy)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
