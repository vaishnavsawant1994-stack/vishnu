import pytest
from fastapi import HTTPException

from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.about_api import about_router


class Registry:
    def is_active(self, device_id):
        return device_id == 'owner-device'

    def authorize(self, device_id, scope):
        return device_id == 'owner-device' and scope == 'device:read'


def endpoint():
    return next(
        route.endpoint for route in about_router({'device_registry': Registry()}).routes
        if route.path == '/iphone/api/about'
    )


def test_about_endpoint_reports_truthful_update_support_and_safe_build_metadata(monkeypatch):
    monkeypatch.setenv('VISHNU_BUILD_VERSION', '9.8.7-test')
    monkeypatch.setenv('VISHNU_BUILD_SHA', 'abc123')
    token = set_trusted_request(TrustedRequestContext('owner-device', 'session-1'))
    try:
        result = endpoint()()
    finally:
        reset_trusted_request(token)
    assert result['product'] == 'Vishnu'
    assert result['version'] == '9.8.7-test'
    assert result['build_sha'] == 'abc123'
    assert result['updates']['available'] is False
    assert result['updates']['status'] == 'managed_by_installation'


def test_about_endpoint_enforces_native_read_scope():
    token = set_trusted_request(TrustedRequestContext(
        'owner-device', 'session-1', scopes=frozenset(), auth_type='native'
    ))
    try:
        with pytest.raises(HTTPException) as denied:
            endpoint()()
        assert denied.value.status_code == 403
    finally:
        reset_trusted_request(token)
