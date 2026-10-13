from __future__ import annotations

import os

from .device_sync import DeviceProgressSyncService
from .hardened import HardenedDataPlane
from .manager import UnifiedDataPlane
from .provider_bridge import reconcile_runtime_providers


def _ensure_native_storage_bridges(runtime: dict) -> dict:
    """Populate opt-in native bridge handles without persisting their locations."""
    bridges = runtime.setdefault('native_storage_bridges', {})
    if 'icloud_bridge' not in bridges:
        root = os.getenv('VISHNU_ICLOUD_BRIDGE_PATH', '').strip()
        if root:
            bridges['icloud_bridge'] = root
    return bridges


def get_data_plane(runtime: dict) -> UnifiedDataPlane | None:
    """Return the single fail-closed data-plane authority for this Vishnu runtime."""
    _ensure_native_storage_bridges(runtime)
    current = runtime.get('data_plane')
    if current is not None:
        reconcile_runtime_providers(current, runtime)
        return current
    settings = runtime.get('settings')
    if settings is None or getattr(settings, 'data_dir', None) is None:
        return None
    manager = HardenedDataPlane(
        settings.data_dir / 'data-plane.sqlite3',
        device_registry=runtime.get('device_registry'),
        device_gateway=runtime.get('device_gateway'),
        events=runtime.get('events'),
    )
    runtime['data_plane'] = manager
    reconcile_runtime_providers(manager, runtime)
    return manager


def ensure_data_plane_security(runtime: dict, manager: UnifiedDataPlane | None = None):
    """Attach the secure byte/envelope layer only when the canonical vault exists."""
    current = runtime.get('data_plane_byte_transport')
    if current is not None:
        return current
    manager = manager or get_data_plane(runtime)
    if manager is None:
        return None
    vault = runtime.get('vault')
    if vault is None:
        return None
    from .byte_transport import LeaseBoundByteTransport
    from .envelopes import EnvelopeKeyManager

    envelopes = runtime.get('data_plane_envelopes')
    if envelopes is None:
        envelopes = EnvelopeKeyManager(manager, vault)
        runtime['data_plane_envelopes'] = envelopes
    transport = LeaseBoundByteTransport(
        manager,
        envelopes,
        gateway=runtime.get('device_gateway'),
        events=runtime.get('events'),
    )
    runtime['data_plane_byte_transport'] = transport
    manager.envelopes = envelopes
    manager.byte_transport = transport
    return transport


def ensure_data_plane_provider_store(runtime: dict, manager: UnifiedDataPlane | None = None):
    """Attach ciphertext-only provider storage using existing Vishnu authorities.

    Direct vault-backed providers use the canonical SecretVault. Google Drive is
    delegated to the existing governed Drive integration. Apple iCloud uses only
    an explicitly configured Apple-host native bridge. No bridge stores provider
    credentials or native filesystem paths in data-plane metadata.
    """
    current = runtime.get('data_plane_provider_store')
    if current is not None:
        return current
    _ensure_native_storage_bridges(runtime)
    manager = manager or get_data_plane(runtime)
    if manager is None or runtime.get('vault') is None:
        return None
    if runtime.get('data_plane_envelopes') is None:
        ensure_data_plane_security(runtime, manager)
    envelopes = runtime.get('data_plane_envelopes')
    if envelopes is None:
        return None
    from .provider_adapters import EncryptedProviderStore
    from .provider_bridges import GovernedProviderAdapterFactory

    factory = GovernedProviderAdapterFactory(manager, runtime['vault'], runtime=runtime)
    store = EncryptedProviderStore(manager, envelopes, factory)
    runtime['data_plane_provider_factory'] = factory
    runtime['data_plane_provider_store'] = store
    manager.provider_store = store
    return store


def build_data_plane_relay(runtime: dict, *, local_device_id: str):
    """Build the optional opaque relay only from an explicitly verified Vishnu Cloud config.

    The relay is not started automatically and never becomes device or sync
    authority. Callers must opt in with a concrete local trusted-device id.
    """
    manager = get_data_plane(runtime)
    vault = runtime.get('vault')
    if manager is None or vault is None:
        return None
    status = manager.provider_status('vishnu_cloud')
    if not status.get('available'):
        return None
    config = status.get('config') or {}
    endpoint = str(config.get('relay_endpoint') or config.get('endpoint') or '').strip()
    credential_ref = str(status.get('credential_ref') or '').strip()
    if not endpoint or not credential_ref:
        return None
    from .relay import OpaqueVishnuRelayClient

    return OpaqueVishnuRelayClient(
        manager,
        vault,
        endpoint=endpoint,
        credential_ref=credential_ref,
        local_device_id=str(local_device_id),
    )


def ensure_data_plane_sync(runtime: dict, manager: UnifiedDataPlane | None = None):
    current = runtime.get('data_plane_sync')
    if current is not None:
        return current
    gateway = runtime.get('device_gateway')
    events = runtime.get('events')
    if gateway is None or events is None:
        return None
    manager = manager or get_data_plane(runtime)
    if manager is None:
        return None
    service = DeviceProgressSyncService(manager, gateway, events).start()
    runtime['data_plane_sync'] = service
    return service


def ensure_data_plane_tools(runtime: dict) -> UnifiedDataPlane | None:
    manager = get_data_plane(runtime)
    if manager is None:
        return None
    ensure_data_plane_security(runtime, manager)
    ensure_data_plane_provider_store(runtime, manager)
    registry = runtime.get('tools')
    if registry is not None:
        from tools import data_access
        data_access.register(registry, manager)
    ensure_data_plane_sync(runtime, manager)
    return manager
