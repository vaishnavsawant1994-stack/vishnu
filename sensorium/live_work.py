from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Mapping


class SensoriumLiveWorkProjection:
    """Presentation-only projection of safe Sensorium/computer-control progress.

    This class never exposes chain-of-thought, raw sensor payloads, screenshots,
    clipboard contents, typed text, action parameters, or execution authority.
    It maps existing authoritative runtime events into a small UI vocabulary.
    """

    AUTHORITY = "read_only_projection"
    MAX_EVENTS = 200

    _EVENTS: dict[str, tuple[str, str]] = {
        "sensorium.sensor_event.injected": ("watching", "Device context updated"),
        "sensorium.context.observed": ("watching", "Context observed"),
        "computer.observed": ("watching", "Screen observed"),
        "computer.planned": ("thinking", "Action plan prepared"),
        "computer.execution.started": ("working", "Computer work started"),
        "computer.step.verified": ("verifying", "Computer step verified"),
        "computer.execution.completed": ("completed", "Computer work completed"),
        "computer.execution.failed": ("blocked", "Computer work needs attention"),
        "turn.needs_approval": ("waiting_for_approval", "Waiting for approval"),
        "workflow.approval_required": ("waiting_for_approval", "Waiting for approval"),
        "tool.approval_required": ("waiting_for_approval", "Waiting for approval"),
        "approval.required": ("waiting_for_approval", "Waiting for approval"),
        "emergency_stop.activated": ("blocked", "Emergency stop is active"),
    }
    _SAFE_METADATA = {
        "transaction_id",
        "step",
        "step_count",
        "kind",
        "event_id",
        "virtual_device_id",
        "controller_device_id",
        "run_id",
        "automation_id",
        "workflow_id",
        "request_id",
    }

    def __init__(self, event_bus: Any, *, max_events: int = MAX_EVENTS) -> None:
        if event_bus is None:
            raise ValueError("event_bus is required")
        if max_events < 1 or max_events > self.MAX_EVENTS:
            raise ValueError(f"max_events must be between 1 and {self.MAX_EVENTS}")
        self._event_bus = event_bus
        self._events: deque[dict[str, Any]] = deque(maxlen=int(max_events))
        self._state = "idle"
        self._activity = ""
        self._sequence = 0
        self._lock = RLock()
        self._unsubscribe = [event_bus.subscribe(name, self._accept) for name in self._EVENTS]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _safe_metadata(cls, event: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in cls._SAFE_METADATA:
            value = event.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (str, int, float, bool)):
                text = str(value)
                metadata[key] = value if not isinstance(value, str) else text[:256]
        return metadata

    def _accept(self, event: dict[str, Any]) -> None:
        name = str(event.get("event") or "")
        mapping = self._EVENTS.get(name)
        if mapping is None:
            return
        state, activity = mapping
        with self._lock:
            self._sequence += 1
            item = {
                "sequence": self._sequence,
                "timestamp": self._now(),
                "source_event": name,
                "state": state,
                "activity": activity,
                "metadata": self._safe_metadata(event),
            }
            self._events.append(item)
            self._state = state
            self._activity = activity

    def snapshot(self, *, limit: int = 50) -> dict[str, Any]:
        bounded = max(1, min(int(limit), self.MAX_EVENTS))
        with self._lock:
            events = list(self._events)[-bounded:]
            return {
                "authority": self.AUTHORITY,
                "presentation_only": True,
                "execution_authority": False,
                "reasoning_exposed": False,
                "raw_sensor_content_exposed": False,
                "state": self._state,
                "activity": self._activity,
                "events": [dict(item) for item in events],
            }

    def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            try:
                unsubscribe()
            except Exception:
                pass
        self._unsubscribe = []


_SENSORIUM_LIVING_STATES: dict[str, tuple[str, float, str]] = {
    "watching": ("watching", 0.4, "Vishnu is observing authorized device context."),
    "thinking": ("thinking", 0.5, "Vishnu is preparing the next governed computer action."),
    "working": ("working", 0.68, "Vishnu is carrying out governed computer work."),
    "waiting_for_approval": ("waiting_approval", 0.95, "Vishnu is waiting for owner approval."),
    "verifying": ("verifying", 0.72, "Vishnu is verifying the latest governed computer action."),
    "blocked": ("blocked", 0.8, "Governed computer work needs attention before it can continue."),
    "completed": ("completed", 0.2, "Governed computer work is complete."),
}
_CANONICAL_IDLE_STATES = {"", "idle", "completed"}


def overlay_sensorium_living(
    canonical_living: Mapping[str, Any] | None,
    sensorium_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Overlay safe Sensorium presence onto an idle/terminal living projection.

    Canonical Project Work always wins while active, blocked, recovering,
    verifying, reviewing, replanning, or waiting for approval. Sensorium may
    provide the global living state only when canonical work is idle/terminal.
    No Sensorium event, metadata, activity text, sensor payload, or model
    reasoning is copied into this projection.
    """

    living = dict(canonical_living or {})
    living.setdefault("authority", "presentation_only")
    living.setdefault("source", "canonical_work_attention")
    living["sensorium_overlay"] = False

    if not sensorium_snapshot:
        return living
    if sensorium_snapshot.get("authority") != SensoriumLiveWorkProjection.AUTHORITY:
        return living
    if sensorium_snapshot.get("presentation_only") is not True:
        return living
    if sensorium_snapshot.get("execution_authority") is not False:
        return living
    if sensorium_snapshot.get("reasoning_exposed") is not False:
        return living
    if sensorium_snapshot.get("raw_sensor_content_exposed") is not False:
        return living

    canonical_state = str(living.get("state") or "").strip().lower()
    if canonical_state not in _CANONICAL_IDLE_STATES:
        return living

    sensorium_state = str(sensorium_snapshot.get("state") or "").strip().lower()
    mapped = _SENSORIUM_LIVING_STATES.get(sensorium_state)
    if mapped is None or sensorium_state in {"", "completed"}:
        return living

    state, intensity, activity = mapped
    living.update(
        {
            "authority": "presentation_only",
            "source": "canonical_work_attention+sensorium",
            "state": state,
            "activity": activity,
            "intensity": intensity,
            "sensorium_overlay": True,
            "sensorium_state": sensorium_state,
            "sensorium_needs_attention": sensorium_state in {"waiting_for_approval", "blocked"},
        }
    )
    return living
