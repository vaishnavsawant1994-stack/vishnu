from __future__ import annotations

import base64
import json

import pytest

from data_plane.byte_transport import LeaseBoundByteTransport
from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.envelopes import EnvelopeKeyManager
from data_plane.provider_adapters import (
    EncryptedProviderStore,
    ProviderAdapterFactory,
    ProviderObjectInfo,
)


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

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return device_id in self.active and scope in {'data:read', 'data:sync', 'data:admin', 'ai:chat'}


class Gateway:
    def __init__(self, registry):
        self.registry = registry
        self.connected = {'phone', 'laptop'}

    def online(self):
        return sorted(self.connected & self.registry.active)


class MemoryAdapter:
    def __init__(self):
        self.objects = {}
        self.fail_put = False
        self.fail_delete = False

    def put(self, object_key, payload, *, content_type='application/octet-stream'):
        if self.fail_put:
            raise RuntimeError('provider unavailable')
        data = bytes(payload)
        self.objects[object_key] = data
        return ProviderObjectInfo(object_key, size=len(data), content_type=content_type)

    def get(self, object_key):
        if object_key not in self.objects:
            raise FileNotFoundError(object_key)
        return self.objects[object_key]

    def delete(self, object_key):
        if self.fail_delete:
            raise RuntimeError('provider unavailable')
        return self.objects.pop(object_key, None) is not None

    def head(self, object_key):
        data = self.objects.get(object_key)
        return None if data is None else ProviderObjectInfo(object_key, size=len(data))

    def verify(self):
        return {'ok': True}


class MemoryFactory:
    def __init__(self, adapter):
        self.adapter = adapter

    def build(self, _provider_id):
        return self.adapter


def provider_stack(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'provider.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider(
        's3', enabled=True, credential_ref='provider:s3',
        config={'bucket': 'owner-vishnu', 'region': 'eu-central-1'}, verified=True,
    )
    manager.register_item(
        'file:provider', entity_type='file', primary_device_id='laptop',
        policy='sync_everywhere', copy_allowed=True,
    )
    vault = Vault()
    adapter = MemoryAdapter()
    store = EncryptedProviderStore(manager, EnvelopeKeyManager(manager, vault), MemoryFactory(adapter))
    return manager, vault, adapter, store


def transfer_stack(tmp_path):
    registry = Registry()
    gateway = Gateway(registry)
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'transfer.sqlite3', device_registry=registry, device_gateway=gateway,
    )
    manager.register_item(
        'file:phone', entity_type='file', primary_device_id='phone',
        policy='device_only', remote_access_allowed=True, copy_allowed=False,
    )
    vault = Vault()
    envelopes = EnvelopeKeyManager(manager, vault)
    transport = LeaseBoundByteTransport(manager, envelopes, gateway=gateway)
    return manager, registry, gateway, vault, envelopes, transport


def test_provider_write_outage_never_creates_durable_location(tmp_path):
    manager, _vault, adapter, store = provider_stack(tmp_path)
    adapter.fail_put = True
    with pytest.raises(RuntimeError, match='unavailable'):
        store.put('s3', 'file:provider', b'must-not-be-recorded-as-uploaded')
    locations = manager.item('file:provider')['locations']
    assert not any(row['location_type'] == 'provider' and row['has_bytes'] for row in locations)


def test_provider_delete_outage_preserves_location_and_blocks_device_only_transition(tmp_path):
    manager, _vault, adapter, store = provider_stack(tmp_path)
    store.put('s3', 'file:provider', b'encrypted-provider-copy')
    adapter.fail_delete = True
    with pytest.raises(RuntimeError, match='unavailable'):
        store.delete('s3', 'file:provider')
    assert any(row['location_type'] == 'provider' and row['has_bytes'] for row in manager.item('file:provider')['locations'])
    with pytest.raises(PermissionError, match='durable bytes remain'):
        manager.set_policy('file:provider', 'device_only')


def test_tampered_provider_ciphertext_fails_authentication(tmp_path):
    _manager, _vault, adapter, store = provider_stack(tmp_path)
    result = store.put('s3', 'file:provider', b'authenticated provider data')
    raw = json.loads(adapter.objects[result['object_key']])
    envelope = raw['envelope']
    ciphertext = bytearray(base64.b64decode(envelope['ciphertext']))
    ciphertext[len(ciphertext) // 2] ^= 0x01
    envelope['ciphertext'] = base64.b64encode(bytes(ciphertext)).decode()
    adapter.objects[result['object_key']] = json.dumps(raw, sort_keys=True, separators=(',', ':')).encode()
    with pytest.raises(ValueError, match='authentication'):
        store.get('s3', 'file:provider')


def test_cloud_off_prevents_canonical_adapter_creation_before_network_use(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'cloud-off.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider(
        'dropbox', enabled=True, credential_ref='provider:dropbox', config={}, verified=True,
    )
    vault = Vault()
    vault.set('provider:dropbox', json.dumps({'access_token': 'never-used-token'}))
    factory = ProviderAdapterFactory(manager, vault)
    assert manager.provider_status('dropbox')['available'] is True
    manager.update_settings(cloud_enabled=False)
    with pytest.raises(PermissionError, match='not connected, enabled, and verified'):
        factory.build('dropbox')


def test_pending_transfer_frame_survives_process_recreation_without_cursor_skip(tmp_path):
    manager, _registry, gateway, _vault, envelopes, transport = transfer_stack(tmp_path)
    opened = transport.open_transfer('file:phone', requester_device_id='laptop', expected_size=10, chunk_size=1024)
    frame = transport.encrypt_chunk(opened['session_id'], 0, b'first-half')
    assert transport.status(opened['session_id'])['bytes_transferred'] == 0

    # Recreate the transport service as a process-crash/restart boundary. The
    # pending encrypted frame is durable; no raw session key is persisted.
    restarted = LeaseBoundByteTransport(manager, envelopes, gateway=gateway)
    replay = restarted.encrypt_chunk(opened['session_id'], 0, b'first-half')
    assert replay == frame
    assert restarted.status(opened['session_id'])['bytes_transferred'] == 0
    restarted.acknowledge_chunk(opened['session_id'], 0)
    second = restarted.encrypt_chunk(opened['session_id'], 1, b'x', eof=True)
    assert restarted.decrypt_chunk(second) == b'x'
    completed = restarted.acknowledge_chunk(opened['session_id'], 1)
    assert completed['state'] == 'complete'
    assert completed['bytes_transferred'] == 10


def test_bounded_multi_chunk_transfer_endurance_completes_without_persistent_copy(tmp_path):
    manager, _registry, _gateway, _vault, _envelopes, transport = transfer_stack(tmp_path)
    chunk_size = 64 * 1024
    chunk_count = 64
    total = chunk_size * chunk_count
    opened = transport.open_transfer(
        'file:phone', requester_device_id='laptop', expected_size=total, chunk_size=chunk_size,
    )
    block = b'z' * chunk_size
    for sequence in range(chunk_count):
        eof = sequence == chunk_count - 1
        frame = transport.encrypt_chunk(opened['session_id'], sequence, block, eof=eof)
        assert transport.decrypt_chunk(frame) == block
        ack = transport.acknowledge_chunk(opened['session_id'], sequence)
        assert ack['bytes_transferred'] == (sequence + 1) * chunk_size
    status = transport.status(opened['session_id'])
    assert status['state'] == 'complete'
    assert status['bytes_transferred'] == total
    assert status['cache_policy'] == 'no_store'
    assert not any(
        row['location_id'] == 'laptop' and row['has_bytes']
        for row in manager.item('file:phone')['locations']
    )
