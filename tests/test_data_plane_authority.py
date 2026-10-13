from __future__ import annotations

import asyncio
import sqlite3

import pytest

from core.events import EventBus
from data_plane.device_sync import DeviceProgressSyncService
from data_plane.enforced import PolicyEnforcedDataPlane


class ScopedRegistry:
    def __init__(self, scopes=None):
        self.active = {'phone', 'laptop'}
        self.scopes = {
            'phone': set(),
            'laptop': set(),
        }
        for device_id, values in (scopes or {}).items():
            self.scopes[device_id] = set(values)

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in self.scopes.get(device_id, set())


class Gateway:
    def __init__(self, online=('phone', 'laptop')):
        self._online = set(online)
        self.requests = []

    def online(self):
        return sorted(self._online)

    async def request(self, device_id, command, timeout=15):
        self.requests.append((device_id, command, timeout))
        return {'ok': True, 'result': {'events': []}}


def test_data_plane_database_sets_explicit_schema_version(tmp_path):
    path = tmp_path / 'data-plane.sqlite3'
    manager = PolicyEnforcedDataPlane(path)
    assert manager.diagnostics()['database_schema_version'] == 1
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 1


def test_newer_data_plane_database_fails_closed(tmp_path):
    path = tmp_path / 'data-plane.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA user_version=2')
    with pytest.raises(RuntimeError, match='newer Vishnu version'):
        PolicyEnforcedDataPlane(path)


def test_exact_registration_replay_is_idempotent_without_version_bump(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'data-plane.sqlite3')
    first = manager.register_item(
        'project:stable',
        entity_type='project',
        primary_device_id='laptop',
        policy='progress_only',
        metadata={'status': 'active'},
    )
    replay = manager.register_item(
        'project:stable',
        entity_type='project',
        primary_device_id='laptop',
        policy='progress_only',
        metadata={'status': 'active'},
    )
    assert replay['version'] == first['version'] == 1
    assert replay['metadata'] == {'status': 'active'}


def test_registration_cannot_bypass_governed_policy_change(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'data-plane.sqlite3')
    manager.register_item(
        'file:stable',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
    )
    with pytest.raises(PermissionError, match='governed policy/domain mutation'):
        manager.register_item(
            'file:stable',
            entity_type='file',
            primary_device_id='phone',
            policy='sync_everywhere',
        )
    assert manager.item('file:stable')['storage_policy'] == 'device_only'
    assert manager.item('file:stable')['version'] == 1


def test_chat_permission_alone_does_not_grant_remote_data_read(tmp_path):
    registry = ScopedRegistry({
        'phone': {'ai:chat'},
        'laptop': {'ai:chat'},
    })
    gateway = Gateway()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    with pytest.raises(PermissionError, match='not permitted for data:read'):
        manager.grant_remote_access('file:phone', requester_device_id='laptop')


def test_data_read_allows_transient_view_but_not_persistent_copy(tmp_path):
    registry = ScopedRegistry({
        'phone': {'data:read'},
        'laptop': {'data:read'},
    })
    gateway = Gateway()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    manager.register_item(
        'file:phone',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
        copy_allowed=True,
    )
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    assert lease['persist_allowed'] is False
    with pytest.raises(PermissionError, match='not permitted for data:admin'):
        manager.grant_remote_access(
            'file:phone',
            requester_device_id='laptop',
            allow_persist=True,
        )


def test_data_admin_is_required_for_persistent_remote_copy_authority(tmp_path):
    registry = ScopedRegistry({
        'phone': {'data:read'},
        'laptop': {'data:read', 'data:admin'},
    })
    gateway = Gateway()
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    manager.register_item(
        'file:phone',
        entity_type='file',
        primary_device_id='phone',
        policy='sync_everywhere',
        copy_allowed=True,
    )
    lease = manager.grant_remote_access(
        'file:phone',
        requester_device_id='laptop',
        allow_persist=True,
    )
    assert lease['persist_allowed'] is True
    assert manager.validate_remote_lease(lease['lease_id'], require_persist=True)['persist_allowed'] is True


def test_reconnect_sync_requires_data_sync_scope_before_device_command(tmp_path):
    registry = ScopedRegistry({
        'phone': {'ai:chat', 'data:read'},
    })
    gateway = Gateway(online=('phone',))
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    service = DeviceProgressSyncService(manager, gateway, EventBus())
    result = asyncio.run(service.sync_device('phone'))
    assert result == {
        'device_id': 'phone',
        'skipped': True,
        'reason': 'data_sync_not_authorized',
    }
    assert gateway.requests == []


def test_reconnect_sync_operates_when_data_sync_scope_is_granted(tmp_path):
    registry = ScopedRegistry({
        'phone': {'data:read', 'data:sync'},
    })
    gateway = Gateway(online=('phone',))
    manager = PolicyEnforcedDataPlane(
        tmp_path / 'data-plane.sqlite3',
        device_registry=registry,
        device_gateway=gateway,
    )
    service = DeviceProgressSyncService(manager, gateway, EventBus())
    result = asyncio.run(service.sync_device('phone'))
    assert result['received'] == 0
    assert result['delivered'] == 0
    assert result['conflicts'] == 0
    assert gateway.requests[0][1].action == 'data_plane_progress_pending'
