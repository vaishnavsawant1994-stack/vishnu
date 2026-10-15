from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WearableObservation:
    device_id: str
    wearable_type: str
    source: str
    payload: dict[str, Any]
    captured_at: float
    confidence: float

    def public(self) -> dict:
        return {
            "device_id": self.device_id,
            "wearable_type": self.wearable_type,
            "source": self.source,
            "payload": dict(self.payload),
            "captured_at": self.captured_at,
            "confidence": self.confidence,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }


class WearableSensorium:
    """Normalizes watch/earbud/glasses observations into Sensorium evidence.

    Glasses/body cameras remain camera sensors and therefore require the same
    explicit camera session authority; registering a wearable never grants
    camera or microphone permission.
    """

    TYPES = frozenset({"apple_watch", "wear_os", "earbuds", "smart_glasses", "body_camera", "other"})

    def __init__(self, *, events=None) -> None:
        self.events = events
        self._devices: dict[str, dict[str, Any]] = {}

    def register(self, device_id: str, *, wearable_type: str, label: str, capabilities) -> dict:
        did = str(device_id or "").strip()[:200]
        kind = str(wearable_type or "other").strip().lower()
        if not did:
            raise ValueError("wearable device ID is required")
        if kind not in self.TYPES:
            raise ValueError("unsupported wearable type")
        caps = sorted({str(item).strip().lower()[:120] for item in capabilities if str(item).strip()})[:64]
        row = {
            "device_id": did,
            "wearable_type": kind,
            "label": str(label or did).strip()[:160],
            "capabilities": caps,
            "registered_at": time.time(),
        }
        self._devices[did] = row
        if self.events is not None:
            self.events.emit("sensorium.wearable.registered", device_id=did, wearable_type=kind)
        return dict(row)

    def list(self) -> list[dict]:
        return [dict(value) for _, value in sorted(self._devices.items())]

    def ingest(
        self,
        device_id: str,
        *,
        source: str,
        payload: dict[str, Any],
        confidence: float = 0.8,
        captured_at: float | None = None,
    ) -> dict:
        did = str(device_id or "").strip()
        row = self._devices.get(did)
        if row is None:
            raise KeyError("wearable is not registered")
        safe = dict(list((payload or {}).items())[:128])
        observation = WearableObservation(
            device_id=did,
            wearable_type=str(row["wearable_type"]),
            source=str(source or "wearable")[:160],
            payload=safe,
            captured_at=float(captured_at or time.time()),
            confidence=max(0.0, min(float(confidence), 1.0)),
        )
        if self.events is not None:
            self.events.emit(
                "sensorium.wearable.observed",
                device_id=did,
                wearable_type=row["wearable_type"],
                source=observation.source,
                execution_authority=False,
            )
        return observation.public()
