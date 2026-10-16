from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from data_plane.runtime import get_data_plane
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.about_api import about_router


ROOT = Path(__file__).resolve().parents[1]


class Registry:
    def is_active(self, device_id):
        return device_id == 'owner-device'

    def authorize(self, device_id, scope):
        return device_id == 'owner-device' and scope in {'device:read', 'device:admin'}


def runtime(tmp_path=None):
    value = {'device_registry': Registry()}
    if tmp_path is not None:
        value['settings'] = SimpleNamespace(data_dir=tmp_path)
    return value


def route(runtime_value, path):
    return next(item.endpoint for item in about_router(runtime_value).routes if item.path == path)


def endpoint():
    return route(runtime(), '/iphone/api/about')


def trusted():
    return set_trusted_request(TrustedRequestContext('owner-device', 'session-1'))


def test_about_endpoint_reports_truthful_update_support_and_safe_build_metadata(monkeypatch):
    monkeypatch.setenv('VISHNU_BUILD_VERSION', '9.8.7-test')
    monkeypatch.setenv('VISHNU_BUILD_SHA', 'abc123')
    token = trusted()
    try:
        result = endpoint()()
    finally:
        reset_trusted_request(token)
    assert result['product'] == 'Vishnu'
    assert result['version'] == '9.8.7-test'
    assert result['build_sha'] == 'abc123'
    assert result['license'] == 'Proprietary — All Rights Reserved'
    assert result['updates']['available'] is False
    assert result['updates']['status'] == 'managed_by_installation'
    assert 'signed updater' in result['updates']['message']


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


def test_storage_provider_detail_page_is_owner_gated_and_secret_free(tmp_path):
    rt = runtime(tmp_path)
    plane = get_data_plane(rt)
    plane.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    plane.configure_provider(
        's3', enabled=True, credential_ref='vault:storage/s3',
        config={'bucket': 'owner-backups', 'region': 'eu-central-1'}, verified=True,
    )
    endpoint = route(rt, '/iphone/api/about/storage-provider/{provider_id}')
    token = trusted()
    try:
        response = endpoint('s3')
    finally:
        reset_trusted_request(token)
    body = response.body.decode('utf-8')
    assert 'Connected Storage Provider' in body
    assert 'owner-backups' in body
    assert 'eu-central-1' in body
    assert 'vault:storage/s3' not in body
    assert 'credential_ref' not in body


def test_sensorium_owner_page_reports_saved_evidence_only(tmp_path):
    rt = runtime(tmp_path)
    endpoint = route(rt, '/iphone/api/about/sensorium/status')
    token = trusted()
    try:
        result = endpoint()
    finally:
        reset_trusted_request(token)
    assert len(result['providers']) == 3
    assert result['live_availability_verified'] is False
    assert result['physical_device'] is False
    assert result['execution_authority'] is False
    assert 'does not probe a live device' in result['message']


def test_updates_release_page_is_truthful_without_fake_updater(tmp_path, monkeypatch):
    monkeypatch.setenv('VISHNU_BUILD_VERSION', '9.8.7-test')
    rt = runtime(tmp_path)
    endpoint = route(rt, '/iphone/api/about/updates')
    token = trusted()
    try:
        response = endpoint()
    finally:
        reset_trusted_request(token)
    body = response.body.decode('utf-8')
    assert 'Updates &amp; Release' in body or 'Updates & Release' in body
    assert '9.8.7-test' in body
    assert 'Managed by platform / installation' in body
    assert 'Signed in-app updater' in body
    assert 'Not connected' in body
    assert 'Install update</' not in body


def test_about_notices_page_exposes_proprietary_identity(tmp_path):
    endpoint = route(runtime(tmp_path), '/iphone/api/about/notices')
    token = trusted()
    try:
        response = endpoint()
    finally:
        reset_trusted_request(token)
    body = response.body.decode('utf-8')
    assert 'Proprietary — All Rights Reserved' in body
    assert 'Third-party notices' in body
    assert 'Updates &amp; Release' in body or 'Updates & Release' in body


def test_about_screen_is_reachable_and_does_not_offer_a_fake_update_action():
    pwa = (ROOT / 'pwa/index.html').read_text(encoding='utf-8')
    cloud_app = (ROOT / 'server/cloud_app.py').read_text(encoding='utf-8')

    assert "['about','About & Updates']" in pwa
    assert "api('/about')" in pwa
    assert "row('about','About & Updates'" in pwa
    assert "managed_by_installation" in (ROOT / 'server/about_api.py').read_text(encoding='utf-8')
    assert 'app.include_router(about_router(runtime))' in cloud_app
    assert 'Check for updates' not in pwa
    assert 'Install update' not in pwa
