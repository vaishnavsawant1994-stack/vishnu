from __future__ import annotations

import pytest

from data_plane.hardened import HardenedDataPlane
from data_plane.manager import UnifiedDataPlane
from devices.registry import DeviceRegistry


class ScopedRegistry:
    def __init__(self):
        self.active = {'phone', 'laptop'}
        self.scopes = {
            'phone': {'ai:chat', 'data:read', 'data:sync'},
            'laptop': {'ai:chat', 'data:read', 'data:sync'},
        }

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in self.scopes.get(device_id, set())


class Gateway:
    def __init__(self, registry):
        self.registry = registry
        self._online = {'phone', 'laptop'}

    def online(self):
        return sorted(device for device in self._online if self.registry.is_active(device))


def hardened(tmp_path):
    registry = ScopedRegistry()
    gateway = Gateway(registry)
    plane = HardenedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    return plane, registry, gateway


def test_v1_data_plane_is_migrated_to_hardened_schema(tmp_path):
    path = tmp_path / 'data-plane.sqlite3'
    legacy = UnifiedDataPlane(path)
    assert legacy.settings()['schema_version'] == 1

    upgraded = HardenedDataPlane(path)
    assert upgraded.settings()['schema_version'] == 2
    diagnostics = upgraded.diagnostics()
    assert 2 in diagnostics['schema_migrations']
    assert diagnostics['remote_cache_policy'] == 'no_store'


def test_new_devices_receive_data_scopes_but_custom_permissions_are_not_broadened(tmp_path):
    path = tmp_path / 'devices.sqlite3'
    registry = DeviceRegistry(path)
    device, _ = registry.enroll('Phone', 'android')
    scopes = set(registry.permissions(device['id'])['scopes'])
    assert {'data:read', 'data:sync'} <= scopes

    registry.set_permissions(device['id'], {'ai:chat'})
    reopened = DeviceRegistry(path)
    assert set(reopened.permissions(device['id'])['scopes']) == {'ai:chat'}


def test_remote_access_requires_dedicated_data_read_scope(tmp_path):
    plane, registry, _ = hardened(tmp_path)
    plane.register_item(
        'file:private',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
    )
    registry.scopes['laptop'].discard('data:read')
    with pytest.raises(PermissionError, match='data:read'):
        plane.grant_remote_access('file:private', requester_device_id='laptop')

    registry.scopes['laptop'].add('data:read')
    lease = plane.grant_remote_access('file:private', requester_device_id='laptop')
    assert lease['cache_policy'] == 'no_store'
    assert lease['index_allowed'] is False
    assert lease['backup_allowed'] is False
    assert lease['offline_copy_allowed'] is False


def test_progress_sync_requires_dedicated_data_sync_scope(tmp_path):
    plane, registry, _ = hardened(tmp_path)
    plane.register_item(
        'project:1',
        entity_type='project',
        primary_device_id='phone',
        policy='progress_only',
    )
    event = plane.prepare_sync_event(
        'project:1',
        origin_device_id='phone',
        payload={'status': 'active'},
    )
    registry.scopes['laptop'].discard('data:sync')
    with pytest.raises(PermissionError, match='data:sync'):
        plane.receive_sync_event('laptop', event)


def test_device_only_transition_waits_for_verified_copy_removal(tmp_path):
    plane, _, _ = hardened(tmp_path)
    plane.register_item(
        'file:1',
        entity_type='file',
        primary_device_id='phone',
        policy='sync_everywhere',
    )
    plane.mark_location(
        'file:1',
        location_type='device',
        location_id='laptop',
        provider_id='local',
        has_bytes=True,
    )
    with pytest.raises(PermissionError, match='durable bytes remain'):
        plane.set_policy('file:1', 'device_only')

    request = plane.begin_copy_removal(
        'file:1',
        location_type='device',
        location_id='laptop',
    )
    assert request['verified'] is False
    status = plane.confirm_copy_removal(
        request['removal_id'],
        verification_ref='device:laptop:delete-readback:ok',
    )
    assert status['verified'] is True
    updated = plane.set_policy('file:1', 'device_only')
    assert updated['storage_policy'] == 'device_only'
    assert all(
        not location['has_bytes'] or location['location_id'] == 'phone'
        for location in updated['locations']
    )
