from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.envelopes import EnvelopeKeyManager
from data_plane.provider_adapters import EncryptedProviderStore, ProviderAdapterError
from data_plane.provider_bridge import connect_runtime_provider, reconcile_runtime_providers
from data_plane.provider_bridges import GovernedProviderAdapterFactory


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


class FakeDrive:
    MAX_FILE_BYTES = 10 * 1024 * 1024

    def __init__(self):
        self.files = {}
        self.contents = {}
        self.next_id = 1

    @staticmethod
    def _query_name(q):
        if not q:
            return None
        marker = "name = '"
        if marker not in q:
            return None
        return q.split(marker, 1)[1].split("'", 1)[0]

    def list_files(self, q='', page_size=100, **_ctx):
        name = self._query_name(q)
        items = list(self.files.values())
        if name is not None:
            items = [item for item in items if item['name'] == name]
        return {'files': [dict(item) for item in items[:page_size]]}

    def upload_file(self, name, mime_type, content, *, parent_id=None, provider_account, request_id, **_ctx):
        file_id = f'f{self.next_id}'
        self.next_id += 1
        data = bytes(content)
        meta = {
            'id': file_id,
            'name': name,
            'mimeType': mime_type,
            'size': str(len(data)),
            'version': '1',
            'parents': [parent_id] if parent_id else [],
        }
        self.files[file_id] = meta
        self.contents[file_id] = data
        return {
            'id': file_id,
            'verification': {'provider_file_id': file_id, 'version': '1', 'size': len(data)},
            'verified': True,
        }

    def update_content(self, file_id, mime_type, content, *, expected_version, provider_account, request_id, **_ctx):
        meta = self.files[file_id]
        assert str(meta['version']) == str(expected_version)
        data = bytes(content)
        version = str(int(meta['version']) + 1)
        meta.update({'mimeType': mime_type, 'size': str(len(data)), 'version': version})
        self.contents[file_id] = data
        return {
            'id': file_id,
            'verification': {'provider_file_id': file_id, 'version': version, 'size': len(data)},
            'verified': True,
        }

    def read_file(self, file_id, **_ctx):
        meta = dict(self.files[file_id])
        return {'content': self.contents[file_id], 'metadata': meta, 'media_type': meta['mimeType']}

    def request(self, method, path, **_kwargs):
        assert method == 'DELETE'
        file_id = str(path).rsplit('/', 1)[-1]
        self.files.pop(file_id, None)
        self.contents.pop(file_id, None)
        return {}


def manager_with_cloud(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'data-plane.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    return manager


def test_google_drive_bridge_reuses_canonical_adapter_without_copying_oauth_secret(tmp_path):
    manager = manager_with_cloud(tmp_path)
    drive = FakeDrive()
    runtime = {'integration_adapters': {'drive': drive}, 'native_storage_bridges': {}}
    status = connect_runtime_provider(
        manager,
        runtime,
        'google_drive',
        config={'parent_id': 'opaque-drive-parent'},
    )
    assert status['credential_ref'] == 'integration:drive'
    assert status['config']['authority'] == 'canonical_integration'
    assert 'token' not in json.dumps(status).lower()

    manager.register_item(
        'file:drive-private',
        entity_type='file',
        primary_device_id='laptop',
        policy='sync_everywhere',
        copy_allowed=True,
    )
    vault = Vault()
    envelopes = EnvelopeKeyManager(manager, vault)
    factory = GovernedProviderAdapterFactory(manager, vault, runtime=runtime)
    store = EncryptedProviderStore(manager, envelopes, factory)
    plaintext = b'owner private bytes that must only reach Drive encrypted'

    result = store.put('google_drive', 'file:drive-private', plaintext)
    assert result['ciphertext_only'] is True
    assert len(drive.contents) == 1
    provider_payload = next(iter(drive.contents.values()))
    provider_name = next(iter(drive.files.values()))['name']
    assert plaintext not in provider_payload
    assert 'drive-private' not in provider_name
    assert store.get('google_drive', 'file:drive-private') == plaintext

    assert store.delete('google_drive', 'file:drive-private') is True
    assert drive.contents == {}
    assert manager.set_policy('file:drive-private', 'device_only')['storage_policy'] == 'device_only'


def test_google_drive_bridge_fails_closed_if_canonical_adapter_disappears(tmp_path):
    manager = manager_with_cloud(tmp_path)
    runtime = {'integration_adapters': {'drive': FakeDrive()}, 'native_storage_bridges': {}}
    connect_runtime_provider(manager, runtime, 'google_drive')
    runtime['integration_adapters'].pop('drive')
    reconcile_runtime_providers(manager, runtime)
    assert manager.provider_status('google_drive')['available'] is False

    vault = Vault()
    factory = GovernedProviderAdapterFactory(manager, vault, runtime=runtime)
    with pytest.raises(PermissionError):
        factory.build('google_drive')


def test_icloud_bridge_keeps_root_out_of_data_plane_metadata_and_round_trips_ciphertext(tmp_path, monkeypatch):
    monkeypatch.setattr('data_plane.provider_bridges.platform.system', lambda: 'Darwin')
    manager = manager_with_cloud(tmp_path)
    root = (tmp_path / 'owner-icloud-container').resolve()
    root.mkdir()
    runtime = {'integration_adapters': {}, 'native_storage_bridges': {'icloud_bridge': str(root)}}
    status = connect_runtime_provider(manager, runtime, 'icloud_bridge')
    assert status['credential_ref'] == 'native:icloud_bridge'
    assert status['config'] == {'authority': 'native_runtime_bridge'}
    assert str(root) not in json.dumps(status)

    manager.register_item(
        'file:icloud-private',
        entity_type='file',
        primary_device_id='mac',
        policy='sync_everywhere',
        copy_allowed=True,
    )
    vault = Vault()
    store = EncryptedProviderStore(
        manager,
        EnvelopeKeyManager(manager, vault),
        GovernedProviderAdapterFactory(manager, vault, runtime=runtime),
    )
    plaintext = b'private bytes stored through owner-selected iCloud Drive'
    result = store.put('icloud_bridge', 'file:icloud-private', plaintext)
    persisted = [path for path in root.rglob('*.vishnu') if path.is_file()]
    assert len(persisted) == 1
    assert plaintext not in persisted[0].read_bytes()
    assert store.get('icloud_bridge', 'file:icloud-private') == plaintext
    assert store.delete('icloud_bridge', 'file:icloud-private') is True
    assert not persisted[0].exists()


def test_icloud_bridge_is_unavailable_off_apple_hosts(tmp_path, monkeypatch):
    monkeypatch.setattr('data_plane.provider_bridges.platform.system', lambda: 'Linux')
    manager = manager_with_cloud(tmp_path)
    root = (tmp_path / 'icloud').resolve()
    root.mkdir()
    runtime = {'integration_adapters': {}, 'native_storage_bridges': {'icloud_bridge': str(root)}}
    connect_runtime_provider(manager, runtime, 'icloud_bridge')
    factory = GovernedProviderAdapterFactory(manager, Vault(), runtime=runtime)
    with pytest.raises(ProviderAdapterError, match='Apple'):
        factory.build('icloud_bridge')


def test_icloud_bridge_rejects_relative_or_missing_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setattr('data_plane.provider_bridges.platform.system', lambda: 'Darwin')
    manager = manager_with_cloud(tmp_path)
    runtime = {'integration_adapters': {}, 'native_storage_bridges': {'icloud_bridge': 'relative/path'}}
    connect_runtime_provider(manager, runtime, 'icloud_bridge')
    factory = GovernedProviderAdapterFactory(manager, Vault(), runtime=runtime)
    with pytest.raises(ProviderAdapterError, match='absolute'):
        factory.build('icloud_bridge')

    runtime['native_storage_bridges']['icloud_bridge'] = str((tmp_path / 'missing').resolve())
    with pytest.raises(ProviderAdapterError, match='unavailable'):
        factory.build('icloud_bridge')
