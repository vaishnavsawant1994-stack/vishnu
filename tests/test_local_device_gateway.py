from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from devices.local_gateway import create_local_device_app
from devices.local_identity import ensure_local_device_identity


class _Registry:
    def enroll(self, name, platform):
        return {'id': 'device-test', 'name': name, 'platform': platform}, 'bearer-test-value-123456'

    def authenticate(self, device_id, token):
        return device_id == 'device-test' and token == 'bearer-test-value-123456'

    def authorize(self, device_id, scope):
        return True

    def is_active(self, device_id):
        return True

    def set_metadata(self, *args, **kwargs):
        return None


class _Gateway:
    def connect(self, *args, **kwargs):
        return None

    def disconnect(self, *args, **kwargs):
        return None

    def receive(self, *args, **kwargs):
        return None


def test_local_tls_identity_is_persistent_and_private(tmp_path: Path):
    first = ensure_local_device_identity(tmp_path)
    second = ensure_local_device_identity(tmp_path)
    assert first.service_id == second.service_id
    assert first.cert_sha256 == second.cert_sha256
    assert len(first.service_id) == 32
    assert len(first.cert_sha256) == 64
    assert first.cert_path.exists()
    assert first.key_path.exists()
    if hasattr(first.key_path.stat(), 'st_mode'):
        assert first.key_path.stat().st_mode & 0o077 == 0


def test_local_gateway_exposes_only_pairing_device_health_and_websocket(tmp_path: Path):
    settings = SimpleNamespace(data_dir=tmp_path, pairing_ttl_seconds=300)
    identity = ensure_local_device_identity(tmp_path)
    app = create_local_device_app(
        settings=settings,
        device_registry=_Registry(),
        device_gateway=_Gateway(),
        runtime={},
        identity=identity,
    )
    paths = {route.path for route in app.routes}
    assert paths == {
        '/device-gateway/health',
        '/pair/confirm',
        '/device/ws/{device_id}',
    }
    forbidden = {
        '/command', '/cloud/command', '/cloud/memory/search', '/oauth/start/{provider_id}',
        '/dashboard-ui', '/apps-tools/capabilities', '/owner/security', '/memory', '/pair/start',
    }
    assert paths.isdisjoint(forbidden)
