from __future__ import annotations

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.manager import _hash


class Registry:
    def __init__(self):
        self.active = {'phone', 'laptop'}

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return device_id in self.active


class Gateway:
    def __init__(self, registry, online=()):
        self.registry = registry
        self._online = set(online)

    def online(self):
        return sorted(device for device in self._online if self.registry.is_active(device))


def test_local_provider_is_always_available(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    status = manager.provider_status('local')
    assert status['available'] is True
    assert status['enabled'] is True
    assert status['configured'] is True


def test_cross_device_access_requires_canonical_gateway(tmp_path):
    registry = Registry()
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=registry)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    with pytest.raises(RuntimeError, match='canonical device gateway'):
        manager.grant_remote_access('file:phone', requester_device_id='laptop')


def test_cross_device_access_requires_live_source(tmp_path):
    registry = Registry()
    gateway = Gateway(registry, online={'laptop'})
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=registry, device_gateway=gateway)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    with pytest.raises(RuntimeError, match='offline'):
        manager.grant_remote_access('file:phone', requester_device_id='laptop')


def test_existing_remote_lease_rechecks_source_reachability(tmp_path):
    registry = Registry()
    gateway = Gateway(registry, online={'phone', 'laptop'})
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=registry, device_gateway=gateway)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    assert manager.validate_remote_lease(lease['lease_id'])['persist_allowed'] is False
    gateway._online.remove('phone')
    with pytest.raises(RuntimeError, match='offline'):
        manager.validate_remote_lease(lease['lease_id'])


def test_disabling_remote_access_revokes_existing_leases(tmp_path):
    registry = Registry()
    gateway = Gateway(registry, online={'phone', 'laptop'})
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=registry, device_gateway=gateway)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    manager.update_settings(remote_access_enabled=False)
    with pytest.raises(PermissionError):
        manager.validate_remote_lease(lease['lease_id'])


def test_disabling_item_remote_access_revokes_existing_lease(tmp_path):
    registry = Registry()
    gateway = Gateway(registry, online={'phone', 'laptop'})
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=registry, device_gateway=gateway)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    manager.set_policy('file:phone', 'device_only', remote_access_allowed=False)
    with pytest.raises(PermissionError):
        manager.validate_remote_lease(lease['lease_id'])


def test_provider_location_requires_verified_connection(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.register_item('file:a', entity_type='file', primary_device_id='laptop', policy='sync_everywhere')
    manager.configure_provider('google_drive', enabled=True, credential_ref='connector:drive', verified=False)
    with pytest.raises(PermissionError, match='connected and verified'):
        manager.mark_location(
            'file:a',
            location_type='provider',
            location_id='drive-object',
            provider_id='google_drive',
        )


def test_verified_provider_can_be_recorded_when_policy_allows(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.register_item('file:a', entity_type='file', primary_device_id='laptop', policy='sync_everywhere')
    manager.configure_provider('google_drive', enabled=True, credential_ref='connector:drive', verified=True)
    item = manager.mark_location(
        'file:a',
        location_type='provider',
        location_id='drive-object',
        provider_id='google_drive',
    )
    assert any(location['provider_id'] == 'google_drive' for location in item['locations'])


def test_cloud_master_off_preserves_provider_preference_but_blocks_effective_use(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.configure_provider('dropbox', enabled=True, credential_ref='connector:dropbox', verified=True)
    assert manager.provider_status('dropbox')['available'] is True
    manager.update_settings(cloud_enabled=False)
    off = manager.provider_status('dropbox')
    assert off['configured_enabled'] is True
    assert off['enabled'] is False
    assert off['available'] is False
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    restored = manager.provider_status('dropbox')
    assert restored['configured_enabled'] is True
    assert restored['available'] is True


def test_device_only_transition_refuses_to_forget_remote_bytes(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.register_item('file:a', entity_type='file', primary_device_id='laptop', policy='sync_everywhere')
    manager.configure_provider('google_drive', enabled=True, credential_ref='connector:drive', verified=True)
    manager.mark_location(
        'file:a',
        location_type='provider',
        location_id='drive-object',
        provider_id='google_drive',
        has_bytes=True,
    )

    with pytest.raises(PermissionError, match='durable bytes remain'):
        manager.set_policy('file:a', 'device_only')

    item = manager.item('file:a')
    assert item['storage_policy'] == 'sync_everywhere'
    assert any(location['has_bytes'] for location in item['locations'] if location['provider_id'] == 'google_drive')


def test_device_only_transition_succeeds_after_verified_remote_removal(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.register_item('file:a', entity_type='file', primary_device_id='laptop', policy='sync_everywhere')
    manager.configure_provider('google_drive', enabled=True, credential_ref='connector:drive', verified=True)
    manager.mark_location(
        'file:a',
        location_type='provider',
        location_id='drive-object',
        provider_id='google_drive',
        has_bytes=True,
    )
    manager.mark_location(
        'file:a',
        location_type='provider',
        location_id='drive-object',
        provider_id='google_drive',
        has_bytes=False,
        available=True,
    )

    item = manager.set_policy('file:a', 'device_only')
    assert item['storage_policy'] == 'device_only'
    assert item['locations'] == [
        {
            'global_id': 'file:a',
            'location_type': 'device',
            'location_id': 'laptop',
            'provider_id': 'local',
            'has_bytes': True,
            'available': True,
            'updated_at': item['locations'][0]['updated_at'],
        }
    ]


def test_on_demand_is_first_class_but_not_sent_through_progress_channel(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=Registry())
    manager.register_item('file:on-demand', entity_type='file', primary_device_id='phone', policy='on_demand', metadata={'name': 'large.pdf'})
    event = manager.prepare_sync_event('file:on-demand', origin_device_id='phone', payload={'name': 'large.pdf', 'size': 12345})
    assert event['storage_policy'] == 'on_demand'
    assert manager.item('file:on-demand')['storage_policy'] == 'on_demand'
    assert manager.pending_progress_events('laptop') == []


def _incoming_event(manager, *, global_id, origin, primary, version, payload, policy='progress_only', kind='update'):
    envelope = {
        'schema_version': manager.SYNC_SCHEMA_VERSION,
        'global_id': global_id,
        'entity_type': 'project',
        'storage_policy': policy,
        'primary_device_id': primary,
        'version': version,
        'origin_device_id': origin,
        'event_kind': kind,
        'payload': dict(payload),
    }
    envelope['payload_hash'] = _hash(envelope['payload'])
    envelope['event_id'] = _hash(manager._sync_identity_body(envelope))
    return envelope


def test_sync_event_identity_tamper_is_rejected(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=Registry())
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    event = manager.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'active'})
    event['event_id'] = '0' * 64
    with pytest.raises(ValueError, match='identity integrity'):
        manager.receive_sync_event('laptop', event)


def test_same_version_different_origin_becomes_conflict(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=Registry())
    manager.register_item('project:1', entity_type='project', primary_device_id='laptop', policy='progress_only', origin_device_id='laptop', metadata={'status': 'laptop'})
    event = _incoming_event(manager, global_id='project:1', origin='phone', primary='laptop', version=1, payload={'status': 'phone'})
    result = manager.receive_sync_event('laptop', event)
    assert result['conflict'] is True
    assert result['reason'] == 'concurrent_same_version'
    assert manager.item('project:1')['metadata']['status'] == 'laptop'


def test_version_gap_is_conflict_not_silent_last_write_wins(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3', device_registry=Registry())
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only', origin_device_id='phone', metadata={'status': 'v1'})
    event = _incoming_event(manager, global_id='project:1', origin='phone', primary='phone', version=3, payload={'status': 'v3'})
    result = manager.receive_sync_event('laptop', event)
    assert result['conflict'] is True
    assert result['reason'] == 'version_gap'
    assert manager.item('project:1')['version'] == 1
