from __future__ import annotations

from typing import Any, Mapping


_RUNTIME_PROVIDER_MAP = {
    'google_drive': ('integration_adapters', 'drive', 'integration:drive', 'canonical_integration'),
    'icloud_bridge': ('native_storage_bridges', 'icloud_bridge', 'native:icloud_bridge', 'native_runtime_bridge'),
}


def runtime_provider_reference(provider_id: str, runtime: dict[str, Any]) -> str | None:
    mapping = _RUNTIME_PROVIDER_MAP.get(str(provider_id))
    if not mapping:
        return None
    collection_name, adapter_id, reference, _authority = mapping
    collection = runtime.get(collection_name) or {}
    return reference if collection.get(adapter_id) is not None else None


def connect_runtime_provider(
    manager,
    runtime: dict[str, Any],
    provider_id: str,
    *,
    config: Mapping[str, Any] | None = None,
):
    """Bind a storage provider to an already-governed Vishnu runtime authority.

    No provider token, filesystem root, or other secret/location value is copied
    into the data-plane database. Provider config may contain only opaque refs.
    """

    provider_id = str(provider_id)
    mapping = _RUNTIME_PROVIDER_MAP.get(provider_id)
    if mapping is None:
        raise RuntimeError('storage provider has no canonical runtime bridge')
    reference = runtime_provider_reference(provider_id, runtime)
    if reference is None:
        raise RuntimeError('no verified canonical integration/native bridge is available for this storage provider')
    authority = mapping[3]
    safe_config = dict(config or {})
    safe_config['authority'] = authority
    return manager.configure_provider(
        provider_id,
        enabled=True,
        credential_ref=reference,
        config=safe_config,
        verified=True,
    )


def reconcile_runtime_providers(manager, runtime: dict[str, Any]) -> None:
    if not manager.settings()['cloud_enabled']:
        return
    for provider_id, (_collection, _adapter_id, expected_ref, authority) in _RUNTIME_PROVIDER_MAP.items():
        status = manager.provider_status(provider_id)
        if not status['configured'] or not status['enabled']:
            continue
        reference = runtime_provider_reference(provider_id, runtime)
        if reference == expected_ref:
            if not status['available']:
                config = dict(status.get('config') or {})
                config['authority'] = authority
                manager.configure_provider(
                    provider_id,
                    enabled=True,
                    credential_ref=expected_ref,
                    config=config,
                    verified=True,
                )
        elif status['available']:
            manager.configure_provider(
                provider_id,
                enabled=True,
                credential_ref=status['credential_ref'],
                config=status['config'],
                verified=False,
            )
