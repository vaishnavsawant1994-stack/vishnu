from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from core.security import PairingManager
from devices.local_gateway import create_local_device_app
from devices.local_identity import ensure_local_device_identity


class _Registry:
    def __init__(self):
        self.enrolled = []

    def enroll(self, name, platform):
        self.enrolled.append((name, platform))
        return {'id': 'mobile-1', 'name': name, 'platform': platform}, 'device-bearer-placeholder-123456789'

    def authenticate(self, device_id, token):
        return False

    def authorize(self, device_id, scope):
        return False

    def is_active(self, device_id):
        return False


class _Gateway:
    def connect(self, *args, **kwargs): pass
    def disconnect(self, *args, **kwargs): pass
    def receive(self, *args, **kwargs): pass


def test_local_pair_confirm_consumes_same_one_time_offer(tmp_path):
    settings = SimpleNamespace(data_dir=tmp_path, pairing_ttl_seconds=300)
    registry = _Registry()
    identity = ensure_local_device_identity(tmp_path)
    app = create_local_device_app(settings=settings, device_registry=registry, device_gateway=_Gateway(), runtime={}, identity=identity)
    offer = PairingManager(300).create()
    client = TestClient(app)
    response = client.post('/pair/confirm', json={'token': offer.token, 'code': offer.code, 'name': 'Phone', 'platform': 'android'})
    assert response.status_code == 200
    assert response.json()['device']['id'] == 'mobile-1'
    replay = client.post('/pair/confirm', json={'token': offer.token, 'code': offer.code, 'name': 'Phone', 'platform': 'android'})
    assert replay.status_code == 401
    assert registry.enrolled == [('Phone', 'android')]
