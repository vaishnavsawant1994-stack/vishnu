from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
MAX_EVENT_METADATA_BYTES = 16 * 1024
MAX_DEVICE_CAPABILITIES = 64


class SensorKind(StrEnum):
    SCREEN = "screen"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    CLIPBOARD = "clipboard"
    WINDOW = "window"
    INPUT = "input"
    SYSTEM = "system"
    LOCATION = "location"
    NETWORK = "network"
    CUSTOM = "custom"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class DeviceState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    PAUSED = "paused"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_identifier(value: str, field_name: str) -> str:
    clean = str(value).strip()
    if not _IDENTIFIER.fullmatch(clean):
        raise ValueError(f"{field_name} must be a bounded identifier")
    return clean


def _json_size(value: Any, *, field_name: str, limit: int) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON serializable") from exc
    if len(encoded) > limit:
        raise ValueError(f"{field_name} exceeds {limit} bytes")


def _normalize_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class SensorEvent:
    event_id: str
    device_id: str
    kind: SensorKind
    timestamp: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    data_classification: DataClassification = DataClassification.INTERNAL
    source: str = "virtual-device-lab"
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _validate_identifier(self.event_id, "event_id"))
        object.__setattr__(self, "device_id", _validate_identifier(self.device_id, "device_id"))
        object.__setattr__(self, "source", _validate_identifier(self.source, "source"))
        if self.correlation_id is not None:
            object.__setattr__(self, "correlation_id", _validate_identifier(self.correlation_id, "correlation_id"))
        if not isinstance(self.kind, SensorKind):
            object.__setattr__(self, "kind", SensorKind(str(self.kind)))
        if not isinstance(self.data_classification, DataClassification):
            object.__setattr__(self, "data_classification", DataClassification(str(self.data_classification)))
        object.__setattr__(self, "timestamp", _normalize_timestamp(self.timestamp))
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be an object")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be an object")
        _json_size(self.payload, field_name="payload", limit=MAX_EVENT_PAYLOAD_BYTES)
        _json_size(self.metadata, field_name="metadata", limit=MAX_EVENT_METADATA_BYTES)

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        kind: SensorKind | str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        data_classification: DataClassification | str = DataClassification.INTERNAL,
        source: str = "virtual-device-lab",
        correlation_id: str | None = None,
        timestamp: datetime | None = None,
        event_id: str | None = None,
    ) -> "SensorEvent":
        return cls(
            event_id=event_id or f"sensor-{uuid.uuid4()}",
            device_id=device_id,
            kind=SensorKind(kind),
            timestamp=timestamp or _utc_now(),
            payload=dict(payload),
            metadata=dict(metadata or {}),
            data_classification=DataClassification(data_classification),
            source=source,
            correlation_id=correlation_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "kind": self.kind.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "data_classification": self.data_classification.value,
            "source": self.source,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SensorEvent":
        if not isinstance(value, dict):
            raise ValueError("sensor event must be an object")
        try:
            timestamp = datetime.fromisoformat(str(value["timestamp"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("sensor event timestamp is invalid") from exc
        return cls(
            event_id=value["event_id"],
            device_id=value["device_id"],
            kind=SensorKind(value["kind"]),
            timestamp=timestamp,
            payload=dict(value["payload"]),
            metadata=dict(value.get("metadata") or {}),
            data_classification=DataClassification(value.get("data_classification", "internal")),
            source=value.get("source", "virtual-device-lab"),
            correlation_id=value.get("correlation_id"),
        )


@dataclass(frozen=True, slots=True)
class VirtualDevice:
    device_id: str
    name: str
    platform: str
    capabilities: frozenset[SensorKind]
    state: DeviceState = DeviceState.ONLINE
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_id", _validate_identifier(self.device_id, "device_id"))
        name = str(self.name).strip()
        platform = str(self.platform).strip()
        if not name or len(name) > 120:
            raise ValueError("name must contain 1-120 characters")
        if not platform or len(platform) > 80:
            raise ValueError("platform must contain 1-80 characters")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "platform", platform)
        capabilities = frozenset(SensorKind(item) for item in self.capabilities)
        if not capabilities:
            raise ValueError("virtual device requires at least one sensor capability")
        if len(capabilities) > MAX_DEVICE_CAPABILITIES:
            raise ValueError("too many virtual device capabilities")
        object.__setattr__(self, "capabilities", capabilities)
        if not isinstance(self.state, DeviceState):
            object.__setattr__(self, "state", DeviceState(str(self.state)))
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be an object")
        _json_size(self.metadata, field_name="metadata", limit=MAX_EVENT_METADATA_BYTES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "platform": self.platform,
            "capabilities": sorted(item.value for item in self.capabilities),
            "state": self.state.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class VirtualScenario:
    scenario_id: str
    device_id: str
    events: tuple[SensorEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _validate_identifier(self.scenario_id, "scenario_id"))
        object.__setattr__(self, "device_id", _validate_identifier(self.device_id, "device_id"))
        if not self.events:
            raise ValueError("scenario requires at least one event")
        if any(event.device_id != self.device_id for event in self.events):
            raise ValueError("all scenario events must belong to the scenario device")
