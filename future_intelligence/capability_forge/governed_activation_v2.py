from __future__ import annotations

from typing import Any

from integrations.discovery.generated_catalog import register_generated_capability, set_generated_capability_state
from integrations.discovery.generated_runtime import load_generated_manifest
from integrations.discovery.generated_runtime_v2 import (
    attach_generated_capability,
    detach_generated_capability_v2,
    validate_generated_manifest_authority_v2,
)

from .activation import ForgeActivationDecision
from .governed_activation import GovernedCapabilityActivationService


class GovernedCapabilityActivationServiceV2(GovernedCapabilityActivationService):
    """V1 activation authority extended only with qualified V2 runtime adapters."""

    def __init__(self, *args, action_service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_service = action_service

    def request_activation(self, package, *, owner_id="owner", device_id=None, session_id=None):
        self._require_packaged_lineage(package)
        manifest = dict(package.manifest)
        if manifest.get("runtime") != "governed_action_v2":
            return super().request_activation(package, owner_id=owner_id, device_id=device_id, session_id=session_id)
        validate_generated_manifest_authority_v2(manifest)
        package_ref = self._package_ref(package.package_path)
        execution_id = self._execution_id("activate", str(package.capability_id), str(package.version), str(package.manifest_digest))
        parameters = {
            "capability_id": str(package.capability_id),
            "version": str(package.version),
            "package_ref": package_ref,
            "manifest_digest": str(package.manifest_digest),
        }
        ticket = self.approvals.create(
            execution_id,
            self.ACTIVATE_TOOL,
            parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(package.capability_id),
            data_classification="internal",
        )
        return ForgeActivationDecision(
            capability_id=str(package.capability_id),
            version=str(package.version),
            package_ref=package_ref,
            manifest_digest=str(package.manifest_digest),
            ticket_id=ticket.id,
            execution_id=execution_id,
        )

    def activate(self, package, *, ticket_id, owner_id="owner", device_id=None, session_id=None) -> dict[str, Any]:
        self._require_packaged_lineage(package)
        manifest = dict(package.manifest)
        if manifest.get("runtime") != "governed_action_v2":
            return super().activate(package, ticket_id=ticket_id, owner_id=owner_id, device_id=device_id, session_id=session_id)
        validate_generated_manifest_authority_v2(manifest)
        if self.action_service is None:
            raise RuntimeError("Forge generated action service is unavailable")
        package_ref = self._package_ref(package.package_path)
        execution_id = self._execution_id("activate", str(package.capability_id), str(package.version), str(package.manifest_digest))
        parameters = {
            "capability_id": str(package.capability_id),
            "version": str(package.version),
            "package_ref": package_ref,
            "manifest_digest": str(package.manifest_digest),
        }
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id), execution_id=execution_id, tool_name=self.ACTIVATE_TOOL,
            parameters=parameters, owner_id=owner_id, device_id=device_id, session_id=session_id,
            destination=str(package.capability_id),
        )
        payload = package.catalog_payload(package_ref=package_ref, state="active")
        try:
            register_generated_capability(self.catalog, payload)
            tool = attach_generated_capability(
                payload,
                tools=self.tools,
                data_root=self.data_root,
                action_service=self.action_service,
                on_invocation=self._observer(str(package.capability_id), str(package.version)),
            )
        except Exception:
            try:
                set_generated_capability_state(self.catalog, str(package.capability_id), "disabled")
            except Exception:
                pass
            self._mark_dispatch_uncertain(str(ticket_id))
            raise
        activation_id = f"activation:{package.capability_id}:{package.version}:{package.manifest_digest[:16]}"
        if self.lifecycle is not None:
            self.lifecycle.record_activation(
                activation_id=activation_id,
                capability_id=str(package.capability_id),
                version=str(package.version),
                package_ref=package_ref,
                manifest_digest=str(package.manifest_digest),
                build_id=str(package.build_id),
                status="active",
                payload={"catalog_payload": payload, "approval_id": str(ticket_id)},
            )
        if self.events is not None:
            self.events.emit(
                "capability_forge.activated",
                capability_id=str(package.capability_id), version=str(package.version),
                activation_id=activation_id, approval_id=str(ticket_id), runtime="governed_action_v2",
            )
        self._complete_dispatch(str(ticket_id), {"action": "activated", "capability_id": str(package.capability_id), "version": str(package.version)})
        return {"capability": payload, "tool": tool.name, "activation_id": activation_id, "approved": True}

    def disable(self, capability_id: str, *, ticket_id: str, owner_id="owner", device_id=None, session_id=None) -> dict[str, Any]:
        capability = self.catalog.get(str(capability_id))
        if not capability or capability.get("runtime") != "governed_action_v2":
            return super().disable(capability_id, ticket_id=ticket_id, owner_id=owner_id, device_id=device_id, session_id=session_id)
        parameters = {
            "capability_id": str(capability_id),
            "version": str(capability.get("version") or ""),
            "manifest_digest": str(capability.get("manifest_digest") or ""),
        }
        execution_id = self._execution_id("disable", str(capability_id), parameters["version"], parameters["manifest_digest"])
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id), execution_id=execution_id, tool_name=self.DISABLE_TOOL,
            parameters=parameters, owner_id=owner_id, device_id=device_id, session_id=session_id,
            destination=str(capability_id),
        )
        try:
            set_generated_capability_state(self.catalog, str(capability_id), "disabled")
            detach_generated_capability_v2(self.tools, str(capability_id))
        except Exception:
            self._mark_dispatch_uncertain(str(ticket_id))
            raise
        if self.lifecycle is not None:
            self.lifecycle.disable_active(str(capability_id))
        if self.events is not None:
            self.events.emit("capability_forge.disabled", capability_id=str(capability_id), approval_id=str(ticket_id))
        self._complete_dispatch(str(ticket_id), {"action": "disabled", "capability_id": str(capability_id)})
        return {"capability_id": str(capability_id), "state": "disabled", "approved": True}

    def rollback(self, capability_id: str, *, ticket_id: str, target_activation_id: str, owner_id="owner", device_id=None, session_id=None) -> dict[str, Any]:
        if self.lifecycle is None:
            raise RuntimeError("Forge lifecycle store is required for rollback")
        target = self.lifecycle.get_activation(str(target_activation_id))
        payload = dict(target.get("payload") or {}).get("catalog_payload") if target else None
        if not target or str(target.get("capability_id")) != str(capability_id) or not isinstance(payload, dict):
            return super().rollback(
                capability_id, ticket_id=ticket_id, target_activation_id=target_activation_id,
                owner_id=owner_id, device_id=device_id, session_id=session_id,
            )
        if payload.get("runtime") != "governed_action_v2":
            return super().rollback(
                capability_id, ticket_id=ticket_id, target_activation_id=target_activation_id,
                owner_id=owner_id, device_id=device_id, session_id=session_id,
            )
        if self.action_service is None:
            raise RuntimeError("Forge generated action service is unavailable")
        parameters = {
            "capability_id": str(capability_id),
            "target_activation_id": str(target_activation_id),
            "target_version": str(target["version"]),
            "manifest_digest": str(target["manifest_digest"]),
        }
        execution_id = self._execution_id("rollback", str(capability_id), parameters["target_version"], parameters["manifest_digest"])
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id), execution_id=execution_id, tool_name=self.ROLLBACK_TOOL,
            parameters=parameters, owner_id=owner_id, device_id=device_id, session_id=session_id,
            destination=str(capability_id),
        )
        package_path = self.data_root / str(target["package_ref"])
        manifest = load_generated_manifest(package_path, expected_digest=str(target["manifest_digest"]))
        validate_generated_manifest_authority_v2(manifest)
        restored = {**payload, "state": "active"}
        try:
            register_generated_capability(self.catalog, restored)
            attach_generated_capability(
                restored,
                tools=self.tools,
                data_root=self.data_root,
                action_service=self.action_service,
                on_invocation=self._observer(str(capability_id), str(target["version"])),
            )
            active = self.lifecycle.rollback_to(str(capability_id), str(target_activation_id))
        except Exception:
            self._mark_dispatch_uncertain(str(ticket_id))
            raise
        if self.events is not None:
            self.events.emit(
                "capability_forge.rolled_back", capability_id=str(capability_id),
                version=str(target["version"]), activation_id=str(target_activation_id), approval_id=str(ticket_id),
            )
        self._complete_dispatch(str(ticket_id), {"action": "rolled_back", "capability_id": str(capability_id), "version": str(target["version"])})
        return {"capability": restored, "activation": active, "approved": True}
