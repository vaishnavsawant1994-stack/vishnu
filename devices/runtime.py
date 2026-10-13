from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Mapping
import uuid


class RuntimeMode(str, Enum):
    REAL = "real"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class RuntimeState(str, Enum):
    READY = "ready"
    OFFLINE = "offline"
    LOCKED = "locked"
    BUSY = "busy"
    CANCELLED = "cancelled"
    ERROR = "error"


class QualificationLevel(IntEnum):
    DESIGNED = 0
    UNIT_TESTED = 1
    SIMULATED = 2
    EMULATOR_TESTED = 3
    REAL_DEVICE_TESTED = 4
    PRODUCTION_QUALIFIED = 5

    @property
    def label(self) -> str:
        return {
            0: "designed",
            1: "unit-tested",
            2: "simulated",
            3: "emulator/simulator-tested",
            4: "real-device-tested",
            5: "production-qualified",
        }[int(self)]


@dataclass(frozen=True)
class DeviceCommand:
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        action = str(self.action).strip()
        if not action or len(action) > 128:
            raise ValueError("device action must be 1-128 characters")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("device command parameters must be an object")
        if len(self.parameters) > 64:
            raise ValueError("device command has too many parameters")
        request_id = str(self.request_id).strip()
        if not request_id or len(request_id) > 128:
            raise ValueError("device request_id must be 1-128 characters")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "parameters", dict(self.parameters))


@dataclass(frozen=True)
class DeviceStatus:
    device_id: str
    name: str
    platform: str
    mode: RuntimeMode
    state: RuntimeState
    qualification: QualificationLevel
    capabilities: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "platform": self.platform,
            "mode": self.mode.value,
            "state": self.state.value,
            "qualification_level": int(self.qualification),
            "qualification": self.qualification.label,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeResult:
    request_id: str
    device_id: str
    action: str
    success: bool
    code: str
    output: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False
    verified: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "action": self.action,
            "success": self.success,
            "code": self.code,
            "output": dict(self.output),
            "simulated": self.simulated,
            "verified": self.verified,
        }


class DeviceRuntime(ABC):
    """Stable boundary used by agents regardless of physical or virtual hardware."""

    @abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> DeviceStatus:
        raise NotImplementedError

    @abstractmethod
    def execute(self, command: DeviceCommand) -> RuntimeResult:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, request_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def verify(self, request_id: str) -> RuntimeResult | None:
        raise NotImplementedError
