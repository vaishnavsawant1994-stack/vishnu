from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from security.approvals import parameter_hash
from integrations.discovery.generated_catalog import register_generated_capability, set_generated_capability_state
from integrations.discovery.generated_runtime import (
    attach_approved_generated_capability,
    detach_generated_capability,
    load_generated_manifest,
    validate_generated_manifest_authority,
)


@dataclass(frozen=True)
class ForgeActivationDecision:
    capability_id: str
    version: str
    package_ref: str
    manifest_digest: str
    ticket_id: str
    execution_id: str

    def parameters(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "version": self.version,
            "package_ref": self.package_ref,
            "manifest_digest": self.manifest_digest,
        }


class CapabilityActivationService:
    """Owner-approved activation/disable/rollback for generated capabilities."""

    ACTIVATE_TOOL = "capability_forge.activate"
    DISABLE_TOOL = "capability_forge.disable"
    ROLLBACK_TOOL = "capability_forge.rollback"

    def __init__(
        self,
        *,
        catalog,
        approvals,
        tools,
        data_root: str | Path,
        lifecycle=None,
        events=None,
    ) -> None:
        self.catalog = catalog
        self.approvals = approvals
        self.tools = tools
        self.data_root = Path(data_root).resolve()
        self.lifecycle = lifecycle
        self.events = events

    def _package_ref(self, package_path: str | Path) -> str:
        package = Path(package_path).resolve()
        try:
            return package.relative_to(self.data_root).as_posix()
        except ValueError as exc:
            raise PermissionError("generated capability package must live under Vishnu data_root") from exc

    @staticmethod
    def _execution_id(action: str, capability_id: str, version: str, manifest_digest: str) -> str:
        seed = f"{action}|{capability_id}|{version}|{manifest_digest}".encode("utf-8")
        return f"forge-{action}:{hashlib.sha256(seed).hexdigest()[:24]}"

    def _observer(self, capability_id: str, version: str):
        if self.lifecycle is None:
            return None

        def observe(*, ok: bool, duration_ms: float, error_code: str | None = None):
            self.lifecycle.record_invocation(
                capability_id=capability_id,
                version=version,
                ok=ok,
                duration_ms=duration_ms,
                error_code=error_code,
            )

        return observe

    def _begin_approved_dispatch(
        self,
        *,
        ticket_id: str,
        execution_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        owner_id: str,
        device_id: str | None,
        session_id: str | None,
        destination: str,
    ):
        record = self.approvals.record(str(ticket_id))
        if not record or record.get("status") != "approved":
            raise PermissionError("owner approval must be granted before Forge dispatch")
        ticket = record["ticket"]
        if ticket.execution_id != execution_id or ticket.tool_name != tool_name:
            raise PermissionError("Forge approval scope mismatch")
        if ticket.parameter_hash != parameter_hash(parameters):
            raise PermissionError("Forge approval parameters changed after approval")
        if ticket.owner_id and ticket.owner_id != str(owner_id or "owner"):
            raise PermissionError("Forge approval owner mismatch")
        if ticket.device_id is not None and ticket.device_id != device_id:
            raise PermissionError("Forge approval device mismatch")
        if ticket.session_id is not None and ticket.session_id != session_id:
            raise PermissionError("Forge approval session mismatch")
        if ticket.security_epoch != self.approvals.current_security_epoch():
            raise PermissionError("Forge approval security epoch changed")
        if ticket.destination != str(destination or "")[:1000]:
            raise PermissionError("Forge approval destination mismatch")
        if ticket.data_classification != "internal":
            raise PermissionError("Forge approval data classification mismatch")
        dispatch = self.approvals.begin_dispatch(
            str(ticket_id),
            worker_id="capability-forge",
            lease_seconds=30,
        )
        if not dispatch.get("dispatch"):
            raise PermissionError(f"Forge approval dispatch is {dispatch.get('status')}")
        return ticket

    def _complete_dispatch(self, ticket_id: str, outcome: dict[str, Any]) -> None:
        self.approvals.complete_dispatch(str(ticket_id), outcome)

    def _mark_dispatch_uncertain(self, ticket_id: str) -> None:
        self.approvals.mark_recovery_required(str(ticket_id), "capability_forge_dispatch_failed")

    def request_activation(
        self,
        package,
        *,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> ForgeActivationDecision:
        manifest = dict(package.manifest)
        validate_generated_manifest_authority(manifest)
        package_ref = self._package_ref(package.package_path)
        decision = ForgeActivationDecision(
            capability_id=str(package.capability_id),
            version=str(package.version),
            package_ref=package_ref,
            manifest_digest=str(package.manifest_digest),
            ticket_id="",
            execution_id=self._execution_id(
                "activate", str(package.capability_id), str(package.version), str(package.manifest_digest)
            ),
        )
        ticket = self.approvals.create(
            decision.execution_id,
            self.ACTIVATE_TOOL,
            decision.parameters(),
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=decision.capability_id,
            data_classification="internal",
        )
        return ForgeActivationDecision(
            capability_id=decision.capability_id,
            version=decision.version,
            package_ref=decision.package_ref,
            manifest_digest=decision.manifest_digest,
            ticket_id=ticket.id,
            execution_id=decision.execution_id,
        )

    def activate(
        self,
        package,
        *,
        ticket_id: str,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        manifest = dict(package.manifest)
        validate_generated_manifest_authority(manifest)
        package_ref = self._package_ref(package.package_path)
        execution_id = self._execution_id(
            "activate", str(package.capability_id), str(package.version), str(package.manifest_digest)
        )
        parameters = {
            "capability_id": str(package.capability_id),
            "version": str(package.version),
            "package_ref": package_ref,
            "manifest_digest": str(package.manifest_digest),
        }
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id),
            execution_id=execution_id,
            tool_name=self.ACTIVATE_TOOL,
            parameters=parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(package.capability_id),
        )
        payload = package.catalog_payload(package_ref=package_ref, state="active")
        try:
            register_generated_capability(self.catalog, payload)
            tool = attach_approved_generated_capability(
                payload,
                tools=self.tools,
                data_root=self.data_root,
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
                capability_id=str(package.capability_id),
                version=str(package.version),
                activation_id=activation_id,
                approval_id=str(ticket_id),
            )
        self._complete_dispatch(str(ticket_id), {"action": "activated", "capability_id": str(package.capability_id), "version": str(package.version)})
        return {
            "capability": payload,
            "tool": tool.name,
            "activation_id": activation_id,
            "approved": True,
        }

    def request_disable(
        self,
        capability_id: str,
        *,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        capability = self.catalog.get(str(capability_id))
        if capability is None or capability.get("type") != "generated_capability":
            raise KeyError(capability_id)
        parameters = {
            "capability_id": str(capability_id),
            "version": str(capability.get("version") or ""),
            "manifest_digest": str(capability.get("manifest_digest") or ""),
        }
        execution_id = self._execution_id(
            "disable", str(capability_id), parameters["version"], parameters["manifest_digest"]
        )
        ticket = self.approvals.create(
            execution_id,
            self.DISABLE_TOOL,
            parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(capability_id),
            data_classification="internal",
        )
        return ticket.id

    def disable(
        self,
        capability_id: str,
        *,
        ticket_id: str,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        capability = self.catalog.get(str(capability_id))
        if capability is None or capability.get("type") != "generated_capability":
            raise KeyError(capability_id)
        parameters = {
            "capability_id": str(capability_id),
            "version": str(capability.get("version") or ""),
            "manifest_digest": str(capability.get("manifest_digest") or ""),
        }
        execution_id = self._execution_id(
            "disable", str(capability_id), parameters["version"], parameters["manifest_digest"]
        )
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id),
            execution_id=execution_id,
            tool_name=self.DISABLE_TOOL,
            parameters=parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(capability_id),
        )
        try:
            set_generated_capability_state(self.catalog, str(capability_id), "disabled")
            detach_generated_capability(self.tools, str(capability_id))
        except Exception:
            self._mark_dispatch_uncertain(str(ticket_id))
            raise
        if self.lifecycle is not None:
            self.lifecycle.disable_active(str(capability_id))
        if self.events is not None:
            self.events.emit("capability_forge.disabled", capability_id=str(capability_id), approval_id=str(ticket_id))
        self._complete_dispatch(str(ticket_id), {"action": "disabled", "capability_id": str(capability_id)})
        return {"capability_id": str(capability_id), "state": "disabled", "approved": True}

    def request_rollback(
        self,
        capability_id: str,
        *,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if self.lifecycle is None:
            raise RuntimeError("Forge lifecycle store is required for rollback")
        target = self.lifecycle.previous_activation(str(capability_id))
        if not target:
            raise ValueError("no previous generated capability version is available")
        payload = dict(target.get("payload") or {}).get("catalog_payload")
        if not isinstance(payload, dict):
            raise RuntimeError("previous activation is missing catalog lineage")
        parameters = {
            "capability_id": str(capability_id),
            "target_activation_id": str(target["id"]),
            "target_version": str(target["version"]),
            "manifest_digest": str(target["manifest_digest"]),
        }
        execution_id = self._execution_id(
            "rollback", str(capability_id), parameters["target_version"], parameters["manifest_digest"]
        )
        ticket = self.approvals.create(
            execution_id,
            self.ROLLBACK_TOOL,
            parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(capability_id),
            data_classification="internal",
        )
        return ticket.id, target

    def rollback(
        self,
        capability_id: str,
        *,
        ticket_id: str,
        target_activation_id: str,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if self.lifecycle is None:
            raise RuntimeError("Forge lifecycle store is required for rollback")
        target = self.lifecycle.get_activation(str(target_activation_id))
        if not target or str(target.get("capability_id")) != str(capability_id):
            raise KeyError(target_activation_id)
        payload = dict(target.get("payload") or {}).get("catalog_payload")
        if not isinstance(payload, dict):
            raise RuntimeError("previous activation is missing catalog lineage")
        parameters = {
            "capability_id": str(capability_id),
            "target_activation_id": str(target_activation_id),
            "target_version": str(target["version"]),
            "manifest_digest": str(target["manifest_digest"]),
        }
        execution_id = self._execution_id(
            "rollback", str(capability_id), parameters["target_version"], parameters["manifest_digest"]
        )
        self._begin_approved_dispatch(
            ticket_id=str(ticket_id),
            execution_id=execution_id,
            tool_name=self.ROLLBACK_TOOL,
            parameters=parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(capability_id),
        )
        package_path = self.data_root / str(target["package_ref"])
        manifest = load_generated_manifest(package_path, expected_digest=str(target["manifest_digest"]))
        validate_generated_manifest_authority(manifest)
        restored = {**payload, "state": "active"}
        register_generated_capability(self.catalog, restored)
        attach_approved_generated_capability(
            restored,
            tools=self.tools,
            data_root=self.data_root,
            on_invocation=self._observer(str(capability_id), str(target["version"])),
        )
        active = self.lifecycle.rollback_to(str(capability_id), str(target_activation_id))
        if self.events is not None:
            self.events.emit(
                "capability_forge.rolled_back",
                capability_id=str(capability_id),
                version=str(target["version"]),
                activation_id=str(target_activation_id),
                approval_id=str(ticket_id),
            )
        self._complete_dispatch(str(ticket_id), {"action": "rolled_back", "capability_id": str(capability_id), "version": str(target["version"])})
        return {
            "capability": restored,
            "activation": active,
            "approved": True,
        }
