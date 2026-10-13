from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from typing import Any

from sensorium.models import DeviceState, SensorEvent, SensorKind, VirtualDevice, VirtualScenario

Authorizer = Callable[[str, str], bool]


class VirtualDeviceLab:
    """Deterministic, side-effect-free sensor/device simulation.

    The lab is intentionally not a hardware driver. It lets Vishnu exercise the
    Sensorium pipeline without microphones, cameras, phones, or desktop control.
    Authorization fails closed unless the caller supplies an authorizer or
    explicitly constructs a trusted-local test lab.
    """

    READ_SCOPE = "device:read"
    ADMIN_SCOPE = "device:admin"
    MAX_EVENTS_PER_DEVICE = 10_000

    def __init__(
        self,
        *,
        event_bus: Any | None = None,
        authorizer: Authorizer | None = None,
        trusted_local: bool = False,
        max_events_per_device: int = MAX_EVENTS_PER_DEVICE,
    ) -> None:
        if authorizer is None and not trusted_local:
            raise ValueError("authorizer is required unless trusted_local=True")
        if max_events_per_device < 1 or max_events_per_device > self.MAX_EVENTS_PER_DEVICE:
            raise ValueError(f"max_events_per_device must be between 1 and {self.MAX_EVENTS_PER_DEVICE}")
        self._event_bus = event_bus
        self._authorizer = authorizer
        self._trusted_local = bool(trusted_local)
        self._max_events = int(max_events_per_device)
        self._devices: dict[str, VirtualDevice] = {}
        self._events: dict[str, list[SensorEvent]] = defaultdict(list)
        self._audit: list[dict[str, Any]] = []
        self._lock = RLock()

    @classmethod
    def from_device_registry(cls, registry: Any, **kwargs: Any) -> "VirtualDeviceLab":
        return cls(authorizer=lambda device_id, scope: bool(registry.authorize(device_id, scope)), **kwargs)

    def _authorize(self, controller_device_id: str | None, scope: str) -> None:
        if self._trusted_local:
            return
        if not controller_device_id or self._authorizer is None:
            raise PermissionError("controller device authorization is required")
        try:
            allowed = bool(self._authorizer(str(controller_device_id), scope))
        except Exception as exc:
            raise PermissionError("controller device authorization failed closed") from exc
        if not allowed:
            raise PermissionError(f"controller device lacks {scope}")

    def _emit(self, event: str, **payload: Any) -> None:
        audit = {"event": event, **deepcopy(payload)}
        with self._lock:
            self._audit.append(audit)
        if self._event_bus is not None:
            self._event_bus.emit(event, **deepcopy(payload))

    @staticmethod
    def _sensor_event_projection(event: SensorEvent) -> dict[str, Any]:
        """Return event metadata safe for shared audit/event projections.

        Raw screen, clipboard, microphone, camera, location and other sensor
        payloads remain in the bounded lab and are only returned by explicit
        authorized reads. Shared EventBus listeners never receive the payload.
        """

        return {
            "event_id": event.event_id,
            "device_id": event.device_id,
            "kind": event.kind.value,
            "timestamp": event.timestamp.isoformat(),
            "data_classification": event.data_classification.value,
            "source": event.source,
            "correlation_id": event.correlation_id,
            "payload_projected": False,
        }

    def register_device(self, device: VirtualDevice, *, controller_device_id: str | None = None) -> dict[str, Any]:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        with self._lock:
            if device.device_id in self._devices:
                raise ValueError("virtual device already exists")
            self._devices[device.device_id] = device
        snapshot = device.to_dict()
        self._emit(
            "sensorium.virtual_device.registered",
            controller_device_id=controller_device_id,
            virtual_device=snapshot,
        )
        return snapshot

    def remove_device(self, device_id: str, *, controller_device_id: str | None = None) -> None:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        with self._lock:
            if device_id not in self._devices:
                raise KeyError("virtual device not found")
            del self._devices[device_id]
            self._events.pop(device_id, None)
        self._emit(
            "sensorium.virtual_device.removed",
            controller_device_id=controller_device_id,
            virtual_device_id=device_id,
        )

    def set_state(
        self,
        device_id: str,
        state: DeviceState | str,
        *,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        normalized = DeviceState(state)
        with self._lock:
            current = self._devices.get(device_id)
            if current is None:
                raise KeyError("virtual device not found")
            updated = replace(current, state=normalized)
            self._devices[device_id] = updated
        snapshot = updated.to_dict()
        self._emit(
            "sensorium.virtual_device.state_changed",
            controller_device_id=controller_device_id,
            virtual_device_id=device_id,
            state=normalized.value,
        )
        return snapshot

    def get_device(self, device_id: str, *, controller_device_id: str | None = None) -> dict[str, Any]:
        self._authorize(controller_device_id, self.READ_SCOPE)
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise KeyError("virtual device not found")
            return device.to_dict()

    def list_devices(self, *, controller_device_id: str | None = None) -> list[dict[str, Any]]:
        self._authorize(controller_device_id, self.READ_SCOPE)
        with self._lock:
            return [self._devices[key].to_dict() for key in sorted(self._devices)]

    def inject_event(self, event: SensorEvent, *, controller_device_id: str | None = None) -> dict[str, Any]:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        with self._lock:
            device = self._devices.get(event.device_id)
            if device is None:
                raise KeyError("virtual device not found")
            if device.state != DeviceState.ONLINE:
                raise RuntimeError("virtual device must be online to inject sensor events")
            if event.kind not in device.capabilities:
                raise PermissionError("virtual device does not declare this sensor capability")
            events = self._events[event.device_id]
            if len(events) >= self._max_events:
                raise RuntimeError("virtual device event buffer is full")
            if any(existing.event_id == event.event_id for existing in events):
                raise ValueError("duplicate sensor event id")
            events.append(event)
        snapshot = event.to_dict()
        self._emit(
            "sensorium.sensor_event.injected",
            controller_device_id=controller_device_id,
            sensor_event=self._sensor_event_projection(event),
        )
        return snapshot

    def read_events(
        self,
        device_id: str,
        *,
        controller_device_id: str | None = None,
        after_event_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._authorize(controller_device_id, self.READ_SCOPE)
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._lock:
            if device_id not in self._devices:
                raise KeyError("virtual device not found")
            events = list(self._events.get(device_id, ()))
        start = 0
        if after_event_id is not None:
            indexes = [index for index, event in enumerate(events) if event.event_id == after_event_id]
            if not indexes:
                raise KeyError("after_event_id not found")
            start = indexes[0] + 1
        return [event.to_dict() for event in events[start : start + limit]]

    def replay_events(
        self,
        device_id: str,
        events: Iterable[SensorEvent],
        *,
        controller_device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        materialized = list(events)
        if any(event.device_id != device_id for event in materialized):
            raise ValueError("replay events must all belong to the requested virtual device")
        ordered = sorted(materialized, key=lambda event: (event.timestamp, event.event_id))
        if not ordered:
            return []

        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise KeyError("virtual device not found")
            if device.state != DeviceState.ONLINE:
                raise RuntimeError("virtual device must be online to inject sensor events")
            if any(event.kind not in device.capabilities for event in ordered):
                raise PermissionError("virtual device does not declare this sensor capability")
            current = self._events[device_id]
            if len(current) + len(ordered) > self._max_events:
                raise RuntimeError("virtual device event buffer is full")
            current_ids = {event.event_id for event in current}
            replay_ids = [event.event_id for event in ordered]
            if len(set(replay_ids)) != len(replay_ids) or current_ids.intersection(replay_ids):
                raise ValueError("duplicate sensor event id")
            current.extend(ordered)

        for event in ordered:
            self._emit(
                "sensorium.sensor_event.injected",
                controller_device_id=controller_device_id,
                sensor_event=self._sensor_event_projection(event),
            )
        return [event.to_dict() for event in ordered]

    def run_scenario(
        self,
        scenario: VirtualScenario,
        *,
        controller_device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._authorize(controller_device_id, self.ADMIN_SCOPE)
        with self._lock:
            if scenario.device_id not in self._devices:
                raise KeyError("virtual device not found")
        self._emit(
            "sensorium.virtual_scenario.started",
            controller_device_id=controller_device_id,
            scenario_id=scenario.scenario_id,
            virtual_device_id=scenario.device_id,
            event_count=len(scenario.events),
        )
        results = self.replay_events(
            scenario.device_id,
            scenario.events,
            controller_device_id=controller_device_id,
        )
        self._emit(
            "sensorium.virtual_scenario.completed",
            controller_device_id=controller_device_id,
            scenario_id=scenario.scenario_id,
            virtual_device_id=scenario.device_id,
            event_count=len(results),
        )
        return results

    def audit_events(self, *, controller_device_id: str | None = None) -> list[dict[str, Any]]:
        self._authorize(controller_device_id, self.READ_SCOPE)
        with self._lock:
            return deepcopy(self._audit)
