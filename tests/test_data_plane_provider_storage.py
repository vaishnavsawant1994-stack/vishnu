from __future__ import annotations

import json

import pytest

from data_plane.envelopes import EnvelopeKeyManager
from data_plane.hardened import HardenedDataPlane
from data_plane.storage_adapters import EncryptedProviderService, ProviderUnavailable


class Vault:
    def __init__(self): self.values = {}
    def get(self, name, default=None): return self.values.get(name, default)
    def set(self, name, value): self.values[name] = value


class MemoryAdapter:
    def __init__(self): self.objects = {}; self.deleted = []
    def put(self, key, payload): self.objects[key] = bytes(payload); return {'object_id': key}
    def get(self, key): return self.objects[key]
    def delete(self, key): self.objects.pop(key, None); self.deleted.append(key); return {'deleted': True, 'reference': f'deleted:{key}'}


class Adapters:
    def __init__(self, adapter): self.value = adapter
    def adapter(self, provider_id): return self.value


def plane(tmp_path, policy='sync_everywhere'):
    manager = HardenedDataPlane(tmp_path / 'data-plane.sqlite3')
    manager.register_item('file:provider-test', entity_type='file', primary_device_id='laptop', policy=policy)
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider('dropbox', enabled=True, credential_ref='vault:dropbox', verified=True)
    vault = Vault(); envelopes = EnvelopeKeyManager(manager, vault); adapter = MemoryAdapter()
    return manager, envelopes, adapter, EncryptedProviderService(manager, envelopes, Adapters(adapter))


def test_provider_receives_only_encrypted_envelope_and_round_trips(tmp_path):
    manager, _, adapter, service = plane(tmp_path)
    secret = b'private provider payload that must never be stored in plaintext'
    result = service.put_plaintext('file:provider-test', 1, secret, 'dropbox', content_type='application/pdf')
    stored = adapter.objects[result['object_key']]
    assert secret not in stored
    package = json.loads(stored.decode('utf-8'))
    assert package['algorithm'] == 'AES-256-GCM'
    assert 'ciphertext' in package
    assert service.get_plaintext('file:provider-test', 1, 'dropbox') == secret
    locations = manager.item('file:provider-test')['locations']
    assert any(item['provider_id'] == 'dropbox' and item['has_bytes'] for item in locations)


@pytest.mark.parametrize('policy', ['device_only', 'progress_only'])
def test_private_policies_cannot_materialize_provider_bytes(tmp_path, policy):
    _, _, adapter, service = plane(tmp_path, policy=policy)
    with pytest.raises(PermissionError, match='does not allow'):
        service.put_plaintext('file:provider-test', 1, b'private', 'dropbox')
    assert adapter.objects == {}


def test_provider_delete_requires_verified_copy_removal(tmp_path):
    manager, _, adapter, service = plane(tmp_path)
    put = service.put_plaintext('file:provider-test', 1, b'payload', 'dropbox')
    result = service.delete_copy('file:provider-test', 1, 'dropbox')
    assert result['removal']['verified'] is True
    assert put['object_key'] in adapter.deleted
    assert not any(item['provider_id'] == 'dropbox' for item in manager.item('file:provider-test')['locations'])


def test_unverified_provider_fails_before_remote_write(tmp_path):
    manager = HardenedDataPlane(tmp_path / 'data-plane.sqlite3')
    manager.register_item('file:provider-test', entity_type='file', primary_device_id='laptop', policy='sync_everywhere')
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider('dropbox', enabled=True, credential_ref='vault:dropbox', verified=False)
    service = EncryptedProviderService(manager, EnvelopeKeyManager(manager, Vault()), Adapters(MemoryAdapter()))
    with pytest.raises(ProviderUnavailable, match='not verified'):
        service.put_plaintext('file:provider-test', 1, b'payload', 'dropbox')
