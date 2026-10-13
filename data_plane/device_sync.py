from __future__ import annotations

import asyncio
import uuid
from typing import Any, Mapping

from devices.gateway import DeviceCommand
from .manager import _hash


class DeviceProgressSyncService:
    """Reconnect sync for bounded progress-only continuation metadata.

    The service deliberately cannot move file bytes. On reconnect it first
    pulls locally-originated mobile progress events and durably applies them to
    the canonical data plane, acknowledging the mobile outbox only afterwards.
    It then pushes unacknowledged canonical progress events back to that device.
    Failed/offline/conflicting deliveries remain pending for later recovery.
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

    async def _request(self, device_id: str, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        command = DeviceCommand(action, parameters, str(uuid.uuid4()))
        response = await self.gateway.request(device_id, command, self.timeout_seconds)
        return self._response_result(response)

    def _canonicalize_device_event(self, device_id: str, source: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        source_event_id = str(source.get('source_event_id') or '').strip()
        global_id = str(source.get('global_id') or '').strip()
        entity_type = str(source.get('entity_type') or '').strip()
        event_kind = str(source.get('event_kind') or '').strip()
        version = int(source.get('version') or 0)
        payload = source.get('payload') or {}
        if not source_event_id or not global_id or not entity_type or event_kind not in {'update', 'delete'} or version < 1:
            raise ValueError('mobile progress event has invalid identity')
        if not isinstance(payload, dict):
            raise ValueError('mobile progress payload must be an object')
        envelope = {
            'schema_version': int(getattr(self.data_plane, 'SYNC_SCHEMA_VERSION', 1)),
            'global_id': global_id,
            'entity_type': entity_type,
            'storage_policy': 'progress_only',
            'primary_device_id': str(source.get('primary_device_id') or device_id),
            'version': version,
            # The authenticated device channel owns origin identity. A mobile
            # payload can never spoof another device as its origin.
            'origin_device_id': device_id,
            'event_kind': event_kind,
            'payload': dict(payload),
        }
        envelope['payload_hash'] = _hash(envelope['payload'])
        identity = self.data_plane._sync_identity_body(envelope)
        envelope['event_id'] = _hash(identity)
        return source_event_id, envelope

    async def _pull_device_events(self, device_id: str, *, limit: int) -> tuple[int, int, int]:
        result = await self._request(device_id, 'data_plane_progress_pending', {'limit': limit})
        raw_events = result.get('events', [])
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            raise RuntimeError('device returned malformed progress outbox')
        received = 0
        conflicts = 0
        failed = 0
        for raw in raw_events[:limit]:
            if device_id not in self.gateway.online():
                break
            if not isinstance(raw, dict):
                failed += 1
                break
            try:
                source_event_id, envelope = self._canonicalize_device_event(device_id, raw)
                applied = self.data_plane.receive_sync_event(device_id, envelope)
                if bool(applied.get('conflict')):
                    conflicts += 1
                    self.events.emit(
                        'data_plane.sync_conflict',
                        device_id=device_id,
                        global_id=envelope['global_id'],
                        event_id=envelope['event_id'],
                        incoming_version=envelope['version'],
                        reason=applied.get('reason'),
                    )
                    break
                if not (bool(applied.get('applied')) or bool(applied.get('duplicate'))):
                    failed += 1
                    break
                ack = await self._request(device_id, 'data_plane_progress_ack', {'source_event_id': source_event_id})
                if not bool(ack.get('acknowledged')):
                    failed += 1
                    break
                received += 1
            except (asyncio.TimeoutError, RuntimeError, PermissionError, ConnectionError, ValueError, KeyError) as exc:
                failed += 1
                self.events.emit(
                    'data_plane.sync_pull_failed',
                    device_id=device_id,
                    error_type=type(exc).__name__,
                )
                break
        return received, conflicts, failed

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
        result = await self._request(device_id, action, parameters)
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
        limit = max(1, min(int(limit), 500))
        if device_id in self._syncing:
            return {'device_id': device_id, 'skipped': True, 'reason': 'already_syncing'}
        if device_id not in self.gateway.online():
            return {'device_id': device_id, 'skipped': True, 'reason': 'offline'}
        try:
            self.data_plane._assert_active_device(device_id, 'data:sync')
        except PermissionError:
            self.events.emit('data_plane.sync_denied', device_id=device_id, reason='data_sync_scope')
            return {'device_id': device_id, 'skipped': True, 'reason': 'data_sync_not_authorized'}
        self._syncing.add(device_id)
        received = 0
        delivered = 0
        conflicts = 0
        failed = 0
        try:
            try:
                received, pull_conflicts, pull_failed = await self._pull_device_events(device_id, limit=limit)
                conflicts += pull_conflicts
                failed += pull_failed
            except (asyncio.TimeoutError, RuntimeError, PermissionError, ConnectionError, ValueError, KeyError) as exc:
                # Older companions that do not yet expose the pull command must
                # not lose the already-safe runtime -> device continuation path.
                # The failure is observable and will recover after upgrade.
                failed += 1
                self.events.emit('data_plane.sync_pull_unavailable', device_id=device_id, error_type=type(exc).__name__)

            if conflicts == 0 and device_id in self.gateway.online():
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
                        break
                    if not applied:
                        conflicts += 1
                        break
                    self.data_plane.acknowledge_sync_event(device_id, event['event_id'])
                    delivered += 1
            result = {
                'device_id': device_id,
                'received': received,
                'delivered': delivered,
                'conflicts': conflicts,
                'failed': failed,
                'remaining': len(self.data_plane.pending_progress_events(device_id, limit=1)),
            }
            self.events.emit('data_plane.sync_completed', **result)
            return result
        finally:
            self._syncing.discard(device_id)
