from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.preferences import Preferences
from onboarding.first_run import FirstRunCoordinator, SetupMode, SetupStatus
from security.owner_access import OwnerAccessStore


class FakeModels:
    def __init__(self):
        self.privacy = None
        self.default = None
        self.connected = None

    def status(self):
        return {'state': 'available' if self.default else 'unconfigured'}

    def set_owner_privacy(self, mode):
        self.privacy = mode

    def set_default_provider(self, provider_id):
        self.default = provider_id
        return {'provider': provider_id, 'configured': True}

    def connect_owner_provider(self, provider_id, api_key, model):
        self.connected = (provider_id, api_key, model)
        return {'provider': provider_id, 'model': model, 'configured': True}


class FakeTools:
    def __init__(self):
        self.mode = None

    def set_autonomy_mode(self, mode):
        self.mode = mode


class FakeDevices:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def list(self):
        return list(self.rows)


class FakeBackups:
    def __init__(self):
        self.inspected = None

    def inspect(self, path):
        self.inspected = path
        return {'encrypted': True, 'created_at': 1234.5, 'files': []}


def runtime(tmp_path, *, devices=None):
    return {
        'preferences': Preferences(tmp_path / 'preferences.json'),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
        'models': FakeModels(),
        'tools': FakeTools(),
        'device_registry': FakeDevices(devices),
        'backups': FakeBackups(),
    }


def test_fresh_install_requires_setup_and_completes_without_storing_secrets(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)

    assert coordinator.should_run() is True
    coordinator.begin(SetupMode.CREATE)
    coordinator.configure_owner(first_name='Vishnu', last_name='Owner', display_name='Owner')
    codes = coordinator.configure_security('correct horse battery staple')
    assert coordinator.snapshot()['stage'] == 'recovery'
    coordinator.confirm_recovery_codes_saved()
    coordinator.configure_preferences(
        privacy_mode='local_preferred',
        autonomy_mode='ask',
        memory_enabled=True,
    )
    coordinator.configure_model(
        provider_id='openai',
        model='gpt-test',
        api_key='sk-test-secret-value-1234567890',
    )
    state = coordinator.complete()

    assert state['status'] == SetupStatus.READY.value
    assert rt['preferences'].get('onboarding_complete') is True
    assert rt['models'].privacy == 'local_preferred'
    assert rt['tools'].mode == 'ask'
    assert rt['models'].connected[0] == 'openai'
    assert len(codes) >= 4
    identity = rt['owner_access'].identity()
    assert identity is not None
    assert identity['owner_id'].startswith('OWNER-')
    assert identity['vishnu_id'].startswith('VISHNU-')
    assert identity['display_name'] == 'Owner'
    assert state['identity_version'] == 1

    persisted = (tmp_path / FirstRunCoordinator.STATE_FILE).read_text(encoding='utf-8')
    assert 'correct horse battery staple' not in persisted
    assert 'sk-test-secret-value-1234567890' not in persisted
    for code in codes:
        assert code not in persisted


def test_setup_cannot_complete_before_recovery_codes_are_confirmed(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    coordinator.configure_owner(first_name='Owner')
    coordinator.configure_security('correct horse battery staple')

    with pytest.raises(RuntimeError, match='recovery'):
        coordinator.configure_preferences(
            privacy_mode='local_preferred', autonomy_mode='ask', memory_enabled=True
        )
    with pytest.raises(RuntimeError, match='Recovery codes'):
        coordinator.complete()


def test_setup_cannot_complete_if_all_recovery_codes_were_consumed(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    coordinator.configure_owner(first_name='Owner')
    codes = coordinator.configure_security('correct horse battery staple')
    coordinator.confirm_recovery_codes_saved()
    coordinator.configure_preferences(privacy_mode='local_preferred', autonomy_mode='ask')
    coordinator.skip_model_configuration()
    for code in codes:
        assert rt['owner_access'].consume_recovery_code(code)

    with pytest.raises(RuntimeError, match='unused recovery code'):
        coordinator.complete()


def test_regenerating_security_invalidates_prior_recovery_confirmation(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    coordinator.configure_owner(first_name='Owner')
    coordinator.configure_security('correct horse battery staple')
    coordinator.confirm_recovery_codes_saved()
    assert 'recovery_saved' in coordinator.snapshot()['completed_steps']

    coordinator.configure_security('another correct horse battery staple')
    state = coordinator.snapshot()
    assert state['stage'] == 'recovery'
    assert 'recovery_saved' not in state['completed_steps']


def test_local_provider_needs_no_api_key(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    result = coordinator.configure_model(provider_id='local')
    assert result['provider'] == 'local'
    assert rt['models'].default == 'local'


def test_existing_trusted_install_is_migrated_without_forcing_wizard(tmp_path):
    rt = runtime(tmp_path, devices=[{'id': 'existing-device'}])
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)

    assert coordinator.should_run() is False
    state = coordinator.snapshot()
    assert state['status'] == SetupStatus.READY.value
    assert state['migrated_legacy_install'] is True
    assert rt['preferences'].get('onboarding_complete') is True
    assert rt['owner_access'].identity() is not None


def test_identity_creation_is_idempotent_and_race_safe(tmp_path):
    store = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')

    def initialize(_):
        return store.initialize_identity(
            first_name='Vaishnav', last_name='Sawant', display_name='Vishnu Owner'
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(initialize, range(16)))

    identities = [identity for identity, _created in results]
    assert len({item['owner_id'] for item in identities}) == 1
    assert len({item['vishnu_id'] for item in identities}) == 1
    assert sum(created for _identity, created in results) == 1


def test_initialized_install_cannot_start_create_again(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    coordinator.configure_owner(first_name='Owner')
    coordinator.configure_security('correct horse battery staple')
    coordinator.confirm_recovery_codes_saved()
    coordinator.configure_preferences(privacy_mode='local_preferred', autonomy_mode='ask')
    coordinator.skip_model_configuration()
    coordinator.complete()

    with pytest.raises(RuntimeError, match='already initialized'):
        coordinator.begin('create')


def test_partial_new_setup_is_never_promoted_as_legacy_install(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('create')
    coordinator.configure_owner(first_name='Owner')
    coordinator.configure_security('correct horse battery staple')

    restarted = FirstRunCoordinator(tmp_path, runtime=rt)
    assert restarted.should_run() is True
    state = restarted.snapshot()
    assert state['status'] == SetupStatus.SETUP_IN_PROGRESS.value
    assert state['stage'] == 'recovery'
    assert state['migrated_legacy_install'] is False


def test_restore_is_validated_and_scheduled_for_next_process_start(tmp_path):
    archive = tmp_path / 'owner.paibackup'
    archive.write_bytes(b'not-read-by-fake')
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('restore')

    result = coordinator.schedule_restore(archive)

    assert result['archive'] == 'owner.paibackup'
    assert result['encrypted'] is True
    state = coordinator.snapshot()
    assert state['status'] == SetupStatus.RESTORING.value
    assert state['stage'] == 'restart_required'
    pending = json.loads((tmp_path / FirstRunCoordinator.PENDING_RESTORE_FILE).read_text(encoding='utf-8'))
    assert pending['path'] == str(archive.resolve())


def test_connect_mode_does_not_mark_local_install_ready(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('connect')
    coordinator.mark_connect_pending('https://vishnu.example.test/path?ignored=yes#fragment')

    assert coordinator.ready is False
    state = coordinator.snapshot()
    assert state['status'] == SetupStatus.CONNECT_PENDING.value
    assert state['connect_url'] == 'https://vishnu.example.test'


def test_connect_url_rejects_embedded_credentials_and_insecure_remote_http(tmp_path):
    rt = runtime(tmp_path)
    coordinator = FirstRunCoordinator(tmp_path, runtime=rt)
    coordinator.begin('connect')

    with pytest.raises(ValueError, match='credentials'):
        coordinator.mark_connect_pending('https://owner:secret@vishnu.example.test')
    with pytest.raises(ValueError, match='HTTPS'):
        coordinator.mark_connect_pending('http://vishnu.example.test')

    state = coordinator.mark_connect_pending('http://localhost:8766')
    assert state['connect_url'] == 'http://localhost:8766'
