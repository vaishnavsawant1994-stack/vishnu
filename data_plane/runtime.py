from __future__ import annotations

from .device_sync import DeviceProgressSyncService
from .enforced import PolicyEnforcedDataPlane
from .manager import UnifiedDataPlane
from .provider_bridge import reconcile_runtime_providers


def get_data_plane(runtime: dict) -> UnifiedDataPlane:
    """Return the single fail-closed data-plane authority for this Vishnu runtime."""

    current = runtime.get('data_plane')
    if current is not None:
        reconcile_runtime_providers(current, runtime)
        return current
    settings = runtime['settings']
    manager = PolicyEnforcedDataPlane(
        settings.data_dir / 'data-plane.sqlite3',
        device_registry=runtime.get('device_registry'),
        device_gateway=runtime.get('device_gateway'),
        events=runtime.get('events'),
    )
    runtime['data_plane'] = manager
    reconcile_runtime_providers(manager, runtime)
    return manager


def ensure_data_plane_sync(runtime: dict, manager: UnifiedDataPlane | None = None):
    current = runtime.get('data_plane_sync')
    if current is not None:
        return current
    gateway = runtime.get('device_gateway')
    events = runtime.get('events')
    if gateway is None or events is None:
        return None
    manager = manager or get_data_plane(runtime)
    service = DeviceProgressSyncService(manager, gateway, events).start()
    runtime['data_plane_sync'] = service
    return service


def ensure_data_plane_tools(runtime: dict) -> UnifiedDataPlane:
    manager = get_data_plane(runtime)
    registry = runtime.get('tools')
    if registry is not None:
        from tools import data_access
        data_access.register(registry, manager)
    ensure_data_plane_sync(runtime, manager)
    return manager
