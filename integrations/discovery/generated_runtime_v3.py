from __future__ import annotations

from pathlib import Path

from integrations.discovery.generated_catalog import set_generated_capability_state
from integrations.discovery.generated_runtime import resolve_generated_package
from integrations.discovery.generated_runtime_v2 import (
    attach_generated_capability,
    detach_generated_capability_v2,
)


def rehydrate_generated_capabilities_v3(
    catalog,
    *,
    tools,
    data_root: str | Path,
    action_service,
    provenance=None,
    invocation_observer=None,
    events=None,
) -> list[str]:
    """Rehydrate generated tools, enforcing V3 provenance when catalog-marked.

    Legacy qualified V1/V2 catalog entries remain backward compatible. Entries
    activated under V3 are marked provenance_required; if their package cannot
    be verified on restart, authority is removed by disabling the catalog item
    and detaching any stale generated tool.
    """
    attached: list[str] = []
    for capability in catalog.all():
        if capability.get("type") != "generated_capability" or capability.get("state") != "active":
            continue
        capability_id = str(capability.get("id") or "")
        observer = invocation_observer(capability, {}) if invocation_observer is not None else None
        try:
            if capability.get("provenance_required"):
                if provenance is None:
                    raise RuntimeError("Capability Forge V3 provenance verifier is unavailable")
                package_path = resolve_generated_package(data_root, str(capability.get("package_ref") or ""))
                evidence = provenance.verify(
                    package_path,
                    expected_manifest_digest=str(capability.get("manifest_digest") or ""),
                )
                expected_key = str(capability.get("provenance_key_id") or "")
                if expected_key and evidence.get("key_id") != expected_key:
                    raise PermissionError("generated capability provenance key changed")
            attach_generated_capability(
                capability,
                tools=tools,
                data_root=data_root,
                action_service=action_service,
                on_invocation=observer,
            )
            attached.append(capability_id)
        except Exception as exc:
            if capability.get("provenance_required"):
                try:
                    set_generated_capability_state(catalog, capability_id, "disabled")
                except Exception:
                    pass
                try:
                    detach_generated_capability_v2(tools, capability_id)
                except Exception:
                    pass
                if events is not None:
                    events.emit(
                        "capability_forge.rehydration_quarantined",
                        capability_id=capability_id,
                        error_type=type(exc).__name__,
                    )
            elif events is not None:
                events.emit(
                    "capability_forge.rehydration_skipped",
                    capability_id=capability_id,
                    error_type=type(exc).__name__,
                )
    return attached
