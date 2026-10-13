from __future__ import annotations

import pytest

from data_plane.manager import UnifiedDataPlane
from data_plane.policy import CloudMode, StoragePolicy


class FakeRegistry:
    def __init__(self, active=('phone', 'laptop')):
        self.active = set(active)
        self.scopes = {}

    def is_active(self, device_id):
        return device_id in self.active

    def authorize(self, device_id, scope):
        return device_id in self.active and self.scopes.get((device_id, scope), True)


class FakeGateway:
    def __init__(self, registry, online=('phone', 'laptop')):
        self.registry = registry
        self._online = set(online)

    def online(self):
        return sorted(device for device in self._online if self.registry.is_active(device))


def plane(tmp_path, *, online=('phone', 'laptop')):
    registry = FakeRegistry()
    gateway = FakeGateway(registry, online=online)
    return UnifiedDataPlane(tmp_path / 'data-plane.sqlite3', device_registry=registry, device_gateway=gateway), registry, gateway


def test_defaults_are_local_first_and_cloud_off(tmp_path):
    manager, _, _ = plane(tmp_path)
    config = manager.settings()
    assert config['cloud_enabled'] is False
    assert config['cloud_mode'] == CloudMode.LOCAL_ONLY.value
    assert config['default_policy'] == StoragePolicy.PROGRESS_ONLY.value
    assert config['remote_access_enabled'] is True


def test_cloud_master_off_blocks_provider_configuration(tmp_path):
    manager, _, _ = plane(tmp_path)
    with pytest.raises(PermissionError, match='disabled'):
        manager.configure_provider('google_drive', enabled=True, credential_ref='connector:google')


def test_cloud_on_never_claims_unverified_provider_available(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    status = manager.configure_provider(
        'google_drive',
        enabled=True,
        credential_ref='connector:google-drive-owner',
        verified=False,
    )
    assert status['configured'] is True
    assert status['enabled'] is True
    assert status['available'] is False


def test_disabling_cloud_disables_configured_providers(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    manager.configure_provider('dropbox', enabled=True, credential_ref='connector:dropbox', verified=True)
    assert manager.provider_status('dropbox')['available'] is True
    manager.update_settings(cloud_enabled=False)
    assert manager.provider_status('dropbox')['enabled'] is False
    assert manager.provider_status('dropbox')['available'] is False


def test_device_only_item_does_not_emit_sync_event_or_gain_other_copy(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item(
        'file:private',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
        metadata={'name': 'private.pdf'},
    )
    assert manager.prepare_sync_event('file:private', origin_device_id='phone', payload={'status': 'seen'}) is None
    with pytest.raises(PermissionError, match='cannot be copied'):
        manager.mark_location('file:private', location_type='device', location_id='laptop', has_bytes=True)


def test_device_only_rejects_cloud_byte_location_even_when_cloud_on(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    manager.register_item('file:a', entity_type='file', primary_device_id='phone', policy='device_only')
    with pytest.raises(PermissionError, match='cloud/provider'):
        manager.mark_location('file:a', location_type='provider', location_id='drive-object-1', provider_id='google_drive')


def test_progress_only_syncs_only_bounded_progress_fields(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    event = manager.prepare_sync_event(
        'project:1',
        origin_device_id='phone',
        payload={
            'project_name': 'Rudra',
            'status': 'in_progress',
            'next_step': 'Finish homepage',
            'private_detail': 'must stay here',
        },
    )
    assert event['payload'] == {
        'project_name': 'Rudra',
        'status': 'in_progress',
        'next_step': 'Finish homepage',
    }
    assert 'private_detail' not in event['payload']


def test_progress_sync_rejects_secret_or_raw_content(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    with pytest.raises(ValueError, match='secrets or raw content'):
        manager.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'ok', 'api_key': 'secret'})
    with pytest.raises(ValueError, match='secrets or raw content'):
        manager.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'ok', 'file_bytes': 'abc'})


def test_metadata_rejects_credentials(tmp_path):
    manager, _, _ = plane(tmp_path)
    with pytest.raises(ValueError, match='secrets'):
        manager.register_item(
            'file:bad',
            entity_type='file',
            primary_device_id='phone',
            metadata={'access_token': 'do-not-store'},
        )


def test_remote_view_requires_online_source_and_does_not_allow_persist(tmp_path):
    manager, _, _ = plane(tmp_path, online=('laptop',))
    manager.register_item(
        'file:phone',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
        remote_access_allowed=True,
        copy_allowed=False,
    )
    with pytest.raises(RuntimeError, match='offline'):
        manager.grant_remote_access('file:phone', requester_device_id='laptop')

    manager.device_gateway._online.add('phone')
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    assert lease['source_device_id'] == 'phone'
    assert lease['persist_allowed'] is False
    assert manager.validate_remote_lease(lease['lease_id'])['persist_allowed'] is False
    with pytest.raises(PermissionError, match='persistence'):
        manager.validate_remote_lease(lease['lease_id'], require_persist=True)


def test_remote_access_cannot_upgrade_view_to_copy_without_item_permission(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item(
        'file:phone',
        entity_type='file',
        primary_device_id='phone',
        policy='device_only',
        copy_allowed=False,
    )
    with pytest.raises(PermissionError, match='permanent copy'):
        manager.grant_remote_access(
            'file:phone',
            requester_device_id='laptop',
            allow_persist=True,
        )


def test_remote_access_master_switch_fail_closes(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    manager.update_settings(remote_access_enabled=False)
    with pytest.raises(PermissionError, match='disabled'):
        manager.grant_remote_access('file:phone', requester_device_id='laptop')


def test_revoked_device_loses_existing_lease(tmp_path):
    manager, registry, _ = plane(tmp_path)
    manager.register_item('file:phone', entity_type='file', primary_device_id='phone', policy='device_only')
    lease = manager.grant_remote_access('file:phone', requester_device_id='laptop')
    registry.active.remove('laptop')
    with pytest.raises(PermissionError, match='active device'):
        manager.validate_remote_lease(lease['lease_id'])


def test_sync_receipt_is_idempotent(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    event = manager.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'active'})
    first = manager.receive_sync_event('laptop', event)
    second = manager.receive_sync_event('laptop', event)
    assert first['applied'] is True
    assert second == {'applied': False, 'duplicate': True, 'event_id': event['event_id']}


def test_stale_sync_event_records_conflict_instead_of_overwriting(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    old = manager.prepare_sync_event('project:1', origin_device_id='phone', payload={'status': 'first'})
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    result = manager.receive_sync_event('laptop', old)
    assert result['applied'] is False
    assert result['conflict'] is True
    assert result['conflict_id']


def test_delete_is_a_tombstone_and_syncs_only_when_policy_allows(tmp_path):
    manager, _, _ = plane(tmp_path)
    manager.register_item('project:1', entity_type='project', primary_device_id='phone', policy='progress_only')
    result = manager.delete_item('project:1', origin_device_id='phone')
    assert result['item']['tombstone'] is True
    assert result['sync_event']['event_kind'] == 'delete'

    manager.register_item('file:only', entity_type='file', primary_device_id='phone', policy='device_only')
    result = manager.delete_item('file:only', origin_device_id='phone')
    assert result['item']['tombstone'] is True
    assert result['sync_event'] is None
