from __future__ import annotations

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.provider_bridge import connect_runtime_provider, reconcile_runtime_providers, runtime_provider_reference


class DummyDrive:
    pass


def test_existing_drive_connection_is_reused_without_token_copy(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    runtime = {'integration_adapters': {'drive': DummyDrive()}}
    assert runtime_provider_reference('google_drive', runtime) == 'integration:drive'
    status = connect_runtime_provider(manager, runtime, 'google_drive')
    assert status['credential_ref'] == 'integration:drive'
    assert status['available'] is True
    assert status['config'] == {'authority': 'canonical_integration'}


def test_bridge_does_not_invent_unavailable_provider(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    with pytest.raises(RuntimeError, match='no verified canonical integration'):
        connect_runtime_provider(manager, {'integration_adapters': {}}, 'google_drive')


def test_reconcile_revokes_availability_when_canonical_adapter_disappears(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    manager.update_settings(cloud_enabled=True, cloud_mode='hybrid')
    runtime = {'integration_adapters': {'drive': DummyDrive()}}
    connect_runtime_provider(manager, runtime, 'google_drive')
    assert manager.provider_status('google_drive')['available'] is True
    runtime['integration_adapters'] = {}
    reconcile_runtime_providers(manager, runtime)
    status = manager.provider_status('google_drive')
    assert status['enabled'] is True
    assert status['available'] is False


def test_cloud_off_never_reconciles_provider_available(tmp_path):
    manager = PolicyEnforcedDataPlane(tmp_path / 'dp.sqlite3')
    runtime = {'integration_adapters': {'drive': DummyDrive()}}
    reconcile_runtime_providers(manager, runtime)
    assert manager.provider_status('google_drive')['available'] is False
