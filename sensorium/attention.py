from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SENSOR_ORDER = (
    "memory",
    "screen",
    "camera",
    "microphone",
    "location",
    "motion",
    "environment",
    "network",
    "spatial",
    "wearable",
    "iot",
)


@dataclass(frozen=True, slots=True)
class SensorNeed:
    sensor: str
    reason: str
    priority: int
    optional: bool = True

    def public(self) -> dict:
        return {
            "sensor": self.sensor,
            "reason": self.reason,
            "priority": self.priority,
            "optional": self.optional,
            "execution_authority": False,
        }


@dataclass(frozen=True, slots=True)
class AttentionPlan:
    purpose: str
    requested: tuple[SensorNeed, ...]
    denied: tuple[str, ...]
    battery_saver: bool
    max_active_sensors: int

    def public(self) -> dict:
        return {
            "purpose": self.purpose,
            "requested": [need.public() for need in self.requested],
            "denied": list(self.denied),
            "battery_saver": self.battery_saver,
            "max_active_sensors": self.max_active_sensors,
            "activation_authorized": False,
            "note": "Attention planning never grants a sensor session. Each sensor still needs its own policy and temporary consent grant.",
        }


class AttentionManager:
    """Chooses the minimum useful sensors without activating any of them."""

    KEYWORDS = {
        "camera": {"look", "see", "show", "point", "cable", "object", "room", "assemble", "repair", "cook", "exercise"},
        "screen": {"screen", "setting", "app", "button", "phone", "computer", "error", "window", "display"},
        "microphone": {"hear", "listen", "sound", "noise", "alarm", "doorbell", "voice", "speaker"},
        "location": {"where am i", "near me", "location", "route", "place", "arrive", "leave"},
        "motion": {"moving", "walking", "running", "orientation", "tilt", "shake", "motion", "exercise"},
        "environment": {"temperature", "pressure", "light", "dark", "bright", "proximity", "environment"},
        "network": {"wifi", "network", "internet", "router", "offline", "connection"},
        "spatial": {"behind", "in front", "distance", "depth", "3d", "room", "where is", "spatial"},
        "wearable": {"watch", "earbuds", "glasses", "wearable"},
        "iot": {"thermostat", "light", "door", "sensor", "smart home", "appliance"},
    }

    def __init__(self, *, events=None) -> None:
        self.events = events

    @staticmethod
    def _normalized_permissions(permitted: Iterable[str] | None) -> set[str]:
        return {str(value).strip().lower() for value in (permitted or ()) if str(value).strip()}

    def plan(
        self,
        purpose: str,
        *,
        permitted: Iterable[str] | None = None,
        battery_percent: int | None = None,
        privacy_denied: Iterable[str] | None = None,
        max_active_sensors: int = 3,
    ) -> AttentionPlan:
        text = str(purpose or "").strip().lower()[:2_000]
        if not text:
            raise ValueError("attention purpose is required")
        allowed = self._normalized_permissions(permitted)
        privacy_block = self._normalized_permissions(privacy_denied)
        battery_saver = battery_percent is not None and int(battery_percent) <= 20
        limit = max(1, min(int(max_active_sensors), 6))
        if battery_saver:
            limit = min(limit, 2)

        needs: list[SensorNeed] = [SensorNeed("memory", "Use existing context before waking physical sensors.", 100, False)]
        for sensor in SENSOR_ORDER:
            if sensor == "memory":
                continue
            words = self.KEYWORDS.get(sensor, set())
            matches = sum(1 for word in words if word in text)
            if matches:
                priority = 80 + min(matches, 5) * 3
                reason = f"Purpose mentions context normally answered by {sensor}."
                needs.append(SensorNeed(sensor, reason, priority, True))

        if len(needs) == 1:
            needs.append(SensorNeed("camera", "Visual context may help if memory is insufficient.", 35, True))

        denied: list[str] = []
        selected: list[SensorNeed] = []
        for need in sorted(needs, key=lambda row: (-row.priority, SENSOR_ORDER.index(row.sensor) if row.sensor in SENSOR_ORDER else 99)):
            if need.sensor != "memory" and need.sensor in privacy_block:
                denied.append(need.sensor)
                continue
            if need.sensor != "memory" and allowed and need.sensor not in allowed:
                denied.append(need.sensor)
                continue
            if len([item for item in selected if item.sensor != "memory"]) >= limit and need.sensor != "memory":
                continue
            selected.append(need)

        plan = AttentionPlan(
            purpose=text,
            requested=tuple(selected),
            denied=tuple(sorted(set(denied))),
            battery_saver=battery_saver,
            max_active_sensors=limit,
        )
        if self.events is not None:
            self.events.emit(
                "sensorium.attention.planned",
                purpose=text[:240],
                requested=[item.sensor for item in plan.requested],
                denied=list(plan.denied),
                activation_authorized=False,
            )
        return plan
