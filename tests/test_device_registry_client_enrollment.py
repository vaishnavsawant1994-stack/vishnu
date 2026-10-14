import pytest

from devices.registry import DeviceRegistry


def test_client_credential_enrollment_is_idempotent_and_never_rebinds(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    device_id = 'c13c4bc5-2031-4a96-a5eb-732399d44712'
    token = 'client-generated-secret-with-more-than-32-characters'

    device, returned = registry.enroll_with_credential(device_id, token, 'First phone', 'ios')
    assert returned == token
    assert registry.authenticate(device_id, token)
    retry, retry_token = registry.enroll_with_credential(device_id, token, 'Renamed', 'android')
    assert retry == device
    assert retry_token == token
    assert registry.list()[0]['name'] == 'First phone'

    with pytest.raises(ValueError, match='already registered'):
        registry.enroll_with_credential(device_id, 'different-secret-value-long-enough-to-pass', 'Other', 'android')
    assert registry.revoke(device_id)
    assert not registry.authenticate(device_id, token)
    with pytest.raises(ValueError, match='already registered'):
        registry.enroll_with_credential(device_id, token, 'First phone', 'ios')


def test_client_credential_enrollment_rejects_weak_material(tmp_path):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    with pytest.raises(ValueError, match='Invalid device ID'):
        registry.enroll_with_credential('short', 's' * 40, 'Phone', 'ios')
    with pytest.raises(ValueError, match='at least 32'):
        registry.enroll_with_credential('c13c4bc5-2031-4a96-a5eb-732399d44712', 'weak', 'Phone', 'ios')
