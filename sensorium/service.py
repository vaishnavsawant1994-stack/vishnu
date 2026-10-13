from __future__ import annotations

from typing import Any

from sensorium.adapters import (
    VirtualAdapterBinding,
    VirtualClipboardAdapter,
    VirtualScreenAdapter,
    VirtualSystemAdapter,
)
from sensorium.virtual_device_lab import VirtualDeviceLab


class SensoriumService:
    """Read-model and planning bridge over Sensorium.

    This service intentionally does not dispatch physical input. Its planner
    observation is untrusted context for the existing governed ComputerIntelligence
    planner; it is not sufficient to satisfy that runtime's execution approvals or
    observation-binding checks.
    """

    def __init__(
        self,
        lab: VirtualDeviceLab,
        *,
        virtual_device_id: str,
        controller_device_id: str | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self.lab = lab
        self.virtual_device_id = str(virtual_device_id)
        self.controller_device_id = controller_device_id
        self.event_bus = event_bus
        binding = VirtualAdapterBinding(
            lab=lab,
            virtual_device_id=self.virtual_device_id,
            controller_device_id=controller_device_id,
        )
        self.screen = VirtualScreenAdapter(binding)
        self.clipboard = VirtualClipboardAdapter(binding)
        self.system = VirtualSystemAdapter(binding)

    def _emit(self, event: str, **payload: Any) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(event, **payload)

    def context_snapshot(self, *, include_clipboard_content: bool = False) -> dict[str, Any]:
        device = self.lab.get_device(
            self.virtual_device_id,
            controller_device_id=self.controller_device_id,
        )
        screen = self.screen.latest()
        clipboard = self.clipboard.latest(include_text=include_clipboard_content)
        system = self.system.latest()
        snapshot = {
            "virtual_device": device,
            "screen": screen,
            "clipboard": clipboard,
            "system": system,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        self._emit(
            "sensorium.context.observed",
            virtual_device_id=self.virtual_device_id,
            controller_device_id=self.controller_device_id,
            screen_event_id=(screen or {}).get("event_id"),
            clipboard_event_id=(clipboard or {}).get("event_id"),
            system_event_id=(system or {}).get("event_id"),
            clipboard_content_included=bool(include_clipboard_content),
            instruction_trust="untrusted",
        )
        return snapshot

    def planner_observation(self) -> dict[str, Any]:
        screen = self.screen.latest(required=True)
        system = self.system.latest()
        clipboard = self.clipboard.latest(include_text=False)
        analysis = str(screen.get("analysis") or "").strip()
        if not analysis:
            analysis = "Virtual Sensorium screen observation is available without semantic analysis."
        return {
            "analysis": analysis,
            "sensorium_context": {
                "virtual_device_id": self.virtual_device_id,
                "screen": screen,
                "system": system,
                "clipboard": clipboard,
                "instruction_trust": "untrusted",
                "execution_authority": False,
            },
            "sensorium_virtual": True,
            "screenshot_evidence_ref": None,
            "screen_fingerprint": screen.get("screen_fingerprint"),
        }
