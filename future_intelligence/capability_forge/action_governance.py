from __future__ import annotations

from .action_runtime import GeneratedActionService, _bounded_names, _host_within, _walk_named_values
from security.approvals import parameter_hash
from tools.registry import Risk


class GovernedGeneratedActionService(GeneratedActionService):
    """Adds strict data, scope aliases and canonical ticket revalidation before V2 commit."""

    @staticmethod
    def _validate_scope(manifest: dict, parameters: dict, risk: Risk) -> None:
        GeneratedActionService._validate_scope(manifest, parameters, risk)
        permissions = dict(manifest.get("permissions") or {})
        hosts = tuple(x.casefold().strip(".") for x in _bounded_names(permissions.get("network_hosts")))
        # Common endpoint aliases are intentionally checked in addition to the
        # V1-compatible url/domain keys. ToolRegistry destination policy remains
        # authoritative, but Forge also fails early on nested endpoint smuggling.
        for value in _walk_named_values(
            parameters,
            keys={"endpoint", "endpoint_url", "base_url", "uri", "webhook_url", "callback_url", "redirect_uri"},
        ):
            if not hosts or not _host_within(value, hosts):
                raise PermissionError("generated action network destination is outside the Forge host scope")

    def stage(self, *args, **kwargs):
        classification = str(kwargs.get("data_classification") or "internal").strip().lower()
        if classification != "internal":
            raise PermissionError("generated actions cannot receive sensitive, secret, or restricted data")
        return super().stage(*args, **kwargs)

    def commit(self, proposal_id: str, **kwargs):
        proposal = self.get(proposal_id)
        if str(proposal.get("data_classification") or "internal").strip().lower() != "internal":
            raise PermissionError("generated actions cannot commit sensitive, secret, or restricted data")
        owner_id = str(kwargs.get("owner_id") or "owner")
        device_id = kwargs.get("device_id")
        session_id = kwargs.get("session_id")
        current_epoch = self.approvals.current_security_epoch()
        for call in proposal.get("calls") or []:
            ticket_id = call.get("approval_id")
            if not ticket_id:
                continue
            record = self.approvals.record(str(ticket_id))
            if not record:
                raise PermissionError("all generated action tickets must be approved before commit")
            ticket = record["ticket"]
            # Report an epoch fence before the generic status check. Advancing the
            # canonical security epoch invalidates approved tickets, and callers
            # need the precise reason instead of a misleading approval-state error.
            if ticket.security_epoch != current_epoch:
                raise PermissionError("generated action approval security epoch changed")
            if record.get("status") != "approved":
                raise PermissionError("all generated action tickets must be approved before commit")
            if ticket.execution_id != f"forge-action:{proposal['id']}" or ticket.tool_name != call["tool"]:
                raise PermissionError("generated action approval scope changed")
            if ticket.parameter_hash != parameter_hash(call["parameters"]):
                raise PermissionError("generated action approval parameters changed")
            if ticket.owner_id and ticket.owner_id != owner_id:
                raise PermissionError("generated action approval owner changed")
            if ticket.device_id is not None and ticket.device_id != device_id:
                raise PermissionError("generated action approval device changed")
            if ticket.session_id is not None and ticket.session_id != session_id:
                raise PermissionError("generated action approval session changed")
            if ticket.destination != str(call.get("destination") or "")[:1000]:
                raise PermissionError("generated action approval destination changed")
            if ticket.data_classification != "internal":
                raise PermissionError("generated action approval data classification changed")
        return super().commit(proposal_id, **kwargs)
