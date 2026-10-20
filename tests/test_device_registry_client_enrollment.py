import time

import pytest

from devices.registry import DeviceRegistry


def test_client_credential_enrollment_is_idempotent_and_never_rebinds(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    device_id = 'c13c4bc5-2031-4a96-a5eb-732399d44712'
    token = 'client-generated-secret-with-more-than-32-characters'

    device, returned = registry.enroll_with_credential(device_id, token, 'First phone', 'ios')
    assert returned == token
    assert registry.authenticate(device_id, token)
    assert set(registry.permissions(device_id)['scopes']) == registry.OWNER_SCOPES
    retry, retry_token = registry.enroll_with_credential(device_id, token, 'Renamed', 'android')
    assert retry == device
    assert retry_token == token
    assert registry.list()[0]['name'] == 'First phone'
    assert registry.authorize(device_id, 'device:admin')
    assert registry.authorize(device_id, 'data:admin')

    with pytest.raises(ValueError, match='already registered'):
        registry.enroll_with_credential(device_id, 'different-secret-value-long-enough-to-pass', 'Other', 'android')
    assert registry.revoke(device_id)
    assert not registry.authenticate(device_id, token)
    with pytest.raises(ValueError, match='already registered'):
        registry.enroll_with_credential(device_id, token, 'First phone', 'ios')


def test_client_credential_enrollment_repairs_legacy_native_owner_scopes_on_retry(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    device_id = 'c13c4bc5-2031-4a96-a5eb-732399d44712'
    token = 'client-generated-secret-with-more-than-32-characters'
    registry.enroll_with_credential(device_id, token, 'Recovered phone', 'android')
    registry.set_permissions(device_id, registry.DEFAULT_SCOPES)
    assert not registry.authorize(device_id, 'device:admin')

    registry.enroll_with_credential(device_id, token, 'Recovered phone', 'android')

    assert set(registry.permissions(device_id)['scopes']) == registry.OWNER_SCOPES
    assert registry.authorize(device_id, 'device:admin')


def test_ordinary_pairing_enrollment_keeps_default_scopes(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    device, _ = registry.enroll('Companion', 'android')
    assert set(registry.permissions(device['id'])['scopes']) == registry.DEFAULT_SCOPES
    assert not registry.authorize(device['id'], 'device:admin')


def test_client_credential_enrollment_rejects_weak_material(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    with pytest.raises(ValueError, match='Invalid device ID'):
        registry.enroll_with_credential('short', 's' * 40, 'Phone', 'ios')
    with pytest.raises(ValueError, match='at least 32'):
        registry.enroll_with_credential('c13c4bc5-2031-4a96-a5eb-732399d44712', 'weak', 'Phone', 'ios')


def test_pending_join_is_not_trusted_until_exact_request_is_approved(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    original, _ = registry.enroll('Owner desktop', 'windows')
    pending = registry.request_join('New browser', 'web-pwa')

    assert not registry.is_active(pending['device_id'])
    assert registry.join_status(pending['request_id'], pending['device_token']) == {'status': 'pending'}
    assert registry.join_status(pending['request_id'], 'wrong-token') is None
    assert registry.decide_join(pending['request_id'], approve=True, decided_by=original['id'])

    enrolled = registry.complete_join(pending['request_id'], pending['device_token'])
    assert enrolled['id'] == pending['device_id']
    assert registry.authenticate(pending['device_id'], pending['device_token'])
    assert registry.is_active(original['id'])
    assert not registry.authorize(pending['device_id'], 'device:admin')
    assert registry.complete_join(pending['request_id'], pending['device_token']) is None


def test_pending_join_denial_and_expiry_cannot_be_replayed(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    denied = registry.request_join('Denied browser', 'web-pwa')
    assert registry.decide_join(denied['request_id'], approve=False, decided_by='trusted-device')
    assert registry.join_status(denied['request_id'], denied['device_token']) == {'status': 'denied'}
    assert registry.complete_join(denied['request_id'], denied['device_token']) is None
    assert not registry.decide_join(denied['request_id'], approve=True, decided_by='trusted-device')

    expired = registry.request_join('Expired browser', 'web-pwa', ttl_seconds=60)
    with registry._con() as con:
        con.execute("UPDATE pending_device_joins SET expires_at=? WHERE id=?", (time.time() - 1, expired['request_id']))
    assert registry.pending_joins() == []
    assert registry.join_status(expired['request_id'], expired['device_token']) == {'status': 'expired'}
