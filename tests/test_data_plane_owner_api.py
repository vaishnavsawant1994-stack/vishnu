from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from data_plane.runtime import get_data_plane
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.data_plane_owner_api import DataPlaneSettingsUpdate, data_plane_owner_router


class Registry:
    def __init__(self, allowed=True):
        self.allowed = allowed

    def is_active(self, device_id):
        return device_id == 'owner-device'

    def authorize(self, device_id, scope):
        return self.allowed and device_id == 'owner-device'


def route_endpoint(router, path, method):
    return next(
        route.endpoint for route in router.routes
        if route.path == path and method in route.methods
    )


def trusted_context(*, auth_type='browser', scopes=None):
    return TrustedRequestContext('owner-device', 'session-1', scopes=scopes, auth_type=auth_type)


def test_data_plane_owner_overview_is_owner_gated_and_secret_free(tmp_path):
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'device_registry': Registry(),
    }
    router = data_plane_owner_router(runtime)
    endpoint = route_endpoint(router, '/iphone/api/data-plane/overview', 'GET')
    with pytest.raises(HTTPException) as missing:
        endpoint()
    assert missing.value.status_code == 401

    token = set_trusted_request(trusted_context())
    try:
        result = endpoint()
    finally:
        reset_trusted_request(token)

    assert result['settings']['default_policy'] == 'progress_only'
    assert result['counts'] == {'items': 0, 'locations': 0, 'pending_events': 0, 'conflicts': 0}
    assert all('credential_ref' not in provider for provider in result['providers'])


def test_data_plane_owner_policy_update_persists_and_requires_admin_scope(tmp_path):
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'device_registry': Registry(),
    }
    router = data_plane_owner_router(runtime)
    endpoint = route_endpoint(router, '/iphone/api/data-plane/settings', 'PUT')
    body = DataPlaneSettingsUpdate(default_policy='device_only')

    token = set_trusted_request(trusted_context(auth_type='native', scopes=frozenset({'device:read'})))
    try:
        with pytest.raises(HTTPException) as denied:
            endpoint(body)
        assert denied.value.status_code == 403
    finally:
        reset_trusted_request(token)

    token = set_trusted_request(trusted_context())
    try:
        result = endpoint(body)
    finally:
        reset_trusted_request(token)

    assert result['settings']['default_policy'] == 'device_only'
    assert get_data_plane(runtime).settings()['default_policy'] == 'device_only'


def test_data_plane_owner_rejects_revoked_device(tmp_path):
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'device_registry': Registry(),
    }
    runtime['device_registry'].is_active = lambda device_id: False
    endpoint = route_endpoint(data_plane_owner_router(runtime), '/iphone/api/data-plane/overview', 'GET')
    token = set_trusted_request(trusted_context())
    try:
        with pytest.raises(HTTPException) as denied:
            endpoint()
        assert denied.value.status_code == 401
    finally:
        reset_trusted_request(token)
