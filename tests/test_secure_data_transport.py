from __future__ import annotations

import base64

import pytest

from data_plane.byte_transport import LeaseBoundByteTransport
from data_plane.envelopes import EnvelopeKeyManager
from data_plane.hardened import HardenedDataPlane


class Vault:
    def __init__(self): self.values = {}
    def get(self, name, default=None): return self.values.get(name, default)
    def set(self, name, value): self.values[name] = value


class Registry:
    def __init__(self): self.active = {'phone', 'laptop'}
    def is_active(self, device_id): return device_id in self.active
    def authorize(self, device_id, scope): return device_id in self.active and scope in {'data:read', 'data:sync', 'ai:chat'}


class Gateway:
    def __init__(self, registry): self.registry = registry; self.connected = {'phone', 'laptop'}
    def online(self): return sorted(self.connected & self.registry.active)


def stack(tmp_path):
    registry = Registry(); gateway = Gateway(registry)
    plane = HardenedDataPlane(tmp_path / 'data-plane.sqlite3', device_registry=registry, device_gateway=gateway)
    plane.register_item('file:private', entity_type='file', primary_device_id='phone', policy='device_only', remote_access_allowed=True, copy_allowed=False, metadata={'name': 'private.pdf'})
    vault = Vault(); envelopes = EnvelopeKeyManager(plane, vault); transport = LeaseBoundByteTransport(plane, envelopes, gateway=gateway)
    return plane, registry, gateway, vault, envelopes, transport


def test_object_envelope_round_trip_and_no_raw_database_key(tmp_path):
    plane, _, _, vault, envelopes, _ = stack(tmp_path)
    package = envelopes.encrypt_bytes('file:private', 1, b'super private bytes', content_type='application/pdf')
    assert envelopes.decrypt_bytes(package) == b'super private bytes'
    assert package['algorithm'] == 'AES-256-GCM'
    assert package['ciphertext'] != base64.b64encode(b'super private bytes').decode()
    assert envelopes.diagnostics()['raw_keys_in_database'] is False
    assert any(name.startswith('data_plane:kek:') for name in vault.values)
    with plane._con() as con:
        columns = {row['name'] for row in con.execute('PRAGMA table_info(data_plane_key_epochs)').fetchall()}
    assert 'key' not in columns and 'raw_key' not in columns


def test_object_envelope_tamper_fails_authentication(tmp_path):
    _, _, _, _, envelopes, _ = stack(tmp_path)
    package = envelopes.encrypt_bytes('file:private', 1, b'original')
    ciphertext = bytearray(base64.b64decode(package['ciphertext'])); ciphertext[-1] ^= 1
    package['ciphertext'] = base64.b64encode(bytes(ciphertext)).decode()
    with pytest.raises(ValueError, match='authentication'): envelopes.decrypt_bytes(package)


def test_key_epoch_rotation_keeps_old_data_decryptable_and_rewraps_without_reencrypting(tmp_path):
    _, _, _, _, envelopes, _ = stack(tmp_path)
    package = envelopes.encrypt_bytes('file:private', 1, b'payload')
    old_epoch, old_ciphertext = package['key_epoch'], package['ciphertext']
    new_epoch = envelopes.rotate_epoch()
    assert new_epoch > old_epoch and envelopes.decrypt_bytes(package) == b'payload'
    rewrapped = envelopes.rewrap_package(package)
    assert rewrapped['key_epoch'] == new_epoch and rewrapped['ciphertext'] == old_ciphertext
    assert envelopes.decrypt_bytes(rewrapped) == b'payload'


def test_remote_transfer_commits_only_after_ack_and_never_adds_copy_location(tmp_path):
    plane, _, _, _, _, transport = stack(tmp_path)
    before = list(plane.item('file:private')['locations'])
    session = transport.open_transfer('file:private', requester_device_id='laptop', expected_size=11, chunk_size=1024)
    assert session['persist_allowed'] is False and session['cache_policy'] == 'no_store'
    frame = transport.encrypt_chunk(session['session_id'], 0, b'hello world', eof=True)
    assert transport.decrypt_chunk(frame) == b'hello world'
    prepared = transport.status(session['session_id'])
    assert prepared['state'] == 'open' and prepared['bytes_transferred'] == 0
    assert prepared['pending_sequence'] == 0 and prepared['pending_frame'] is True
    ack = transport.acknowledge_chunk(session['session_id'], 0)
    assert ack['acknowledged'] is True and ack['state'] == 'complete'
    status = transport.status(session['session_id'])
    assert status['bytes_transferred'] == 11 and status['raw_session_key_exposed'] is False
    assert plane.item('file:private')['locations'] == before
    assert not any(row['location_id'] == 'laptop' and row['has_bytes'] for row in before)


def test_unacknowledged_frame_replays_identically_without_advancing_cursor(tmp_path):
    _, _, _, _, _, transport = stack(tmp_path)
    session = transport.open_transfer('file:private', requester_device_id='laptop', chunk_size=1024)
    first = transport.encrypt_chunk(session['session_id'], 0, b'first')
    retry = transport.encrypt_chunk(session['session_id'], 0, b'first')
    assert retry == first
    assert transport.status(session['session_id'])['bytes_transferred'] == 0
    with pytest.raises(ValueError, match='awaiting acknowledgment'):
        transport.encrypt_chunk(session['session_id'], 1, b'next')
    with pytest.raises(ValueError, match='mismatch'):
        transport.acknowledge_chunk(session['session_id'], 1)
    ack = transport.acknowledge_chunk(session['session_id'], 0)
    assert ack['next_sequence'] == 1 and ack['bytes_transferred'] == 5
    duplicate = transport.acknowledge_chunk(session['session_id'], 0)
    assert duplicate['duplicate'] is True
    second = transport.encrypt_chunk(session['session_id'], 1, b'next', eof=True)
    assert second['offset'] == 5


def test_transfer_chunk_tamper_is_rejected(tmp_path):
    _, _, _, _, _, transport = stack(tmp_path)
    session = transport.open_transfer('file:private', requester_device_id='laptop', chunk_size=1024)
    frame = transport.encrypt_chunk(session['session_id'], 0, b'secret')
    ciphertext = bytearray(base64.b64decode(frame['ciphertext'])); ciphertext[0] ^= 1
    frame['ciphertext'] = base64.b64encode(bytes(ciphertext)).decode()
    with pytest.raises(ValueError, match='authentication'): transport.decrypt_chunk(frame)


def test_revoked_requester_invalidates_open_transfer(tmp_path):
    _, registry, _, _, _, transport = stack(tmp_path)
    session = transport.open_transfer('file:private', requester_device_id='laptop', chunk_size=1024)
    registry.active.remove('laptop')
    with pytest.raises(PermissionError): transport.encrypt_chunk(session['session_id'], 0, b'data')


def test_source_offline_invalidates_transfer_before_next_chunk(tmp_path):
    _, _, gateway, _, _, transport = stack(tmp_path)
    session = transport.open_transfer('file:private', requester_device_id='laptop', chunk_size=1024)
    gateway.connected.remove('phone')
    with pytest.raises(RuntimeError, match='offline'): transport.encrypt_chunk(session['session_id'], 0, b'data')


def test_transfer_expiry_revokes_underlying_lease(tmp_path):
    plane, _, _, _, _, transport = stack(tmp_path)
    session = transport.open_transfer('file:private', requester_device_id='laptop', chunk_size=1024)
    with plane._con() as con:
        con.execute('UPDATE data_plane_transfer_sessions SET expires_at=0 WHERE session_id=?', (session['session_id'],))
    with pytest.raises(PermissionError, match='expired'): transport.encrypt_chunk(session['session_id'], 0, b'data')
    assert transport.status(session['session_id'])['state'] == 'aborted'
