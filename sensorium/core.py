from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ProviderMode(str, Enum):
    REAL = "real"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ProviderState(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass(frozen=True)
class Observation:
    provider: str
    kind: str
    mode: ProviderMode
    payload: Mapping[str, Any]
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    simulated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "mode": self.mode.value,
            "payload": dict(self.payload),
            "observed_at": self.observed_at,
            "simulated": self.simulated,
        }


class SensorProvider(ABC):
    name: str
    kind: str

    @property
    @abstractmethod
    def mode(self) -> ProviderMode:
        raise NotImplementedError

    @property
    def state(self) -> ProviderState:
        if self.mode == ProviderMode.DISABLED:
            return ProviderState.DISABLED
        if self.mode == ProviderMode.UNAVAILABLE:
            return ProviderState.UNAVAILABLE
        return ProviderState.READY

    @abstractmethod
    def observe(self) -> Observation:
        raise NotImplementedError


class StaticSensorProvider(SensorProvider):
    """Deterministic provider for fixtures, simulators and repeatable tests."""

    def __init__(self, name: str, kind: str, payload: Mapping[str, Any] | None = None, *, mode: ProviderMode = ProviderMode.SIMULATED):
        self.name = str(name).strip()
        self.kind = str(kind).strip()
        self._payload = dict(payload or {})
        self._mode = ProviderMode(mode)
        if not self.name or not self.kind:
            raise ValueError("sensor provider name and kind are required")

    @property
    def mode(self) -> ProviderMode:
        return self._mode

    def set_payload(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)

    def set_mode(self, mode: ProviderMode) -> None:
        self._mode = ProviderMode(mode)

    def observe(self) -> Observation:
        if self.state != ProviderState.READY:
            raise RuntimeError(f"sensor provider is {self.state.value}")
        return Observation(
            provider=self.name,
            kind=self.kind,
            mode=self.mode,
            payload=dict(self._payload),
            simulated=self.mode == ProviderMode.SIMULATED,
        )


class Sensorium:
    """Small aggregation boundary; providers remain explicit and permissionable."""

    ALLOWED_KINDS = {
        "screen",
        "camera",
        "microphone",
        "clipboard",
        "window",
        "system_telemetry",
        "location",
        "device",
    }

    def __init__(self, events: Any | None = None):
        self.events = events
        self._providers: dict[str, SensorProvider] = {}

    def register(self, provider: SensorProvider) -> None:
        if provider.kind not in self.ALLOWED_KINDS:
            raise ValueError("unsupported sensor provider kind")
        if provider.name in self._providers:
            raise ValueError("duplicate sensor provider")
        self._providers[provider.name] = provider
        self._emit("sensorium.provider.registered", provider=provider.name, kind=provider.kind, mode=provider.mode.value)

    def provider(self, name: str) -> SensorProvider:
        try:
            return self._providers[str(name)]
        except KeyError as exc:
            raise KeyError("sensor provider not found") from exc

    def status(self) -> list[dict[str, str]]:
        return [
            {
                "name": provider.name,
                "kind": provider.kind,
                "mode": provider.mode.value,
                "state": provider.state.value,
            }
            for provider in sorted(self._providers.values(), key=lambda item: item.name)
        ]

    def observe(self, name: str) -> dict[str, Any]:
        provider = self.provider(name)
        self._emit("sensorium.observation.started", provider=provider.name, kind=provider.kind)
        try:
            observation = provider.observe()
        except Exception as exc:
            self._emit("sensorium.observation.failed", provider=provider.name, kind=provider.kind, error=type(exc).__name__)
            raise
        self._emit("sensorium.observation.completed", provider=provider.name, kind=provider.kind, simulated=observation.simulated)
        return observation.as_dict()

    def observe_kind(self, kind: str) -> list[dict[str, Any]]:
        kind = str(kind).strip()
        if kind not in self.ALLOWED_KINDS:
            raise ValueError("unsupported sensor provider kind")
        return [self.observe(provider.name) for provider in self._providers.values() if provider.kind == kind and provider.state == ProviderState.READY]

    def _emit(self, name: str, **payload: Any) -> None:
        if self.events is None:
            return
        emit = getattr(self.events, "emit", None)
        if callable(emit):
            emit(name, **payload)
