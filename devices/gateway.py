from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any


@dataclass
class DeviceCommand:
    action: str
    parameters: dict[str, Any]
    request_id: str


class DeviceGateway:
    """Live trusted-device transport.

    The gateway is deliberately transport-only. It authenticates active device
    identity through DeviceRegistry, tracks the live WebSocket/event loop and
    correlates responses. Tool/approval authority stays in ToolRegistry and the
    caller. Live capability advertisements are ephemeral and never treated as
    owner permission.
    """

    def __init__(self, registry, events):
        self.registry = registry
        self.events = events
        self._sessions = {}
        self._loops = {}
        self._pending = {}
        self._capabilities: dict[str, frozenset[str]] = {}

    def connect(self, device_id, session):
        if not self.registry.is_active(device_id):
            raise PermissionError("device is not active")
        self._sessions[device_id] = session
        try:
            self._loops[device_id] = asyncio.get_running_loop()
        except RuntimeError:
            self._loops.pop(device_id, None)
        self.events.emit("device.connected", device_id=device_id)

    def disconnect(self, device_id):
        self._sessions.pop(device_id, None)
        self._loops.pop(device_id, None)
        self._capabilities.pop(device_id, None)
        for request_id, pending in list(self._pending.items()):
            expected_device, fut = pending
            if expected_device == device_id and not fut.done():
                fut.set_exception(RuntimeError("device disconnected"))
                self._pending.pop(request_id, None)
        self.events.emit("device.disconnected", device_id=device_id)

    def capabilities(self, device_id) -> tuple[str, ...]:
        if not self.registry.is_active(device_id):
            self._capabilities.pop(device_id, None)
            return ()
        return tuple(sorted(self._capabilities.get(device_id, ())))

    async def send(self, device_id, command: DeviceCommand):
        if not self.registry.is_active(device_id):
            self._sessions.pop(device_id, None)
            self._loops.pop(device_id, None)
            self._capabilities.pop(device_id, None)
            raise PermissionError("device is not active")
        session = self._sessions.get(device_id)
        if session is None:
            raise RuntimeError("device is offline")
        await session.send_json(
            {
                "type": "command",
                "request_id": command.request_id,
                "action": command.action,
                "parameters": command.parameters,
            }
        )
        return {"queued": True, "request_id": command.request_id}

    async def request(self, device_id, command: DeviceCommand, timeout=15):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[command.request_id] = (device_id, fut)
        try:
            await self.send(device_id, command)
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(command.request_id, None)

    def request_sync(self, device_id, command: DeviceCommand, timeout=15):
        """Submit a request from synchronous governed tool execution.

        Device WebSockets live on the server's asyncio loop while ToolRegistry
        handlers are synchronous. This method schedules the existing async
        request on the device loop and blocks only the caller thread. It refuses
        to block the device loop itself, preventing an event-loop deadlock.
        """
        if not self.registry.is_active(device_id):
            raise PermissionError("device is not active")
        loop = self._loops.get(device_id)
        if loop is None or not loop.is_running() or device_id not in self._sessions:
            raise RuntimeError("device is offline")
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            raise RuntimeError("synchronous device request cannot block the device event loop")
        bounded_timeout = max(1.0, min(float(timeout), 120.0))
        future = asyncio.run_coroutine_threadsafe(
            self.request(device_id, command, timeout=bounded_timeout),
            loop,
        )
        try:
            return future.result(timeout=bounded_timeout + 2.0)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError("trusted device request timed out") from exc

    def receive(self, device_id, msg: dict):
        if not self.registry.is_active(device_id):
            self._sessions.pop(device_id, None)
            self._loops.pop(device_id, None)
            self._capabilities.pop(device_id, None)
            self.events.emit("device.message.rejected", device_id=device_id, reason="device_revoked")
            return False
        if msg.get("type") == "hello":
            raw = msg.get("capabilities") or ()
            if isinstance(raw, (list, tuple)):
                clean = frozenset(
                    str(item).strip()[:80]
                    for item in raw[:128]
                    if str(item).strip()
                )
                self._capabilities[device_id] = clean
                self.events.emit(
                    "device.capabilities",
                    device_id=device_id,
                    capability_count=len(clean),
                )
        rid = msg.get("request_id")
        pending = self._pending.get(rid)
        if pending:
            expected_device, fut = pending
            if expected_device == device_id and not fut.done():
                fut.set_result({"device_id": device_id, **msg})
        self.events.emit("device.message", device_id=device_id, message=msg)
        return True

    def online(self):
        stale = [device_id for device_id in self._sessions if not self.registry.is_active(device_id)]
        for device_id in stale:
            self._sessions.pop(device_id, None)
            self._loops.pop(device_id, None)
            self._capabilities.pop(device_id, None)
        return sorted(self._sessions)
