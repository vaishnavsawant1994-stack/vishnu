from __future__ import annotations

import uuid
from typing import Any

from desktop.application_context import ApplicationContextObserver
from desktop.input_clipboard import ClipboardSnapshot, default_clipboard_adapter
from devices.gateway import DeviceCommand


class DesktopPhysicalSensorAdapter:
    """On-demand physical desktop observations with no input authority.

    Sensorium may observe the host through existing safe primitives, but this
    adapter deliberately exposes no click, keyboard, window-control, or other
    side-effecting method. Screen analysis reuses the existing governed
    ComputerIntelligence observation path and is treated as sensitive context.
    """

    def __init__(
        self,
        registry,
        *,
        computer=None,
        clipboard_adapter=None,
        application_observer=None,
        event_bus=None,
    ) -> None:
        if registry is None:
            raise ValueError("device registry is required")
        self.registry = registry
        self.computer = computer
        self.clipboard = clipboard_adapter or default_clipboard_adapter()
        self.application_observer = application_observer or ApplicationContextObserver()
        self.event_bus = event_bus

    def _require(self, controller_device_id: str, scope: str) -> str:
        device_id = str(controller_device_id or "").strip()
        if not device_id or not self.registry.authorize(device_id, scope):
            raise PermissionError(f"device is not permitted to use {scope}")
        return device_id

    def _emit(self, *, controller_device_id: str, sensor: str, sensitive: bool = False) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(
                "sensorium.physical.observed",
                controller_device_id=controller_device_id,
                platform="desktop",
                sensor=sensor,
                sensitive=bool(sensitive),
                execution_authority=False,
            )

    def observe_system(self, controller_device_id: str) -> dict[str, Any]:
        device_id = self._require(controller_device_id, "device:read")
        application = dict(self.application_observer.capture() or {})
        # ApplicationContext.safe_dict already removes the raw window title.
        application.pop("window_title", None)
        result = {
            "physical": True,
            "platform": "desktop",
            "system": {"application": application},
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        self._emit(controller_device_id=device_id, sensor="system")
        return result

    def observe_clipboard(
        self,
        controller_device_id: str,
        *,
        include_content: bool = False,
    ) -> dict[str, Any]:
        device_id = self._require(controller_device_id, "device:read")
        if include_content:
            self._require(device_id, "memory:sensitive")
        text, sequence = self.clipboard.read_text()
        snapshot = ClipboardSnapshot.from_value(str(text), int(sequence)).safe_dict()
        result: dict[str, Any] = {
            "physical": True,
            "platform": "desktop",
            "clipboard": snapshot,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        if include_content:
            result["clipboard"] = {**snapshot, "text": str(text)[:65_536]}
        self._emit(controller_device_id=device_id, sensor="clipboard", sensitive=include_content)
        return result

    def observe_screen(
        self,
        controller_device_id: str,
        *,
        question: str = "Describe the visible screen and relevant UI state without acting.",
        monitor: int = 1,
    ) -> dict[str, Any]:
        device_id = self._require(controller_device_id, "device:read")
        self._require(device_id, "memory:sensitive")
        if self.computer is None or not hasattr(self.computer, "observe"):
            raise RuntimeError("physical desktop screen observation is unavailable")
        prompt = str(question or "").strip()
        if not prompt or len(prompt) > 2_000:
            raise ValueError("screen observation question must contain 1-2000 characters")
        monitor_id = int(monitor)
        if monitor_id < 1 or monitor_id > 32:
            raise ValueError("monitor is outside the allowed range")
        observed = dict(self.computer.observe(prompt, monitor=monitor_id) or {})
        analysis = str(observed.get("analysis") or "")[:20_000]
        result = {
            "physical": True,
            "platform": "desktop",
            "screen": {
                "analysis": analysis,
                "screen_fingerprint": observed.get("screen_fingerprint"),
                "evidence_available": bool(observed.get("screenshot_evidence_ref")),
            },
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        self._emit(controller_device_id=device_id, sensor="screen", sensitive=True)
        return result

    def context_snapshot(
        self,
        controller_device_id: str,
        *,
        include_clipboard_content: bool = False,
        include_screen_analysis: bool = False,
        monitor: int = 1,
    ) -> dict[str, Any]:
        device_id = self._require(controller_device_id, "device:read")
        system = self.observe_system(device_id)["system"]
        try:
            clipboard = self.observe_clipboard(
                device_id,
                include_content=include_clipboard_content,
            )["clipboard"]
        except RuntimeError as exc:
            clipboard = {"available": False, "reason": str(exc)[:120]}
        screen = None
        if include_screen_analysis:
            screen = self.observe_screen(device_id, monitor=monitor)["screen"]
        return {
            "physical": True,
            "platform": "desktop",
            "system": system,
            "clipboard": clipboard,
            "screen": screen,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }


class MobilePhysicalSensorAdapter:
    """Read-only mobile observation bridge over the existing DeviceGateway."""

    ALLOWED_ACTIONS = frozenset({"device_info", "battery"})

    def __init__(self, registry, gateway, *, event_bus=None) -> None:
        if registry is None or gateway is None:
            raise ValueError("device registry and gateway are required")
        self.registry = registry
        self.gateway = gateway
        self.event_bus = event_bus

    def _require_access(self, controller_device_id: str, target_device_id: str) -> tuple[str, str]:
        controller = str(controller_device_id or "").strip()
        target = str(target_device_id or "").strip()
        if not controller or not self.registry.authorize(controller, "device:read"):
            raise PermissionError("controller device is not permitted to read device context")
        if not target or not self.registry.is_active(target):
            raise PermissionError("target device is not active")
        if not self.registry.authorize(target, "device:read"):
            raise PermissionError("target device does not permit device context reads")
        if target != controller and not self.registry.authorize(controller, "device:admin"):
            raise PermissionError("cross-device Sensorium reads require device:admin")
        return controller, target

    @staticmethod
    def _bounded_device_info(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise RuntimeError("mobile device_info returned an invalid result")
        allowed = {"manufacturer", "model", "sdk", "name", "system", "version"}
        result: dict[str, Any] = {}
        for key in allowed:
            if key not in value:
                continue
            item = value[key]
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                result[key] = item
            elif isinstance(item, str):
                result[key] = item[:200]
        return result

    @staticmethod
    def _bounded_battery(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise RuntimeError("mobile battery returned an invalid result")
        result: dict[str, Any] = {}
        if "percent" in value:
            percent = int(value["percent"])
            if percent < -1 or percent > 100:
                raise RuntimeError("mobile battery percent is outside the allowed range")
            result["percent"] = percent
        if "state" in value:
            state = value["state"]
            if isinstance(state, int):
                result["state"] = state
            elif isinstance(state, str):
                result["state"] = state[:80]
        return result

    async def _request(self, target_device_id: str, action: str, timeout: float) -> dict[str, Any]:
        if action not in self.ALLOWED_ACTIONS:
            raise PermissionError("Sensorium mobile adapter only permits read-only observations")
        bounded_timeout = max(1.0, min(float(timeout), 30.0))
        command = DeviceCommand(action=action, parameters={}, request_id=str(uuid.uuid4()))
        response = await self.gateway.request(target_device_id, command, timeout=bounded_timeout)
        if not isinstance(response, dict) or response.get("device_id") != target_device_id:
            raise RuntimeError("mobile Sensorium response identity mismatch")
        if response.get("ok") is not True:
            raise RuntimeError("mobile Sensorium observation failed")
        result = response.get("result")
        if action == "device_info":
            return self._bounded_device_info(result)
        return self._bounded_battery(result)

    async def observe(
        self,
        controller_device_id: str,
        target_device_id: str,
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        controller, target = self._require_access(controller_device_id, target_device_id)
        device_info = await self._request(target, "device_info", timeout)
        battery = await self._request(target, "battery", timeout)
        result = {
            "physical": True,
            "platform": "mobile",
            "target_device_id": target,
            "device_info": device_info,
            "battery": battery,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        if self.event_bus is not None:
            self.event_bus.emit(
                "sensorium.physical.observed",
                controller_device_id=controller,
                target_device_id=target,
                platform="mobile",
                sensor="device_info,battery",
                sensitive=False,
                execution_authority=False,
            )
        return result
