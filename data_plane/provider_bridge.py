from __future__ import annotations

from typing import Any


_RUNTIME_PROVIDER_MAP = {
    'google_drive': ('drive', 'integration:drive'),
}


def runtime_provider_reference(provider_id: str, runtime: dict[str, Any]) -> str | None:
    mapping = _RUNTIME_PROVIDER_MAP.get(str(provider_id))
    if not mapping:
        return None
    adapter_id, reference = mapping
    adapters = runtime.get('integration_adapters') or {}
    return reference if adapters.get(adapter_id) is not None else None


def connect_runtime_provider(manager, runtime: dict[str, Any], provider_id: str):
    """Bind a storage provider to an already-governed Vishnu integration.

    No provider token is copied into the data-plane database. The data plane
    records only an opaque integration reference and treats the provider as
    verified only while the canonical integration adapter actually exists.
    """

    provider_id = str(provider_id)
    reference = runtime_provider_reference(provider_id, runtime)
    if reference is None:
        raise RuntimeError('no verified canonical integration is available for this storage provider')
    return manager.configure_provider(
        provider_id,
        enabled=True,
        credential_ref=reference,
        config={'authority': 'canonical_integration'},
        verified=True,
    )


def reconcile_runtime_providers(manager, runtime: dict[str, Any]) -> None:
    if not manager.settings()['cloud_enabled']:
        return
    for provider_id, (_adapter_id, expected_ref) in _RUNTIME_PROVIDER_MAP.items():
        status = manager.provider_status(provider_id)
        if not status['configured'] or not status['enabled']:
            continue
        reference = runtime_provider_reference(provider_id, runtime)
        if reference == expected_ref:
            if not status['available']:
                manager.configure_provider(
                    provider_id,
                    enabled=True,
                    credential_ref=expected_ref,
                    config={'authority': 'canonical_integration'},
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
