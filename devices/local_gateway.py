from __future__ import annotations

import json
import queue
import socket
import threading
import time
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import uvicorn

from core.security import PairingManager
from devices.local_discovery import DiscoveryDescriptor, LocalDeviceAdvertiser
from devices.local_identity import LocalDeviceIdentity, ensure_local_device_identity


class PairConfirm(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=6, max_length=6)
    name: str = Field(default='Device', max_length=120)
    platform: str = Field(default='unknown', max_length=80)


def _bounded_mapping(value, *, max_bytes=65536, max_depth=8, max_items=256, max_string=12000):
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise ValueError('JSON object nesting exceeds limit')
        if isinstance(current, dict):
            if len(current) > max_items:
                raise ValueError('JSON object contains too many fields')
            for key, child in current.items():
                if len(str(key)) > 256:
                    raise ValueError('JSON object key is too long')
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > max_items:
                raise ValueError('JSON collection contains too many items')
            for child in current:
                stack.append((child, depth + 1))
        elif isinstance(current, str) and len(current) > max_string:
            raise ValueError('JSON string exceeds limit')
        nodes += 1
        if nodes > 4096:
            raise ValueError('JSON object is too complex')
    encoded = json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > max_bytes:
        raise ValueError('JSON object exceeds maximum size')
    return value


def create_local_device_app(*, settings, device_registry, device_gateway, runtime, identity: LocalDeviceIdentity) -> FastAPI:
    """Create the LAN surface. It intentionally contains no owner/control APIs."""
    app = FastAPI(title='Vishnu Local Device Gateway', docs_url=None, redoc_url=None, openapi_url=None)
    pairing = PairingManager(settings.pairing_ttl_seconds)

    @app.get('/device-gateway/health')
    def health():
        return {
            'ok': True,
            'service': 'vishnu-local-device-gateway',
            'protocol': 2,
            'service_id': identity.service_id,
        }

    @app.post('/pair/confirm')
    def pair_confirm(body: PairConfirm):
        if not pairing.consume(body.token, body.code):
            raise HTTPException(401, 'Invalid or expired pairing offer')
        if not device_registry:
            raise HTTPException(503, 'Device registry unavailable')
        device, device_token = device_registry.enroll(body.name, body.platform)
        continuity = runtime.get('continuity') if runtime else None
        if continuity:
            continuity.resume(device['id'])
        return {'device': device, 'bearer_token': device_token}

    @app.websocket('/device/ws/{device_id}')
    async def device_ws(ws: WebSocket, device_id: str):
        token = ws.headers.get('authorization', '').removeprefix('Bearer ').strip()
        if not device_registry or not token or not device_registry.authenticate(device_id, token):
            await ws.close(code=4401)
            return
        if hasattr(device_registry, 'authorize') and not device_registry.authorize(device_id, 'ai:chat'):
            await ws.close(code=4403)
            return
        await ws.accept()
        if device_gateway:
            device_gateway.connect(device_id, ws)
        continuity = runtime.get('continuity') if runtime else None
        if continuity:
            continuity.resume(device_id)
        try:
            while True:
                message = await ws.receive_json()
                if not device_registry or not device_registry.is_active(device_id):
                    if device_gateway:
                        device_gateway.disconnect(device_id)
                    await ws.close(code=4401)
                    break
                if hasattr(device_registry, 'authorize') and not device_registry.authorize(device_id, 'ai:chat'):
                    if device_gateway:
                        device_gateway.disconnect(device_id)
                    await ws.close(code=4403)
                    break
                if message.get('type') == 'push_registration' and message.get('provider') == 'apns' and message.get('token'):
                    device_registry.set_metadata(device_id, 'push.apns.token', str(message['token']).strip())
                    if message.get('environment'):
                        device_registry.set_metadata(
                            device_id,
                            'push.apns.environment',
                            str(message.get('environment')).strip().lower(),
                        )
                if message.get('type') == 'continuity_event' and continuity:
                    thread = continuity.active_for_device(device_id)
                    if thread:
                        try:
                            payload = _bounded_mapping(dict(message.get('payload') or {}))
                        except (TypeError, ValueError):
                            await ws.send_json({'type': 'error', 'error': 'invalid continuity payload'})
                            continue
                        continuity.append(
                            thread['id'],
                            device_id=device_id,
                            kind=str(message.get('kind', 'device_event'))[:80],
                            payload=payload,
                        )
                if device_gateway:
                    device_gateway.receive(device_id, message)
                if message.get('type') != 'result':
                    await ws.send_json({'type': 'ack', 'message_id': message.get('message_id')})
        except WebSocketDisconnect:
            pass
        finally:
            if device_gateway:
                device_gateway.disconnect(device_id)

    return app


def _port_available(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _choose_port(preferred: int) -> int:
    start = max(1024, min(int(preferred), 65525))
    for value in range(start, min(start + 10, 65535)):
        if _port_available(value):
            return value
    raise RuntimeError('No local device-gateway port is available')


@dataclass(frozen=True)
class LocalGatewayDescriptor:
    service_id: str
    service_name: str
    port: int
    cert_sha256: str


class LocalDeviceGatewayRuntime:
    """Lifecycle authority for Vishnu's minimal zero-config LAN surface."""

    def __init__(self, *, settings, device_registry, device_gateway, runtime):
        self.settings = settings
        self.device_registry = device_registry
        self.device_gateway = device_gateway
        self.runtime = runtime
        self.identity = ensure_local_device_identity(settings.data_dir)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._advertiser: LocalDeviceAdvertiser | None = None
        self._descriptor: LocalGatewayDescriptor | None = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._server and self._thread and self._thread.is_alive() and self._descriptor)

    @property
    def descriptor(self) -> LocalGatewayDescriptor | None:
        with self._lock:
            return self._descriptor

    def has_mobile_devices(self) -> bool:
        if not self.device_registry or not hasattr(self.device_registry, 'list'):
            return False
        try:
            return any(
                str(row.get('platform') or '').strip().lower() in {'android', 'ios'} and not row.get('revoked')
                for row in self.device_registry.list()
            )
        except Exception:
            return False

    def ensure_running(self) -> LocalGatewayDescriptor:
        with self._lock:
            if self._descriptor and self._server and self._thread and self._thread.is_alive():
                return self._descriptor
            port = _choose_port(getattr(self.settings, 'local_device_gateway_port', 8767))
            app = create_local_device_app(
                settings=self.settings,
                device_registry=self.device_registry,
                device_gateway=self.device_gateway,
                runtime=self.runtime,
                identity=self.identity,
            )
            config = uvicorn.Config(
                app,
                host='0.0.0.0',
                port=port,
                log_level='warning',
                access_log=False,
                ssl_certfile=str(self.identity.cert_path),
                ssl_keyfile=str(self.identity.key_path),
            )
            server = uvicorn.Server(config)
            thread = threading.Thread(target=server.run, name='vishnu-local-device-gateway', daemon=True)
            thread.start()
            deadline = time.time() + 8.0
            while time.time() < deadline and thread.is_alive() and not getattr(server, 'started', False):
                time.sleep(0.05)
            if not thread.is_alive() or not getattr(server, 'started', False):
                server.should_exit = True
                raise RuntimeError('Vishnu could not start the secure local device gateway')
            advertiser = LocalDeviceAdvertiser(
                service_id=self.identity.service_id,
                port=port,
                cert_sha256=self.identity.cert_sha256,
            )
            try:
                discovered: DiscoveryDescriptor = advertiser.start()
            except Exception:
                server.should_exit = True
                thread.join(timeout=3)
                raise
            descriptor = LocalGatewayDescriptor(
                service_id=discovered.service_id,
                service_name=discovered.service_name,
                port=discovered.port,
                cert_sha256=discovered.cert_sha256,
            )
            self._server = server
            self._thread = thread
            self._advertiser = advertiser
            self._descriptor = descriptor
            return descriptor

    def start_if_needed(self) -> LocalGatewayDescriptor | None:
        if not bool(getattr(self.settings, 'local_device_gateway_enabled', True)):
            return None
        if not self.has_mobile_devices():
            return None
        return self.ensure_running()

    def stop(self) -> None:
        with self._lock:
            advertiser = self._advertiser
            server = self._server
            thread = self._thread
            self._advertiser = None
            self._server = None
            self._thread = None
            self._descriptor = None
        if advertiser:
            try:
                advertiser.stop()
            except Exception:
                pass
        if server:
            server.should_exit = True
        if thread and thread.is_alive():
            thread.join(timeout=5)
