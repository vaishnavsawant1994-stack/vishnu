from __future__ import annotations

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane


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
        return sorted(self._online)


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
