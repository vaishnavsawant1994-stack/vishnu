from __future__ import annotations

import pytest

from core.security import PairingManager
from devices.pairing_payload import build_pairing_uri, normalize_vishnu_origin, parse_pairing_uri


def test_pairing_uri_round_trip_preserves_existing_pairing_authority():
    manager = PairingManager(ttl_seconds=300)
    offer = manager.create()
    uri = build_pairing_uri(
        base_url='https://vishnu.example.test/ignored/path?query=ignored',
        token=offer.token,
        code=offer.code,
        expires_at=offer.expires_at,
    )
    payload = parse_pairing_uri(uri, now=offer.expires_at - 10)
    assert payload.base_url == 'https://vishnu.example.test'
    assert payload.token == offer.token
    assert payload.code == offer.code
    assert manager.consume(payload.token, payload.code) is True
    assert manager.consume(payload.token, payload.code) is False


def test_desktop_and_api_manager_instances_share_one_offer_authority():
    desktop = PairingManager(ttl_seconds=300)
    api = PairingManager(ttl_seconds=300)
    offer = desktop.create()
    assert api.consume(offer.token, offer.code) is True
    assert desktop.consume(offer.token, offer.code) is False

    abandoned = desktop.create()
    assert api.invalidate(abandoned.token) is True
    assert desktop.consume(abandoned.token, abandoned.code) is False


def test_pairing_payload_rejects_expired_or_wrong_shape():
    sample_token = 'a' * 24
    with pytest.raises(ValueError, match='expired'):
        parse_pairing_uri(
            f'vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test&token={sample_token}&code=123456&expires=100',
            now=101,
        )
    with pytest.raises(ValueError, match='six digits'):
        build_pairing_uri(
            base_url='https://vishnu.example.test',
            token=sample_token,
            code='12345',
            expires_at=9_999_999_999,
        )


def test_pairing_payload_rejects_url_userinfo_and_remote_http():
    userinfo_url = 'https://' + 'person' + ':' + 'credential' + '@vishnu.example.test'
    with pytest.raises(ValueError, match='credentials'):
        normalize_vishnu_origin(userinfo_url)
    with pytest.raises(ValueError, match='HTTPS'):
        normalize_vishnu_origin('http://vishnu.example.test')
    assert normalize_vishnu_origin('http://localhost:8766', allow_local_http=True) == 'http://localhost:8766'


def test_pairing_uri_rejects_duplicate_or_unknown_fields():
    sample_token = 'a' * 24
    base = f'vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test&token={sample_token}&code=123456&expires=9999999999'
    with pytest.raises(ValueError, match='fields'):
        parse_pairing_uri(base + '&token=duplicated')
    with pytest.raises(ValueError, match='fields'):
        parse_pairing_uri(base + '&extra=1')
