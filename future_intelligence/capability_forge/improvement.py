from __future__ import annotations

from typing import Any


class CapabilityImprovementService:
    """Convert degraded generated-capability evidence into governed proposals.

    The service can observe health events and create a deduplicated Forge gap/spec/
    plan automatically, but it has no build, approval, activation, disable,
    rollback, merge or deploy authority.
    """

    def __init__(self, forge, evaluator, catalog, *, events=None) -> None:
        self.forge = forge
        self.evaluator = evaluator
        self.catalog = catalog
        self.events = events
        self._evaluating = False
        self._unsubscribe = None
        if events is not None and hasattr(events, "subscribe"):
            self._unsubscribe = events.subscribe("capability_forge.health_evaluated", self._on_health_event)

    def detach(self) -> None:
        if callable(self._unsubscribe):
            self._unsubscribe()
        self._unsubscribe = None

    def _on_health_event(self, event: dict[str, Any]) -> None:
        if self._evaluating:
            return
        if not (event.get("rollback_recommended") or str(event.get("state") or "") == "degraded"):
            return
        capability_id = str(event.get("capability_id") or "")
        if not capability_id:
            return
        try:
            self.propose(capability_id)
        except (KeyError, ValueError, PermissionError, RuntimeError):
            return

    def propose(self, capability_id: str, *, force: bool = False) -> dict[str, Any] | None:
        capability = self.catalog.get(str(capability_id))
        if not capability or capability.get("type") != "generated_capability":
            raise KeyError("generated capability not found")
        self._evaluating = True
        try:
            health = self.evaluator.evaluate(str(capability_id))
        finally:
            self._evaluating = False
        should_propose = bool(force or health.rollback_recommended or health.state == "degraded")
        if not should_propose:
            return None
        if not force and not health.sufficient_evidence:
            return None
        permissions = dict(capability.get("permissions") or {})
        reasons = list(health.reasons or ())[:20]
        payload = {
            "capability_gap": True,
            "capability_name": f"Improve {capability.get('name') or capability_id}",
            "requested_outcome": (
                f"Create a safer and more reliable next version of {capability_id}. "
                f"Current active version is {capability.get('version') or health.active_version}. "
                + ("Observed health reasons: " + "; ".join(reasons) if reasons else "Re-qualify the current capability behavior.")
            ),
            "required_operations": ["improve_generated_capability"],
            "network_hosts": list(permissions.get("network_hosts") or []),
            "filesystem_read": list(permissions.get("filesystem_read") or []),
            "filesystem_write": list(permissions.get("filesystem_write") or []),
            "secret_names": [],
            "connector_ids": list(permissions.get("connector_ids") or []),
            "side_effects": list(permissions.get("side_effects") or []),
            "ui_required": bool(permissions.get("ui_required")),
            "background_allowed": bool(permissions.get("background_allowed")),
            "preferred_route": "generated",
            "improvement_of": str(capability_id),
            "current_version": str(capability.get("version") or health.active_version or ""),
            "health_state": health.state,
            "health_reasons": reasons,
        }
        requirements = {
            "name": payload["capability_name"],
            "purpose": payload["requested_outcome"],
            "required_operations": payload["required_operations"],
            "network_hosts": payload["network_hosts"],
            "filesystem_read": payload["filesystem_read"],
            "filesystem_write": payload["filesystem_write"],
            "connector_ids": payload["connector_ids"],
            "side_effects": payload["side_effects"],
            "ui_required": payload["ui_required"],
            "background_allowed": payload["background_allowed"],
            "metadata": {
                "preferred_route": "generated",
                "improvement_of": str(capability_id),
                "previous_version": payload["current_version"],
                "health_state": health.state,
                "health_reasons": reasons,
                "allowed_tools": list(permissions.get("allowed_tools") or []),
                "runtime": str(capability.get("runtime") or ""),
                "ui": capability.get("ui"),
            },
        }
        result = self.forge.propose("system", payload, requirements=requirements)
        if result is None:
            return None
        gap, spec, plan = result
        if self.events is not None:
            self.events.emit(
                "capability_forge.improvement_proposed",
                capability_id=str(capability_id), gap_id=gap.id, spec_id=spec.id, plan_id=plan.id,
                health_state=health.state, activation=False,
            )
        return {
            "health": health.to_dict(),
            "gap": gap.to_dict(),
            "spec": spec.to_dict(),
            "plan": plan.to_dict(),
            "activation": False,
        }
