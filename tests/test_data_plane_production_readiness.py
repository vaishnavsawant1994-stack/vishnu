from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.envelopes import EnvelopeKeyManager
from data_plane.manager import _hash
from data_plane.provider_adapters import (
    EncryptedProviderStore,
    ProviderAdapterError,
    ProviderAdapterFactory,
    ProviderObjectInfo,
    S3CompatibleAdapter,
    VaultCredentialResolver,
)
from data_plane.relay import OpaqueVishnuRelayClient, RelayError


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


class Registry:
    def __init__(self):
        self.active = {'phone', 'laptop'}
        self.scopes = {
            'phone': {'data:read', 'data:sync', 'data:admin'},
            'laptop': {'data:read', 'data:sync', 'data:admin'},
        }

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in self.scopes.get(device_id, set())


class Gateway:
    def __init__(self):
        self.devices = {'phone', 'laptop'}

    def online(self):
        return sorted(self.devices)


class MemoryAdapter:
    def __init__(self):
        self.objects = {}

    def put(self, object_key, payload, *, content_type='application/octet-stream'):
        data = bytes(payload)
        self.objects[object_key] = data
        return ProviderObjectInfo(object_key, size=len(data), content_type=content_type)

    def get(self, object_key):
        if object_key not in self.objects:
            raise FileNotFoundError(object_key)
        return self.objects[object_key]

    def delete(self, object_key):
        return self.objects.pop(object_key, None) is not None

    def head(self, object_key):
        data = self.objects.get(object_key)
        return None if data is None else ProviderObjectInfo(object_key, size=len(data))

    def verify(self):
        return {'ok': True}


class MemoryFactory:
    def __init__(self, adapter):
        self.adapter = adapter

    def build(self, provider_id):
        return self.adapter


class DummyHttpClient:
    def request(self, *args, **kwargs):
        raise AssertionError('network should not be used by signing test')


class FakeResponse:
    def __init__(self, status_code=200, body=None, *, headers=None, content=b''):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class RelayClient:
    def __init__(self):
        self.sent = []

    def post(self, url, *, headers=None, content=None):
        body = json.loads(content)
        self.sent.append(body)
        return FakeResponse(body={'message_id': body['message_id']})

    def get(self, url, *, headers=None):
        if url.endswith('/health'):
            return FakeResponse(body={'service': 'vishnu-relay', 'version': 1})
        return FakeResponse(body={'messages': [], 'cursor': None})

    def delete(self, url, *, headers=None):
        return FakeResponse(status_code=204)


def configured_manager(tmp_path, *, registry=None):
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=Gateway() if registry else None,
    )
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider(
        's3',
        enabled=True,
        credential_ref='provider:s3',
        config={'bucket': 'owner-vishnu', 'region': 'eu-central-1'},
        verified=True,
    )
    return manager


def test_encrypted_provider_round_trip_never_stores_plaintext(tmp_path):
    manager = configured_manager(tmp_path)
    manager.register_item(
        'file:private',
        entity_type='file',
        primary_device_id='laptop',
        policy='sync_everywhere',
        copy_allowed=True,
    )
    vault = Vault()
    envelopes = EnvelopeKeyManager(manager, vault)
    adapter = MemoryAdapter()
    store = EncryptedProviderStore(manager, envelopes, MemoryFactory(adapter))
    plaintext = b'private-patient-document-content-1234'

    result = store.put('s3', 'file:private', plaintext, content_type='application/pdf')
    provider_blob = adapter.objects[result['object_key']]

    assert result['ciphertext_only'] is True
    assert plaintext not in provider_blob
    assert b'private-patient-document-content-1234' not in provider_blob
    assert store.get('s3', 'file:private') == plaintext
    locations = manager.item('file:private')['locations']
    assert any(row['provider_id'] == 's3' and row['has_bytes'] for row in locations)


def test_device_only_and_progress_only_bytes_cannot_use_provider_store(tmp_path):
    manager = configured_manager(tmp_path)
    vault = Vault()
    envelopes = EnvelopeKeyManager(manager, vault)
    adapter = MemoryAdapter()
    store = EncryptedProviderStore(manager, envelopes, MemoryFactory(adapter))
    for global_id, policy in [('file:phone', 'device_only'), ('project:progress', 'progress_only')]:
        manager.register_item(
            global_id,
            entity_type='file',
            primary_device_id='phone',
            policy=policy,
            copy_allowed=True,
        )
        with pytest.raises(PermissionError):
            store.put('s3', global_id, b'must-not-leave-source')
    assert adapter.objects == {}


def test_provider_copy_can_be_deleted_before_device_only_transition(tmp_path):
    manager = configured_manager(tmp_path)
    manager.register_item(
        'file:migrating', entity_type='file', primary_device_id='laptop',
        policy='sync_everywhere', copy_allowed=True,
    )
    vault = Vault()
    adapter = MemoryAdapter()
    store = EncryptedProviderStore(manager, EnvelopeKeyManager(manager, vault), MemoryFactory(adapter))
    store.put('s3', 'file:migrating', b'encrypted elsewhere')
    with pytest.raises(PermissionError, match='durable bytes remain'):
        manager.set_policy('file:migrating', 'device_only')
    assert store.delete('s3', 'file:migrating') is True
    assert manager.set_policy('file:migrating', 'device_only')['storage_policy'] == 'device_only'


def test_vault_credential_resolver_keeps_secret_behind_reference():
    vault = Vault()
    vault.set('provider:dropbox', json.dumps({'access_token': 'secret-access-token'}))
    resolved = VaultCredentialResolver(vault).resolve('provider:dropbox')
    assert resolved['access_token'] == 'secret-access-token'
    with pytest.raises(ProviderAdapterError):
        VaultCredentialResolver(vault).resolve('missing')


def test_factory_rejects_unverified_provider_before_secret_resolution(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'data-plane.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider(
        'dropbox', enabled=True, credential_ref='provider:dropbox', config={}, verified=False,
    )
    vault = Vault()
    vault.set('provider:dropbox', 'should-not-be-read-for-unverified-provider')
    with pytest.raises(PermissionError, match='not connected, enabled, and verified'):
        ProviderAdapterFactory(manager, vault).build('dropbox')


def test_s3_sigv4_header_never_contains_secret_key():
    adapter = S3CompatibleAdapter(
        provider_id='s3',
        config={'bucket': 'owner-bucket', 'region': 'eu-central-1', 'endpoint': 'https://s3.eu-central-1.amazonaws.com'},
        credentials={'access_key_id': 'ACCESS123', 'secret_access_key': 'super-secret-signing-key'},
        client=DummyHttpClient(),
    )
    headers = adapter._signed_headers('PUT', adapter._url('v1/object'), b'ciphertext')
    authorization = headers['Authorization']
    assert 'ACCESS123' in authorization
    assert 'super-secret-signing-key' not in authorization
    assert headers['X-Amz-Content-Sha256'] == _sha(b'ciphertext')


def _sha(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def test_s3_compatible_adapter_rejects_non_https_endpoint():
    with pytest.raises(ProviderAdapterError, match='HTTPS'):
        S3CompatibleAdapter(
            provider_id='cloudflare_r2',
            config={'bucket': 'owner', 'region': 'auto', 'endpoint': 'http://example.test'},
            credentials={'access_key_id': 'a', 'secret_access_key': 'b'},
            client=DummyHttpClient(),
        )


def relay_manager(tmp_path):
    registry = Registry()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'relay-data-plane.sqlite3', device_registry=registry, device_gateway=Gateway(),
    )
    manager.update_settings(cloud_enabled=True, cloud_mode='vishnu_cloud')
    return manager, registry


def test_optional_relay_accepts_ciphertext_only_and_rechecks_trusted_devices(tmp_path):
    manager, registry = relay_manager(tmp_path)
    vault = Vault()
    vault.set('relay:credential', json.dumps({'token': 'relay-secret'}))
    http = RelayClient()
    relay = OpaqueVishnuRelayClient(
        manager, vault, endpoint='https://relay.example.test', credential_ref='relay:credential',
        local_device_id='laptop', client=http,
    )
    frame = {
        'protocol': 'vishnu-byte-transfer-v1',
        'algorithm': 'AES-256-GCM',
        'nonce': base64.b64encode(b'n' * 12).decode(),
        'ciphertext': base64.b64encode(b'encrypted-only').decode(),
        'sequence': 0,
        'eof': True,
    }
    result = relay.send_encrypted('phone', frame)
    assert result['target_device_id'] == 'phone'
    assert http.sent[0]['frame']['ciphertext'] == frame['ciphertext']
    assert 'plaintext' not in json.dumps(http.sent[0])

    registry.active.remove('phone')
    with pytest.raises(PermissionError):
        relay.send_encrypted('phone', frame)


def test_relay_rejects_plaintext_fields_even_when_ciphertext_is_present(tmp_path):
    manager, _ = relay_manager(tmp_path)
    vault = Vault()
    vault.set('relay:credential', 'relay-secret')
    relay = OpaqueVishnuRelayClient(
        manager, vault, endpoint='https://relay.example.test', credential_ref='relay:credential',
        local_device_id='laptop', client=RelayClient(),
    )
    with pytest.raises(RelayError, match='plaintext'):
        relay.send_encrypted('phone', {
            'algorithm': 'AES-256-GCM',
            'nonce': base64.b64encode(b'n' * 12).decode(),
            'ciphertext': base64.b64encode(b'ciphertext').decode(),
            'plaintext': 'secret',
        })


def test_relay_is_fail_closed_when_cloud_is_disabled(tmp_path):
    manager, _ = relay_manager(tmp_path)
    manager.update_settings(cloud_enabled=False)
    vault = Vault()
    vault.set('relay:credential', 'relay-secret')
    relay = OpaqueVishnuRelayClient(
        manager, vault, endpoint='https://relay.example.test', credential_ref='relay:credential',
        local_device_id='laptop', client=RelayClient(),
    )
    with pytest.raises(PermissionError, match='disabled'):
        relay.verify()


def _sync_event(*, global_id, version, origin, payload, kind='update', policy='progress_only'):
    body = {
        'schema_version': 1,
        'global_id': global_id,
        'entity_type': 'project',
        'storage_policy': policy,
        'primary_device_id': origin,
        'version': version,
        'origin_device_id': origin,
        'event_kind': kind,
        'payload': payload,
    }
    return {'event_id': _hash(body), **body, 'payload_hash': _hash(payload)}


def test_multi_device_replay_conflict_tombstone_and_endurance(tmp_path):
    registry = Registry()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'endurance.sqlite3', device_registry=registry, device_gateway=Gateway(),
    )

    # Bounded endurance campaign: many offline-origin records plus duplicate replay.
    for index in range(250):
        global_id = f'project:{index}'
        event = _sync_event(
            global_id=global_id,
            version=1,
            origin='phone',
            payload={'project_id': global_id, 'status': 'active', 'progress': index},
        )
        first = manager.receive_sync_event('laptop', event)
        replay = manager.receive_sync_event('laptop', event)
        assert first['applied'] is True
        assert replay['duplicate'] is True

    # Same-version edit from a different offline origin is an explicit conflict.
    conflicting = _sync_event(
        global_id='project:0', version=1, origin='laptop',
        payload={'project_id': 'project:0', 'status': 'blocked', 'progress': 0},
    )
    conflict = manager.receive_sync_event('phone', conflicting)
    assert conflict['conflict'] is True
    assert conflict['reason'] == 'concurrent_same_version'

    # A later tombstone from the authoritative origin propagates and survives replay.
    deleted = _sync_event(
        global_id='project:1', version=2, origin='phone', kind='delete',
        payload={'updated_at': '2026-10-14T00:00:00+00:00'},
    )
    assert manager.receive_sync_event('laptop', deleted)['applied'] is True
    assert manager.item('project:1')['tombstone'] is True
    assert manager.receive_sync_event('laptop', deleted)['duplicate'] is True

    diagnostics = manager.diagnostics()
    assert diagnostics['items'] == 250
    assert diagnostics['events'] >= 251
    assert diagnostics['conflicts'] >= 1


def test_revoked_origin_cannot_resume_offline_sync(tmp_path):
    registry = Registry()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'revoke.sqlite3', device_registry=registry, device_gateway=Gateway(),
    )
    registry.active.remove('phone')
    event = _sync_event(
        global_id='project:revoked', version=1, origin='phone',
        payload={'project_id': 'project:revoked', 'status': 'active'},
    )
    with pytest.raises(PermissionError):
        manager.receive_sync_event('laptop', event)
    with pytest.raises(KeyError):
        manager.item('project:revoked')


def test_pwa_service_worker_never_dynamically_caches_api_or_private_data():
    root = Path(__file__).resolve().parents[1]
    sw = (root / 'pwa' / 'sw.js').read_text(encoding='utf-8')
    cache = (root / 'pwa' / 'data-plane-cache.js').read_text(encoding='utf-8')
    assert "url.pathname.startsWith('/iphone/api/')" in sw
    assert "dataPolicy==='device_only'" in sw
    assert "SHELL_SET.has(url.pathname)" in sw
    assert "MAX_ENTRIES=512" in cache
    assert "MAX_TOTAL_BYTES=8*1024*1024" in cache
    assert "device-only data is never persisted" in cache
    assert "AES-GCM" in cache
