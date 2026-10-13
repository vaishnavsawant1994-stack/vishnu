from __future__ import annotations

import asyncio
import uuid
from typing import Any

from devices.gateway import DeviceCommand


class DeviceProgressSyncService:
    """Best-effort reconnect sync for progress-only continuation metadata.

    The service deliberately cannot move file bytes. It consumes only the
    data plane's progress-only event projection and sends it through the
    already-authenticated canonical DeviceGateway. Failed/offline deliveries
    stay unacknowledged and are retried on a later device connection.
    """

    def __init__(self, data_plane, gateway, events, *, timeout_seconds: float = 10.0):
        self.data_plane = data_plane
        self.gateway = gateway
        self.events = events
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 30.0))
        self._unsubscribe = None
        self._tasks: set[asyncio.Task] = set()
        self._syncing: set[str] = set()

    def start(self):
        if self._unsubscribe is not None:
            return self
        self._unsubscribe = self.events.subscribe('device.connected', self._on_device_connected)
        return self

    def stop(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    def _on_device_connected(self, event: dict[str, Any]):
        device_id = str(event.get('device_id') or '').strip()
        if not device_id:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # DeviceGateway connections normally originate in the async server
            # loop. Without that loop we fail closed and wait for the next
            # connection instead of creating an unsafe cross-loop request.
            self.events.emit('data_plane.sync_deferred', device_id=device_id, reason='no_async_device_loop')
            return
        task = loop.create_task(self.sync_device(device_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _response_result(response: dict[str, Any]) -> dict[str, Any]:
        if not bool(response.get('ok')):
            raise RuntimeError(str(response.get('error') or 'device rejected data-plane sync'))
        result = response.get('result')
        if not isinstance(result, dict):
            raise RuntimeError('device returned malformed data-plane result')
        return result

    async def _deliver(self, device_id: str, event: dict[str, Any]) -> bool:
        kind = str(event['event_kind'])
        if kind == 'delete':
            action = 'data_plane_tombstone'
            parameters = {
                'global_id': event['global_id'],
                'version': int(event['version']),
            }
        else:
            action = 'data_plane_progress_put'
            parameters = {
                'global_id': event['global_id'],
                'entity_type': event['entity_type'],
                'version': int(event['version']),
                'payload': dict(event.get('payload') or {}),
            }
        command = DeviceCommand(action, parameters, str(uuid.uuid4()))
        response = await self.gateway.request(device_id, command, self.timeout_seconds)
        result = self._response_result(response)
        if bool(result.get('conflict')):
            self.events.emit(
                'data_plane.sync_conflict',
                device_id=device_id,
                global_id=event['global_id'],
                event_id=event['event_id'],
                remote_version=result.get('local_version'),
                incoming_version=event['version'],
            )
            return False
        if kind == 'delete':
            return bool(result.get('deleted'))
        return bool(result.get('applied'))

    async def sync_device(self, device_id: str, *, limit: int = 100) -> dict[str, Any]:
        device_id = str(device_id or '').strip()
        if not device_id:
            raise ValueError('device_id is required')
        if device_id in self._syncing:
            return {'device_id': device_id, 'skipped': True, 'reason': 'already_syncing'}
        if device_id not in self.gateway.online():
            return {'device_id': device_id, 'skipped': True, 'reason': 'offline'}
        self._syncing.add(device_id)
        delivered = 0
        conflicts = 0
        failed = 0
        try:
            pending = self.data_plane.pending_progress_events(device_id, limit=limit)
            for event in pending:
                if device_id not in self.gateway.online():
                    break
                try:
                    applied = await self._deliver(device_id, event)
                except (asyncio.TimeoutError, RuntimeError, PermissionError, ConnectionError) as exc:
                    failed += 1
                    self.events.emit(
                        'data_plane.sync_delivery_failed',
                        device_id=device_id,
                        global_id=event['global_id'],
                        event_id=event['event_id'],
                        error_type=type(exc).__name__,
                    )
                    # Preserve order for a project's continuation stream. A
                    # later reconnect will retry this and every unacked event.
                    break
                if not applied:
                    conflicts += 1
                    break
                self.data_plane.acknowledge_sync_event(device_id, event['event_id'])
                delivered += 1
            result = {
                'device_id': device_id,
                'delivered': delivered,
                'conflicts': conflicts,
                'failed': failed,
                'remaining': len(self.data_plane.pending_progress_events(device_id, limit=1)),
            }
            self.events.emit('data_plane.sync_completed', **result)
            return result
        finally:
            self._syncing.discard(device_id)
