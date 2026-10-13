from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .service import CapabilityForgeService


FORGE_OBSERVED_EVENTS = (
    "capability.gap",
    "capability.missing",
    "tool.unavailable",
    "workflow.failed",
    "automation.failed",
    "engineering.capability_missing",
)


def attach_capability_forge_observers(events, forge: CapabilityForgeService) -> Callable[[], None]:
    """Attach conservative event observers and return a detach callback.

    The bridge does not infer that every failure is a capability gap. It forwards
    normalized events to F1, whose detector still requires an explicit typed gap
    signal (or a recognized missing-capability error code).
    """
    if events is None or not hasattr(events, "subscribe"):
        raise TypeError("an EventBus-compatible events object is required")
    unsubscribers: list[Callable[[], None]] = []

    def observe(event: dict[str, Any]) -> None:
        payload = dict(event.get("payload") or {})
        for key, value in event.items():
            if key not in {"event", "payload"} and key not in payload:
                payload[key] = value
        payload.setdefault("source_event", str(event.get("event") or "unknown"))
        forge.observe_gap("system", payload)

    for event_name in FORGE_OBSERVED_EVENTS:
        unsubscribers.append(events.subscribe(event_name, observe))

    def detach() -> None:
        for unsubscribe in reversed(unsubscribers):
            unsubscribe()

    return detach
