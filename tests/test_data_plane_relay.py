from __future__ import annotations

import time

import pytest

from data_plane.relay import OpaqueDataRelay


class Registry:
    def __init__(self): self.active = {'phone', 'laptop'}
    def is_active(self, device_id): return device_id in self.active
    def authorize(self, device_id, scope): return device_id in self.active and scope == 'data:read'


def encrypted_frame():
    return {
        'protocol': 'vishnu-byte-transfer-v1',
        'session_id': 'session-12345678',
        'sequence': 0,
        'nonce': 'YWJjZGVmZ2hpamts',
        'ciphertext': 'ZW5jcnlwdGVkLWJ5dGVz',
        'chunk_digest': '0' * 64,
        'eof': False,
    }


def test_relay_is_opaque_store_and_forward(tmp_path):
    relay = OpaqueDataRelay(tmp_path / 'relay.sqlite3', device_registry=Registry())
    put = relay.put('phone', 'laptop', encrypted_frame(), ttl_seconds=60)
    assert put['opaque_ciphertext_only'] is True
    pulled = relay.pull('laptop')
    assert len(pulled) == 1
    assert pulled[0]['frame']['ciphertext'] == encrypted_frame()['ciphertext']
    assert relay.acknowledge('laptop', pulled[0]['frame_id']) is True
    assert relay.pull('laptop') == []
    assert relay.diagnostics()['stores_plaintext'] is False


@pytest.mark.parametrize('field', ['plaintext', 'bytes', 'bytes_b64', 'raw', 'file_bytes', 'content'])
def test_relay_refuses_plaintext_bearing_fields(tmp_path, field):
    relay = OpaqueDataRelay(tmp_path / 'relay.sqlite3', device_registry=Registry())
    frame = encrypted_frame(); frame[field] = 'private'
    with pytest.raises(PermissionError, match='plaintext'):
        relay.put('phone', 'laptop', frame)


def test_relay_revocation_and_recipient_binding_fail_closed(tmp_path):
    registry = Registry(); relay = OpaqueDataRelay(tmp_path / 'relay.sqlite3', device_registry=registry)
    result = relay.put('phone', 'laptop', encrypted_frame())
    with pytest.raises(PermissionError):
        relay.pull('unknown')
    registry.active.remove('laptop')
    with pytest.raises(PermissionError):
        relay.acknowledge('laptop', result['frame_id'])


def test_expired_frames_are_not_returned(tmp_path):
    relay = OpaqueDataRelay(tmp_path / 'relay.sqlite3', device_registry=Registry())
    result = relay.put('phone', 'laptop', encrypted_frame(), ttl_seconds=1)
    with relay._con() as con:
        con.execute('UPDATE data_relay_frames SET expires_at=? WHERE frame_id=?', (time.time() - 1, result['frame_id']))
    assert relay.pull('laptop') == []
