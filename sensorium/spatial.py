from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SpatialAnchor:
    anchor_id: str
    label: str
    source: str
    x: float
    y: float
    z: float
    confidence: float
    captured_at: float
    persistent: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "label": self.label,
            "source": self.source,
            "position_m": {"x": self.x, "y": self.y, "z": self.z},
            "distance_from_origin_m": math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z),
            "confidence": self.confidence,
            "captured_at": self.captured_at,
            "persistent": self.persistent,
            "execution_authority": False,
        }


class SpatialWorld:
    """Ephemeral 3D/spatial anchors sourced from ARKit/ARCore/depth clients."""

    def __init__(self, *, events=None, max_anchors: int = 2048) -> None:
        self.events = events
        self.max_anchors = max(32, min(int(max_anchors), 10_000))
        self._anchors: dict[str, SpatialAnchor] = {}

    @staticmethod
    def _coordinate(value: Any, field: str) -> float:
        number = float(value)
        if not math.isfinite(number) or abs(number) > 100_000:
            raise ValueError(f"invalid spatial coordinate {field}")
        return number

    def upsert(
        self,
        *,
        label: str,
        source: str,
        x: float,
        y: float,
        z: float,
        confidence: float = 0.7,
        anchor_id: str | None = None,
        captured_at: float | None = None,
        persistent: bool = False,
    ) -> dict:
        key = str(anchor_id or uuid.uuid4())[:200]
        title = str(label or "object").strip()[:160]
        if not title:
            raise ValueError("spatial anchor label is required")
        anchor = SpatialAnchor(
            anchor_id=key,
            label=title,
            source=str(source or "spatial")[:160],
            x=self._coordinate(x, "x"),
            y=self._coordinate(y, "y"),
            z=self._coordinate(z, "z"),
            confidence=max(0.0, min(float(confidence), 1.0)),
            captured_at=float(captured_at or time.time()),
            persistent=bool(persistent),
        )
        if len(self._anchors) >= self.max_anchors and key not in self._anchors:
            evict = min(self._anchors.values(), key=lambda item: item.captured_at)
            self._anchors.pop(evict.anchor_id, None)
        self._anchors[key] = anchor
        if self.events is not None:
            self.events.emit(
                "sensorium.spatial.anchor_updated",
                anchor_id=key,
                source=anchor.source,
                persistent=anchor.persistent,
                execution_authority=False,
            )
        return anchor.public()

    def get(self, anchor_id: str) -> dict:
        anchor = self._anchors.get(str(anchor_id))
        if anchor is None:
            raise KeyError("spatial anchor not found")
        return anchor.public()

    def list(self) -> list[dict]:
        return [anchor.public() for anchor in sorted(self._anchors.values(), key=lambda item: item.captured_at, reverse=True)]

    def relation(self, first_id: str, second_id: str) -> dict:
        first = self._anchors.get(str(first_id))
        second = self._anchors.get(str(second_id))
        if first is None or second is None:
            raise KeyError("spatial anchor not found")
        dx = first.x - second.x
        dy = first.y - second.y
        dz = first.z - second.z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        horizontal = "left_of" if dx < -0.1 else "right_of" if dx > 0.1 else "aligned_x"
        vertical = "below" if dy < -0.1 else "above" if dy > 0.1 else "aligned_y"
        depth = "in_front_of" if dz < -0.1 else "behind" if dz > 0.1 else "aligned_z"
        return {
            "first": first.anchor_id,
            "second": second.anchor_id,
            "distance_m": distance,
            "relations": [horizontal, vertical, depth],
            "confidence": min(first.confidence, second.confidence),
            "execution_authority": False,
        }

    def clear_ephemeral(self) -> int:
        ids = [key for key, value in self._anchors.items() if not value.persistent]
        for key in ids:
            self._anchors.pop(key, None)
        return len(ids)
