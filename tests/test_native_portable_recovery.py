from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from devices.registry import DeviceRegistry
from recovery.disaster_recovery import DISASTER_RECOVERY_MAGIC, RECOVERY_KEY_FILE_MAGIC
from security.owner_access import OwnerAccessStore
from server.native_capability_auth import native_capability_auth_router


class _Sessions:
    native_client_redirects = {}


class _Setup:
    def __init__(self, *, ready=False):
        self.ready = ready
        self.scheduled = None

    def snapshot(self):
        return {'status': 'ready' if self.ready else 'uninitialized'}

    def schedule_disaster_recovery(self, archive, key_file, passphrase):
        assert archive.is_file()
        assert key_file.is_file()
        assert passphrase == 'correct horse battery staple'
        self.scheduled = (archive, key_file)
        return {'archive': archive.name, 'portable': True}


class _RestoredSetup:
    ready = False

    def __init__(self, owner_access, registry):
        self.owner_access = owner_access
        self.registry = registry
        self.recorded = None

    def snapshot(self):
        return {'status': 'setup_in_progress', 'mode': 'restore', 'stage': 'owner'}

    def configure_owner(self, *, first_name, last_name='', display_name=''):
        identity = self.owner_access.identity()
        assert identity['first_name'] == first_name
        assert identity['last_name'] == last_name
        assert identity['display_name'] == display_name
        return identity

    def configure_security(self, password):
        self.owner_access.set_password(password)
        return self.owner_access.regenerate_recovery_codes()

    def initialize_pending_identity(self):
        return self.owner_access.identity()

    def record_first_device(self, device_id):
        assert self.registry.is_active(device_id)
        self.recorded = device_id
        return {'device_id': device_id, 'owner_id': self.owner_access.identity()['owner_id']}


class _Events:
    def __init__(self):
        self.items = []

    def emit(self, name, **payload):
        self.items.append((name, payload))


def _runtime(tmp_path, *, ready=False):
    return {
        'pwa_sessions': _Sessions(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
        'device_registry': DeviceRegistry(tmp_path / 'devices.sqlite3'),
        'first_run_setup': _Setup(ready=ready),
        'events': _Events(),
        'android_asset_links': [],
        'apple_app_site_association': {},
    }


def _client(runtime):
    app = FastAPI()
    app.include_router(native_capability_auth_router(runtime))
    return TestClient(app, base_url='https://vishnu.example')


def test_native_portable_recovery_stages_streams_and_schedules_without_persisting_passphrase(tmp_path, monkeypatch):
    monkeypatch.setenv('PERSONAL_AI_BOOTSTRAP_SECRET', 'B' * 48)
    runtime = _runtime(tmp_path)
    client = _client(runtime)
    headers = {'X-Vishnu-Bootstrap': 'B' * 48, 'Content-Type': 'application/octet-stream'}

    archive_response = client.post(
        '/iphone/api/native/recovery-package/archive',
        content=DISASTER_RECOVERY_MAGIC + b'encrypted-bundle',
        headers=headers,
    )
    assert archive_response.status_code == 200
    session = archive_response.json()['session_id']

    key_response = client.post(
        f'/iphone/api/native/recovery-package/key?session_id={session}',
        content=RECOVERY_KEY_FILE_MAGIC + b'encrypted-key',
        headers=headers,
    )
    assert key_response.status_code == 200

    scheduled = client.post(
        '/iphone/api/native/recovery-package/schedule',
        json={
            'session_id': session,
            'bootstrap_secret': 'B' * 48,
            'passphrase': 'correct horse battery staple',
        },
    )
    assert scheduled.status_code == 200
    assert scheduled.json()['status'] == 'restart_required'
    assert runtime['first_run_setup'].scheduled is not None
    archive, key_file = runtime['first_run_setup'].scheduled
    assert archive.is_file()
    assert not key_file.exists()
    assert 'correct horse battery staple' not in archive.read_bytes().decode('latin1')
    assert not (tmp_path / '.native-recovery-staging' / session).exists()


def test_restored_runtime_can_recreate_owner_security_and_first_native_device(tmp_path, monkeypatch):
    monkeypatch.setenv('PERSONAL_AI_BOOTSTRAP_SECRET', 'B' * 48)
    owner_access = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')
    identity, _ = owner_access.initialize_identity(
        first_name='Restored', last_name='Owner', display_name='Restored Owner',
    )
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    setup = _RestoredSetup(owner_access, registry)
    runtime = {
        'pwa_sessions': _Sessions(),
        'owner_access': owner_access,
        'device_registry': registry,
        'first_run_setup': setup,
        'events': _Events(),
        'android_asset_links': [],
        'apple_app_site_association': {},
    }
    device_id = str(uuid.uuid4())
    response = _client(runtime).post(
        '/iphone/api/native/recovery-package/owner',
        json={
            'bootstrap_secret': 'B' * 48,
            'setup_claim': 'C' * 48,
            'password': 'a fresh restored owner password',
            'device_id': device_id,
            'device_token': 'D' * 48,
            'device_name': 'Replacement phone',
            'platform': 'android',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['identity']['owner_id'] == identity['owner_id']
    assert payload['identity']['vishnu_id'] == identity['vishnu_id']
    assert len(payload['recovery_codes']) >= 4
    assert owner_access.password_configured()
    assert owner_access.recovery_codes_remaining() == len(payload['recovery_codes'])
    assert registry.authenticate(device_id, 'D' * 48)
    assert registry.authorize(device_id, 'device:admin')
    assert setup.recorded == device_id


def test_native_portable_recovery_rejects_wrong_bootstrap_and_bad_formats(tmp_path, monkeypatch):
    monkeypatch.setenv('PERSONAL_AI_BOOTSTRAP_SECRET', 'B' * 48)
    runtime = _runtime(tmp_path)
    client = _client(runtime)

    wrong = client.post(
        '/iphone/api/native/recovery-package/archive',
        content=DISASTER_RECOVERY_MAGIC + b'x',
        headers={'X-Vishnu-Bootstrap': 'X' * 48},
    )
    assert wrong.status_code == 401

    malformed = client.post(
        '/iphone/api/native/recovery-package/archive',
        content=b'not-a-vishnu-recovery-bundle',
        headers={'X-Vishnu-Bootstrap': 'B' * 48},
    )
    assert malformed.status_code == 422


def test_native_portable_recovery_rejects_oversized_key_and_initialized_target(tmp_path, monkeypatch):
    monkeypatch.setenv('PERSONAL_AI_BOOTSTRAP_SECRET', 'B' * 48)
    runtime = _runtime(tmp_path)
    client = _client(runtime)
    headers = {'X-Vishnu-Bootstrap': 'B' * 48}
    archive_response = client.post(
        '/iphone/api/native/recovery-package/archive',
        content=DISASTER_RECOVERY_MAGIC + b'x',
        headers=headers,
    )
    session = archive_response.json()['session_id']
    oversized = client.post(
        f'/iphone/api/native/recovery-package/key?session_id={session}',
        content=RECOVERY_KEY_FILE_MAGIC + (b'x' * 8192),
        headers=headers,
    )
    assert oversized.status_code == 413

    ready_client = _client(_runtime(tmp_path / 'ready', ready=True))
    ready = ready_client.post(
        '/iphone/api/native/recovery-package/archive',
        content=DISASTER_RECOVERY_MAGIC + b'x',
        headers=headers,
    )
    assert ready.status_code == 409