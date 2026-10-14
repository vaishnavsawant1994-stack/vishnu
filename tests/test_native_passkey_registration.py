from __future__ import annotations

import base64
import json
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from devices.registry import DeviceRegistry
from security.owner_access import OwnerAccessStore
from server.native_capability_auth import (
    _android_passkey_origins,
    _ios_passkey_enabled,
    native_capability_auth_router,
)


class _Sessions:
    native_client_redirects = {}


class _Events:
    def __init__(self):
        self.items = []

    def emit(self, name, **payload):
        self.items.append((name, payload))


def _fingerprint() -> str:
    return ':'.join(f'{value:02X}' for value in range(32))


def _asset_links():
    return [{
        'relation': ['delegate_permission/common.get_login_creds'],
        'target': {
            'namespace': 'android_app',
            'package_name': 'ai.personal.companion',
            'sha256_cert_fingerprints': [_fingerprint()],
        },
    }]


def _runtime(tmp_path, *, android=True, ios=True):
    owner_access = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')
    owner_access.initialize_identity(
        first_name='Owner', last_name='', display_name='Vishnu Owner',
    )
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    token = 'T' * 48
    device_id = str(uuid.uuid4())
    registry.enroll_with_credential(device_id, token, 'Phone', 'android')
    registry.set_permissions(device_id, registry.OWNER_SCOPES)
    events = _Events()
    runtime = {
        'pwa_sessions': _Sessions(),
        'owner_access': owner_access,
        'device_registry': registry,
        'events': events,
        'android_asset_links': _asset_links() if android else [],
        'apple_app_site_association': {
            'webcredentials': {'apps': ['TEAMID.ai.personal.companion']},
        } if ios else {},
    }
    return runtime, device_id, token


def _client(runtime):
    app = FastAPI()
    app.include_router(native_capability_auth_router(runtime))
    return TestClient(app)


def _headers():
    return {'host': 'vishnu.example', 'x-forwarded-proto': 'https'}


def test_android_origins_derive_only_from_configured_signing_fingerprints():
    digest = bytes(range(32))
    encoded = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    assert _android_passkey_origins(_asset_links()) == {
        f'android:apk-key-hash:{encoded}',
    }
    assert _android_passkey_origins([{
        'relation': ['delegate_permission/common.handle_all_urls'],
        'target': {
            'namespace': 'android_app',
            'package_name': 'ai.personal.companion',
            'sha256_cert_fingerprints': [_fingerprint()],
        },
    }]) == set()


def test_ios_passkeys_require_explicit_webcredentials_association():
    assert _ios_passkey_enabled({
        'webcredentials': {'apps': ['TEAMID.ai.personal.companion']},
    }) is True
    assert _ios_passkey_enabled({
        'applinks': {'details': [{'appIDs': ['TEAMID.ai.personal.companion']}]},
    }) is False


def test_native_passkey_options_require_owner_scoped_device_and_android_association(tmp_path):
    runtime, device_id, token = _runtime(tmp_path, android=False)
    client = _client(runtime)
    body = {'device_id': device_id, 'device_token': token, 'platform': 'android'}
    response = client.post('/iphone/api/native/passkeys/register/options', json=body, headers=_headers())
    assert response.status_code == 409
    assert 'Digital Asset Link' in response.text

    runtime['android_asset_links'] = _asset_links()
    response = client.post('/iphone/api/native/passkeys/register/options', json=body, headers=_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload['rp_id'] == 'vishnu.example'
    assert payload['public_key']['rp']['id'] == 'vishnu.example'
    assert payload['public_key']['authenticatorSelection']['userVerification'] == 'required'
    challenge = runtime['owner_access'].consume_challenge(
        payload['challenge_id'], 'native_registration', device_id=device_id,
    )
    assert challenge is not None
    assert challenge['origin'] == 'native:android'


def test_native_passkey_options_reject_wrong_device_secret(tmp_path):
    runtime, device_id, _ = _runtime(tmp_path)
    response = _client(runtime).post(
        '/iphone/api/native/passkeys/register/options',
        json={'device_id': device_id, 'device_token': 'X' * 48, 'platform': 'android'},
        headers=_headers(),
    )
    assert response.status_code == 401


def test_native_passkey_options_reject_platform_spoofing(tmp_path):
    runtime, device_id, token = _runtime(tmp_path)
    response = _client(runtime).post(
        '/iphone/api/native/passkeys/register/options',
        json={'device_id': device_id, 'device_token': token, 'platform': 'ios'},
        headers=_headers(),
    )
    assert response.status_code == 403


def test_android_completion_rejects_origin_not_in_asset_links_before_crypto_verification(tmp_path):
    runtime, device_id, token = _runtime(tmp_path)
    client = _client(runtime)
    options = client.post(
        '/iphone/api/native/passkeys/register/options',
        json={'device_id': device_id, 'device_token': token, 'platform': 'android'},
        headers=_headers(),
    ).json()
    client_data = base64.urlsafe_b64encode(json.dumps({
        'type': 'webauthn.create',
        'challenge': 'not-used-because-origin-fails-first',
        'origin': 'https://attacker.example',
    }).encode()).decode().rstrip('=')
    response = client.post(
        '/iphone/api/native/passkeys/register/complete',
        json={
            'device_id': device_id,
            'device_token': token,
            'platform': 'android',
            'challenge_id': options['challenge_id'],
            'credential': {
                'id': 'fake',
                'rawId': 'fake',
                'type': 'public-key',
                'response': {'clientDataJSON': client_data},
            },
            'name': 'Android passkey',
        },
        headers=_headers(),
    )
    assert response.status_code == 401
    assert 'origin is not authorized' in response.text


def test_native_passkey_options_require_https(tmp_path):
    runtime, device_id, token = _runtime(tmp_path)
    response = _client(runtime).post(
        '/iphone/api/native/passkeys/register/options',
        json={'device_id': device_id, 'device_token': token, 'platform': 'android'},
        headers={'host': 'vishnu.example', 'x-forwarded-proto': 'http'},
    )
    assert response.status_code == 400
    assert 'requires HTTPS' in response.text
