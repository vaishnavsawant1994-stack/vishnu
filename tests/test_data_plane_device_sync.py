from __future__ import annotations

import asyncio

from core.events import EventBus
from data_plane.device_sync import DeviceProgressSyncService
from data_plane.enforced import PolicyEnforcedDataPlane


class Registry:
    def __init__(self):
        self.active = {'phone', 'laptop'}

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return device_id in self.active


class Gateway:
    def __init__(self, *, online=('laptop',), response=None, pending_events=None):
        self._online = set(online)
        self.response = response or {'ok': True, 'result': {'applied': True}}
        self.pending_events = list(pending_events or [])
        self.requests = []

    def online(self):
        return sorted(self._online)

    async def request(self, device_id, command, timeout=15):
        self.requests.append((device_id, command, timeout))
        if command.action == 'data_plane_progress_pending':
            return {'ok': True, 'result': {'events': list(self.pending_events)}}
        if command.action == 'data_plane_progress_ack':
            source_id = command.parameters.get('source_event_id')
            self.pending_events = [event for event in self.pending_events if event.get('source_event_id') != source_id]
            return {'ok': True, 'result': {'acknowledged': True}}
        return dict(self.response)


def manager(tmp_path):
    return PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=Registry())


def actions(gateway):
    return [command.action for _, command, _ in gateway.requests]


def test_reconnect_sync_delivers_progress_only_and_records_receipt(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    event = data_plane.prepare_sync_event(
        'project:1',
        origin_device_id='phone',
        payload={'project_name': 'Rudra', 'status': 'active', 'next_step': 'Homepage'},
    )
    gateway = Gateway()
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result['received'] == 0
    assert result['delivered'] == 1
    assert result['failed'] == 0
    assert result['remaining'] == 0
    assert actions(gateway) == ['data_plane_progress_pending', 'data_plane_progress_put']
    command = gateway.requests[-1][1]
    assert command.parameters['global_id'] == 'project:1'
    assert command.parameters['payload']['next_step'] == 'Homepage'
    assert data_plane.pending_progress_events('laptop') == []
    assert event['event_id']


def test_offline_device_keeps_events_pending_for_later_reconnect(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    data_plane.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'active'})
    gateway = Gateway(online=())
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result == {'device_id': 'laptop', 'skipped': True, 'reason': 'offline'}
    assert len(data_plane.pending_progress_events('laptop')) == 1


def test_conflict_is_not_acknowledged_or_overwritten(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    data_plane.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'active'})
    gateway = Gateway(response={'ok': True, 'result': {'applied': False, 'conflict': True, 'local_version': 9}})
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result['delivered'] == 0
    assert result['conflicts'] == 1
    assert len(data_plane.pending_progress_events('laptop')) == 1


def test_device_rejection_leaves_event_pending(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    data_plane.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'active'})
    gateway = Gateway(response={'ok': False, 'error': 'not allowed'})
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result['failed'] == 1
    assert len(data_plane.pending_progress_events('laptop')) == 1


def test_delete_sync_uses_tombstone_command(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    data_plane.delete_item('project:1', origin_device_id='phone')
    gateway = Gateway(response={'ok': True, 'result': {'deleted': True}})
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result['delivered'] == 1
    assert actions(gateway) == ['data_plane_progress_pending', 'data_plane_tombstone']


def test_sync_everywhere_domain_payload_is_not_sent_through_progress_protocol(tmp_path):
    data_plane = manager(tmp_path)
    data_plane.register_item('file:1', entity_type='file', primary_device_id='phone', policy='sync_everywhere')
    data_plane.prepare_sync_event('file:1', origin_device_id='phone', payload={'name': 'large-video.mp4'})
    gateway = Gateway()
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('laptop'))
    assert result['delivered'] == 0
    assert actions(gateway) == ['data_plane_progress_pending']


def test_phone_offline_change_is_pulled_applied_and_acked_on_reconnect(tmp_path):
    data_plane = manager(tmp_path)
    mobile_event = {
        'source_event_id': 'mobile-1',
        'global_id': 'project:mobile-created',
        'entity_type': 'project',
        'storage_policy': 'progress_only',
        'version': 1,
        'event_kind': 'update',
        'payload': {'project_name': 'Rudra', 'status': 'active', 'next_step': 'Continue on laptop'},
    }
    gateway = Gateway(online=('phone',), pending_events=[mobile_event])
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('phone'))
    assert result['received'] == 1
    assert result['delivered'] == 0
    assert result['conflicts'] == 0
    assert actions(gateway) == ['data_plane_progress_pending', 'data_plane_progress_ack']
    assert gateway.pending_events == []
    item = data_plane.item('project:mobile-created')
    assert item['origin_device_id'] == 'phone'
    assert item['metadata']['next_step'] == 'Continue on laptop'


def test_mobile_event_cannot_spoof_another_origin_device(tmp_path):
    data_plane = manager(tmp_path)
    mobile_event = {
        'source_event_id': 'mobile-2',
        'global_id': 'project:origin',
        'entity_type': 'project',
        'storage_policy': 'progress_only',
        'origin_device_id': 'laptop',
        'version': 1,
        'event_kind': 'update',
        'payload': {'status': 'active'},
    }
    gateway = Gateway(online=('phone',), pending_events=[mobile_event])
    service = DeviceProgressSyncService(data_plane, gateway, EventBus())
    result = asyncio.run(service.sync_device('phone'))
    assert result['received'] == 1
    assert data_plane.item('project:origin')['origin_device_id'] == 'phone'
