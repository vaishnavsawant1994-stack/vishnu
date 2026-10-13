from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from devices.runtime import (
    DeviceCommand,
    DeviceRuntime,
    DeviceStatus,
    QualificationLevel,
    RuntimeMode,
    RuntimeResult,
    RuntimeState,
)


_DEFAULT_CAPABILITIES = (
    "app.open",
    "device.status",
    "location.read",
    "notification.emit",
    "telemetry.read",
)


@dataclass
class VirtualDeviceProfile:
    device_id: str
    name: str
    platform: str
    capabilities: tuple[str, ...] = _DEFAULT_CAPABILITIES
    battery_percent: int = 100
    network: str = "wifi"
    locked: bool = False
    online: bool = True
    location: dict[str, Any] | None = None
    installed_apps: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=lambda: set(_DEFAULT_CAPABILITIES))

    def __post_init__(self) -> None:
        self.device_id = str(self.device_id).strip()
        self.name = str(self.name).strip()
        self.platform = str(self.platform).strip().lower()
        self.capabilities = tuple(sorted({str(item).strip() for item in self.capabilities if str(item).strip()}))
        self.battery_percent = max(0, min(100, int(self.battery_percent)))
        if not self.device_id or not self.name or not self.platform:
            raise ValueError("virtual device id, name and platform are required")


class SimulatedDeviceRuntime(DeviceRuntime):
    """Deterministic, no-I/O device runtime for development and qualification.

    It never reaches physical hardware, the network, the host shell, or package
    managers. State changes are in-memory and therefore bounded and reversible.
    """

    def __init__(self, profile: VirtualDeviceProfile):
        self.profile = profile
        self._results: dict[str, RuntimeResult] = {}
        self._cancelled: set[str] = set()
        self._notifications: list[dict[str, Any]] = []
        self._active_app: str | None = None
        self._fail_next: str | None = None

    def capabilities(self) -> tuple[str, ...]:
        return self.profile.capabilities

    def status(self) -> DeviceStatus:
        state = RuntimeState.OFFLINE if not self.profile.online else RuntimeState.LOCKED if self.profile.locked else RuntimeState.READY
        return DeviceStatus(
            device_id=self.profile.device_id,
            name=self.profile.name,
            platform=self.profile.platform,
            mode=RuntimeMode.SIMULATED,
            state=state,
            qualification=QualificationLevel.SIMULATED,
            capabilities=self.capabilities(),
            metadata={
                "battery_percent": self.profile.battery_percent,
                "network": self.profile.network,
                "active_app": self._active_app,
                "notification_count": len(self._notifications),
            },
        )

    def inject_failure(self, reason: str | None) -> None:
        allowed = {None, "disconnect", "permission_revoked", "timeout", "runtime_error"}
        if reason not in allowed:
            raise ValueError("unsupported simulated failure")
        self._fail_next = reason

    def execute(self, command: DeviceCommand) -> RuntimeResult:
        if command.request_id in self._cancelled:
            return self._remember(command, False, "cancelled", {})
        if command.action not in self.profile.capabilities:
            return self._remember(command, False, "capability_not_supported", {})
        if command.action not in self.profile.permissions:
            return self._remember(command, False, "permission_denied", {})
        if not self.profile.online:
            return self._remember(command, False, "device_offline", {})

        failure = self._fail_next
        self._fail_next = None
        if failure == "disconnect":
            self.profile.online = False
            return self._remember(command, False, "device_disconnected", {})
        if failure == "permission_revoked":
            self.profile.permissions.discard(command.action)
            return self._remember(command, False, "permission_revoked", {})
        if failure == "timeout":
            return self._remember(command, False, "simulated_timeout", {})
        if failure == "runtime_error":
            return self._remember(command, False, "simulated_runtime_error", {})

        if self.profile.locked and command.action not in {"device.status", "telemetry.read"}:
            return self._remember(command, False, "device_locked", {})

        handler = {
            "app.open": self._open_app,
            "device.status": self._read_status,
            "location.read": self._read_location,
            "notification.emit": self._emit_notification,
            "telemetry.read": self._read_telemetry,
        }.get(command.action)
        if handler is None:
            return self._remember(command, False, "capability_not_implemented", {})
        return self._remember(command, True, "ok", handler(dict(command.parameters)))

    def cancel(self, request_id: str) -> bool:
        request_id = str(request_id).strip()
        if not request_id:
            return False
        self._cancelled.add(request_id)
        return True

    def verify(self, request_id: str) -> RuntimeResult | None:
        result = self._results.get(str(request_id))
        if result is None:
            return None
        return RuntimeResult(
            request_id=result.request_id,
            device_id=result.device_id,
            action=result.action,
            success=result.success,
            code=result.code,
            output=deepcopy(dict(result.output)),
            simulated=True,
            verified=True,
        )

    def set_scenario(
        self,
        *,
        battery_percent: int | None = None,
        network: str | None = None,
        locked: bool | None = None,
        online: bool | None = None,
        permissions: Iterable[str] | None = None,
        location: Mapping[str, Any] | None = None,
    ) -> DeviceStatus:
        if battery_percent is not None:
            self.profile.battery_percent = max(0, min(100, int(battery_percent)))
        if network is not None:
            self.profile.network = str(network).strip().lower()[:32] or "offline"
        if locked is not None:
            self.profile.locked = bool(locked)
        if online is not None:
            self.profile.online = bool(online)
        if permissions is not None:
            requested = {str(item).strip() for item in permissions if str(item).strip()}
            if not requested.issubset(set(self.profile.capabilities)):
                raise ValueError("simulated permissions must be declared capabilities")
            self.profile.permissions = requested
        if location is not None:
            self.profile.location = dict(location)
        return self.status()

    def _remember(self, command: DeviceCommand, success: bool, code: str, output: Mapping[str, Any]) -> RuntimeResult:
        result = RuntimeResult(
            request_id=command.request_id,
            device_id=self.profile.device_id,
            action=command.action,
            success=success,
            code=code,
            output=dict(output),
            simulated=True,
            verified=False,
        )
        self._results[command.request_id] = result
        return result

    def _open_app(self, parameters: dict[str, Any]) -> dict[str, Any]:
        app = str(parameters.get("app", "")).strip()
        if not app or len(app) > 128:
            raise ValueError("app.open requires app")
        if self.profile.installed_apps and app not in self.profile.installed_apps:
            return {"opened": False, "app": app, "reason": "not_installed"}
        self._active_app = app
        return {"opened": True, "app": app}

    def _read_status(self, _parameters: dict[str, Any]) -> dict[str, Any]:
        return self.status().as_dict()

    def _read_location(self, _parameters: dict[str, Any]) -> dict[str, Any]:
        return {"location": deepcopy(self.profile.location), "available": self.profile.location is not None}

    def _emit_notification(self, parameters: dict[str, Any]) -> dict[str, Any]:
        title = str(parameters.get("title", "")).strip()[:160]
        body = str(parameters.get("body", "")).strip()[:2000]
        if not title:
            raise ValueError("notification.emit requires title")
        item = {"title": title, "body": body}
        self._notifications.append(item)
        return {"delivered": True, "notification": item}

    def _read_telemetry(self, _parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "battery_percent": self.profile.battery_percent,
            "network": self.profile.network,
            "locked": self.profile.locked,
            "online": self.profile.online,
        }
