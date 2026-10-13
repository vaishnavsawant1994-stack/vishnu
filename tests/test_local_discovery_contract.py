from __future__ import annotations

from devices.local_discovery import LocalDeviceAdvertiser, SERVICE_PREFIX, SERVICE_TYPE


def test_discovery_descriptor_contains_identity_but_no_credentials():
    service_id = '0123456789abcdef0123456789abcdef'
    fingerprint = 'ab' * 32
    advertiser = LocalDeviceAdvertiser(service_id=service_id, port=8767, cert_sha256=fingerprint)
    descriptor = advertiser.descriptor
    assert SERVICE_TYPE == '_vishnu._tcp.local.'
    assert descriptor.service_name == f'{SERVICE_PREFIX}{service_id}'
    assert descriptor.service_id == service_id
    assert descriptor.cert_sha256 == fingerprint
    rendered = repr(descriptor).lower()
    for forbidden in ('bearer', 'password', 'api_key', 'memory', 'approval'):
        assert forbidden not in rendered
