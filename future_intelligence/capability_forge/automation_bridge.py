from __future__ import annotations

import json
from typing import Any


class CapabilityForgeAutomationBridge:
    """Project owner-approved generated capabilities onto the canonical AutomationEngine.

    This adapter does not execute capabilities or approve side effects. Scheduled
    work enters Vishnu through the existing automation/agent path, so a generated
    action can at most stage its exact side-effect proposal and surface canonical
    approval tickets for the owner.
    """

    def __init__(self, automations, catalog, *, events=None) -> None:
        self.automations = automations
        self.catalog = catalog
        self.events = events

    def _capability(self, capability_id: str) -> dict[str, Any]:
        item = self.catalog.get(str(capability_id))
        if not item or item.get("type") != "generated_capability" or item.get("state") != "active":
            raise KeyError("active generated capability not found")
        permissions = dict(item.get("permissions") or {})
        if not permissions.get("background_allowed"):
            raise PermissionError("this generated capability was not qualified for background scheduling")
        return item

    @staticmethod
    def _prompt(capability_id: str, parameters: dict[str, Any]) -> str:
        payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(payload.encode("utf-8")) > 128_000:
            raise ValueError("generated capability scheduled parameters exceed size limit")
        return (
            "Run the active generated capability " + str(capability_id) + " with exactly this JSON input: " + payload + ". "
            "Use only the registered capability tool. Do not substitute another tool or broaden its scope. "
            "If the capability stages side effects, stop at its canonical approval boundary; never approve or commit them automatically."
        )

    def schedule(
        self,
        capability_id: str,
        parameters: dict[str, Any],
        *,
        next_run_at: str,
        interval_seconds: int | None = None,
        condition: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(parameters, dict):
            raise ValueError("scheduled generated capability parameters must be an object")
        capability = self._capability(capability_id)
        if interval_seconds is not None:
            interval_seconds = int(interval_seconds)
            if interval_seconds < 3600:
                raise ValueError("generated capability recurring schedules are limited to once per hour or slower")
        automation_id = self.automations.create(
            str(title or f"Generated capability · {capability.get('name') or capability_id}")[:200],
            self._prompt(capability_id, parameters),
            str(next_run_at),
            interval_seconds=interval_seconds,
            condition=dict(condition or {}),
        )
        if self.events is not None:
            self.events.emit(
                "capability_forge.schedule_created",
                capability_id=str(capability_id),
                automation_id=str(automation_id),
                recurring=interval_seconds is not None,
            )
        return {
            "automation_id": str(automation_id),
            "capability_id": str(capability_id),
            "next_run_at": str(next_run_at),
            "interval_seconds": interval_seconds,
            "enabled": True,
            "side_effect_auto_approval": False,
        }

    def enable(self, automation_id: str, enabled: bool) -> dict[str, Any]:
        self.automations.enable(str(automation_id), bool(enabled))
        if self.events is not None:
            self.events.emit("capability_forge.schedule_enabled", automation_id=str(automation_id), enabled=bool(enabled))
        return {"automation_id": str(automation_id), "enabled": bool(enabled)}
