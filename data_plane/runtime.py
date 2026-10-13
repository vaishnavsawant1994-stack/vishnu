from __future__ import annotations

from .device_sync import DeviceProgressSyncService
from .hardened import HardenedDataPlane
from .manager import UnifiedDataPlane
from .provider_bridge import reconcile_runtime_providers


def get_data_plane(runtime: dict) -> UnifiedDataPlane | None:
    """Return the single fail-closed data-plane authority for this Vishnu runtime."""
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


def ensure_data_plane_storage(runtime: dict, manager: UnifiedDataPlane | None = None):
    """Attach optional provider/relay services without changing data authority."""
    manager = manager or get_data_plane(runtime)
    if manager is None:
        return None
    settings = runtime.get('settings')
    if settings is None or getattr(settings, 'data_dir', None) is None:
        return None

    relay = runtime.get('data_plane_relay')
    if relay is None:
        from .relay import OpaqueDataRelay
        relay = OpaqueDataRelay(
            settings.data_dir / 'data-relay.sqlite3',
            device_registry=runtime.get('device_registry'),
        )
        runtime['data_plane_relay'] = relay
        manager.data_relay = relay

    ensure_data_plane_security(runtime, manager)
    envelopes = runtime.get('data_plane_envelopes')
    vault = runtime.get('vault')
    if envelopes is None or vault is None:
        return relay

    service = runtime.get('data_plane_provider_storage')
    if service is None:
        from .storage_adapters import EncryptedProviderService, StorageAdapterManager
        adapters = StorageAdapterManager(
            manager,
            vault,
            connector_resolver=runtime.get('storage_connector_resolver'),
        )
        service = EncryptedProviderService(manager, envelopes, adapters)
        runtime['data_plane_storage_adapters'] = adapters
        runtime['data_plane_provider_storage'] = service
        manager.storage_adapters = adapters
        manager.provider_storage = service
    return service


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
    ensure_data_plane_storage(runtime, manager)
    registry = runtime.get('tools')
    if registry is not None:
        from tools import data_access
        data_access.register(registry, manager)
    ensure_data_plane_sync(runtime, manager)
    return manager
