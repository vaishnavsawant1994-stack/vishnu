from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WearableObservation:
    device_id: str
    wearable_type: str
    transport: str
    source: str
    payload: dict[str, Any]
    captured_at: float
    confidence: float

    def public(self) -> dict:
        return {
            "device_id": self.device_id,
            "wearable_type": self.wearable_type,
            "transport": self.transport,
            "source": self.source,
            "payload": dict(self.payload),
            "captured_at": self.captured_at,
            "confidence": self.confidence,
            "raw_media_retained": False,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }


class WearableSensorium:
    """Normalizes watch/earbud/glasses observations into Sensorium evidence.

    The boundary represents real vendor transport families (WatchConnectivity,
    Wear OS Data Layer, Bluetooth audio metadata and paired-phone relays) while
    deliberately refusing raw camera/audio media. Glasses/body cameras remain
    governed camera/microphone sensors and must use their separate session paths.
    """

    TYPES = frozenset({"apple_watch", "wear_os", "earbuds", "smart_glasses", "body_camera", "other"})
    TRANSPORT_BY_TYPE = {
        "apple_watch": "watch_connectivity",
        "wear_os": "wear_data_layer",
        "earbuds": "bluetooth_audio",
        "smart_glasses": "phone_relay",
        "body_camera": "phone_relay",
        "other": "phone_relay",
    }
    TRANSPORTS = frozenset({"watch_connectivity", "wear_data_layer", "bluetooth_audio", "phone_relay", "external_https"})
    FORBIDDEN_MEDIA_KEYS = (
        "image",
        "photo",
        "video",
        "frame",
        "base64",
        "pcm",
        "audio_bytes",
        "recording",
        "microphone_bytes",
        "camera_bytes",
    )
    MAX_PAYLOAD_BYTES = 64 * 1024

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
            "transport": self.TRANSPORT_BY_TYPE[kind],
            "label": str(label or did).strip()[:160],
            "capabilities": caps,
            "registered_at": time.time(),
            "camera_permission_granted": False,
            "microphone_permission_granted": False,
            "execution_authority": False,
        }
        self._devices[did] = row
        if self.events is not None:
            self.events.emit(
                "sensorium.wearable.registered",
                device_id=did,
                wearable_type=kind,
                transport=row["transport"],
                execution_authority=False,
            )
        return dict(row)

    def list(self) -> list[dict]:
        return [dict(value) for _, value in sorted(self._devices.items())]

    @classmethod
    def _bounded_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        safe = dict(list((payload or {}).items())[:128])
        lowered = {str(key).lower() for key in safe}
        if any(any(token in key for token in cls.FORBIDDEN_MEDIA_KEYS) for key in lowered):
            raise PermissionError(
                "raw wearable camera/audio media must use the separately governed camera or microphone Sensorium path"
            )
        try:
            encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("wearable observation must be JSON-serializable") from exc
        if len(encoded) > cls.MAX_PAYLOAD_BYTES:
            raise ValueError("wearable observation is too large")
        return safe

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
        supplied_source = str(source or "wearable").strip().lower()
        expected_transport = str(row["transport"])
        if supplied_source in {"", "wearable"}:
            normalized_source = expected_transport
        elif supplied_source in self.TRANSPORTS:
            normalized_source = supplied_source
        else:
            raise ValueError("unsupported wearable transport source")
        if normalized_source != expected_transport and normalized_source != "phone_relay":
            raise PermissionError("wearable observation arrived through an unexpected transport")
        safe = self._bounded_payload(payload)
        observation = WearableObservation(
            device_id=did,
            wearable_type=str(row["wearable_type"]),
            transport=normalized_source,
            source=f"wearable:{normalized_source}",
            payload=safe,
            captured_at=float(captured_at or time.time()),
            confidence=max(0.0, min(float(confidence), 1.0)),
        )
        if self.events is not None:
            self.events.emit(
                "sensorium.wearable.observed",
                device_id=did,
                wearable_type=row["wearable_type"],
                transport=observation.transport,
                source=observation.source,
                raw_media_retained=False,
                execution_authority=False,
            )
        return observation.public()
