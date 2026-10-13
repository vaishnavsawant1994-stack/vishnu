from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
import uuid

from devices.runtime import DeviceCommand, RuntimeResult
from devices.simulator import SimulatedDeviceRuntime, VirtualDeviceProfile


MAX_VIRTUAL_DEVICES = 64
SUPPORTED_PLATFORMS = {"android-emulator", "ios-simulator", "desktop", "web", "iot-mock"}


@dataclass(frozen=True)
class VirtualDeviceDescriptor:
    device_id: str
    name: str
    platform: str


class VirtualDeviceLab:
    """Owns deterministic virtual runtimes without impersonating physical devices."""

    def __init__(self, events: Any | None = None):
        self.events = events
        self._runtimes: dict[str, SimulatedDeviceRuntime] = {}

    def create_device(
        self,
        name: str,
        platform: str,
        *,
        device_id: str | None = None,
        capabilities: Iterable[str] | None = None,
        installed_apps: Iterable[str] | None = None,
    ) -> VirtualDeviceDescriptor:
        if len(self._runtimes) >= MAX_VIRTUAL_DEVICES:
            raise RuntimeError("virtual device lab capacity reached")
        platform = str(platform).strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError("unsupported virtual device platform")
        name = str(name).strip()
        if not name or len(name) > 160:
            raise ValueError("virtual device name must be 1-160 characters")
        device_id = str(device_id or f"virtual-{uuid.uuid4()}").strip()
        if not device_id or len(device_id) > 160 or device_id in self._runtimes:
            raise ValueError("virtual device id is invalid or already exists")

        kwargs: dict[str, Any] = {}
        if capabilities is not None:
            kwargs["capabilities"] = tuple(capabilities)
        if installed_apps is not None:
            kwargs["installed_apps"] = {str(item).strip() for item in installed_apps if str(item).strip()}
        profile = VirtualDeviceProfile(device_id=device_id, name=name, platform=platform, **kwargs)
        self._runtimes[device_id] = SimulatedDeviceRuntime(profile)
        self._emit("virtual_device.created", device_id=device_id, platform=platform)
        return VirtualDeviceDescriptor(device_id=device_id, name=name, platform=platform)

    def remove_device(self, device_id: str) -> bool:
        runtime = self._runtimes.pop(str(device_id), None)
        if runtime is None:
            return False
        self._emit("virtual_device.removed", device_id=runtime.profile.device_id)
        return True

    def runtime(self, device_id: str) -> SimulatedDeviceRuntime:
        try:
            return self._runtimes[str(device_id)]
        except KeyError as exc:
            raise KeyError("virtual device not found") from exc

    def list_devices(self) -> list[dict[str, Any]]:
        return [self._runtimes[key].status().as_dict() for key in sorted(self._runtimes)]

    def status(self, device_id: str) -> dict[str, Any]:
        return self.runtime(device_id).status().as_dict()

    def execute(self, device_id: str, action: str, parameters: Mapping[str, Any] | None = None, *, request_id: str | None = None) -> dict[str, Any]:
        command_kwargs: dict[str, Any] = {
            "action": action,
            "parameters": dict(parameters or {}),
        }
        if request_id is not None:
            command_kwargs["request_id"] = request_id
        command = DeviceCommand(**command_kwargs)
        result = self.runtime(device_id).execute(command)
        self._emit(
            "virtual_device.command",
            device_id=device_id,
            request_id=result.request_id,
            action=action,
            success=result.success,
            code=result.code,
        )
        return result.as_dict()

    def cancel(self, device_id: str, request_id: str) -> bool:
        cancelled = self.runtime(device_id).cancel(request_id)
        if cancelled:
            self._emit("virtual_device.command.cancelled", device_id=device_id, request_id=request_id)
        return cancelled

    def verify(self, device_id: str, request_id: str) -> RuntimeResult | None:
        return self.runtime(device_id).verify(request_id)

    def set_scenario(self, device_id: str, **scenario: Any) -> dict[str, Any]:
        status = self.runtime(device_id).set_scenario(**scenario)
        self._emit("virtual_device.scenario.changed", device_id=device_id, state=status.state.value)
        return status.as_dict()

    def inject_failure(self, device_id: str, reason: str | None) -> None:
        self.runtime(device_id).inject_failure(reason)
        self._emit("virtual_device.failure.armed", device_id=device_id, reason=reason or "none")

    def _emit(self, name: str, **payload: Any) -> None:
        if self.events is None:
            return
        emit = getattr(self.events, "emit", None)
        if callable(emit):
            emit(name, **payload)
