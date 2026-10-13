from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sensorium.models import DataClassification, SensorEvent, SensorKind


def _bounded_text(value: Any, *, field_name: str, limit: int) -> str:
    text = str(value or "")
    if len(text) > limit:
        raise ValueError(f"{field_name} exceeds {limit} characters")
    return text


def _bounded_dimension(value: Any, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    number = int(value)
    if number < 1 or number > 32768:
        raise ValueError(f"{field_name} is outside the allowed range")
    return number


def _bounded_percent(value: Any, *, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0 or number > 100:
        raise ValueError(f"{field_name} is outside the allowed range")
    return number


def _safe_elements(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("screen elements must be a list")
    if len(value) > 256:
        raise ValueError("screen elements exceed 256 entries")
    allowed = {
        "id",
        "role",
        "label",
        "text",
        "x",
        "y",
        "width",
        "height",
        "actionable",
        "disabled",
    }
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("screen elements must contain objects")
        clean = {key: item[key] for key in allowed if key in item}
        for key in ("label", "text", "role", "id"):
            if key in clean:
                clean[key] = _bounded_text(clean[key], field_name=f"screen element {key}", limit=1000)
        result.append(clean)
    return result


@dataclass(frozen=True, slots=True)
class VirtualAdapterBinding:
    lab: Any
    virtual_device_id: str
    controller_device_id: str | None = None

    def latest(self, kind: SensorKind | str) -> dict[str, Any] | None:
        normalized = SensorKind(kind).value
        cursor: str | None = None
        latest_match: dict[str, Any] | None = None
        for _ in range(10):
            batch = self.lab.read_events(
                self.virtual_device_id,
                controller_device_id=self.controller_device_id,
                after_event_id=cursor,
                limit=1000,
            )
            if not batch:
                break
            for event in batch:
                if event.get("kind") == normalized:
                    latest_match = event
            cursor = str(batch[-1]["event_id"])
            if len(batch) < 1000:
                break
        return latest_match

    def publish(self, event: SensorEvent) -> dict[str, Any]:
        if event.device_id != self.virtual_device_id:
            raise ValueError("sensor event device does not match adapter binding")
        return self.lab.inject_event(event, controller_device_id=self.controller_device_id)


class VirtualScreenAdapter:
    def __init__(self, binding: VirtualAdapterBinding):
        self.binding = binding

    @staticmethod
    def normalize_event(event: dict[str, Any] | None, *, required: bool = False) -> dict[str, Any] | None:
        if event is None:
            if required:
                raise LookupError("virtual screen observation is unavailable")
            return None
        payload = dict(event.get("payload") or {})
        analysis = _bounded_text(
            payload.get("analysis") or payload.get("description") or "",
            field_name="screen analysis",
            limit=20_000,
        )
        elements = _safe_elements(payload.get("elements", payload.get("ui_elements")))
        return {
            "event_id": event["event_id"],
            "timestamp": event["timestamp"],
            "analysis": analysis,
            "width": _bounded_dimension(payload.get("width"), field_name="screen width"),
            "height": _bounded_dimension(payload.get("height"), field_name="screen height"),
            "frame_ref": _bounded_text(payload.get("frame_ref"), field_name="frame_ref", limit=1000) or None,
            "screen_fingerprint": _bounded_text(
                payload.get("screen_fingerprint"),
                field_name="screen_fingerprint",
                limit=256,
            )
            or None,
            "elements": elements,
            "data_classification": event.get("data_classification", "internal"),
            "source": event.get("source"),
            "instruction_trust": "untrusted",
        }

    def latest(self, *, required: bool = False) -> dict[str, Any] | None:
        return self.normalize_event(self.binding.latest(SensorKind.SCREEN), required=required)

    def publish(
        self,
        *,
        analysis: str,
        width: int | None = None,
        height: int | None = None,
        elements: list[dict[str, Any]] | None = None,
        frame_ref: str | None = None,
        screen_fingerprint: str | None = None,
        data_classification: DataClassification | str = DataClassification.INTERNAL,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "analysis": _bounded_text(analysis, field_name="screen analysis", limit=20_000),
            "elements": _safe_elements(elements),
        }
        if width is not None:
            payload["width"] = _bounded_dimension(width, field_name="screen width")
        if height is not None:
            payload["height"] = _bounded_dimension(height, field_name="screen height")
        if frame_ref:
            payload["frame_ref"] = _bounded_text(frame_ref, field_name="frame_ref", limit=1000)
        if screen_fingerprint:
            payload["screen_fingerprint"] = _bounded_text(
                screen_fingerprint,
                field_name="screen_fingerprint",
                limit=256,
            )
        event = SensorEvent.create(
            device_id=self.binding.virtual_device_id,
            kind=SensorKind.SCREEN,
            payload=payload,
            data_classification=data_classification,
            source="sensorium-virtual-screen",
            correlation_id=correlation_id,
        )
        return self.binding.publish(event)


class VirtualClipboardAdapter:
    MAX_TEXT_CHARS = 16_384

    def __init__(self, binding: VirtualAdapterBinding):
        self.binding = binding

    @classmethod
    def normalize_event(
        cls,
        event: dict[str, Any] | None,
        *,
        include_text: bool = False,
    ) -> dict[str, Any] | None:
        if event is None:
            return None
        payload = dict(event.get("payload") or {})
        text = _bounded_text(payload.get("text"), field_name="clipboard text", limit=cls.MAX_TEXT_CHARS)
        result = {
            "event_id": event["event_id"],
            "timestamp": event["timestamp"],
            "mime_type": _bounded_text(
                payload.get("mime_type") or "text/plain",
                field_name="clipboard mime_type",
                limit=120,
            ),
            "content_length": len(text),
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "data_classification": event.get("data_classification", "sensitive"),
            "source": event.get("source"),
            "instruction_trust": "untrusted",
        }
        if include_text:
            result["text"] = text
        return result

    def latest(self, *, include_text: bool = False) -> dict[str, Any] | None:
        return self.normalize_event(self.binding.latest(SensorKind.CLIPBOARD), include_text=include_text)

    def publish(
        self,
        text: str,
        *,
        mime_type: str = "text/plain",
        data_classification: DataClassification | str = DataClassification.SENSITIVE,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "text": _bounded_text(text, field_name="clipboard text", limit=self.MAX_TEXT_CHARS),
            "mime_type": _bounded_text(mime_type, field_name="clipboard mime_type", limit=120),
        }
        event = SensorEvent.create(
            device_id=self.binding.virtual_device_id,
            kind=SensorKind.CLIPBOARD,
            payload=payload,
            data_classification=data_classification,
            source="sensorium-virtual-clipboard",
            correlation_id=correlation_id,
        )
        return self.binding.publish(event)


class VirtualSystemAdapter:
    _TEXT_FIELDS = ("active_app", "active_window", "network_type")
    _PERCENT_FIELDS = ("battery_percent", "cpu_percent", "memory_percent")
    _BOOL_FIELDS = ("network_online", "charging")

    def __init__(self, binding: VirtualAdapterBinding):
        self.binding = binding

    @classmethod
    def normalize_metrics(cls, metrics: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(metrics, dict):
            raise ValueError("system metrics must be an object")
        clean: dict[str, Any] = {}
        for key in cls._TEXT_FIELDS:
            if key in metrics and metrics[key] is not None:
                clean[key] = _bounded_text(metrics[key], field_name=key, limit=500)
        for key in cls._PERCENT_FIELDS:
            if key in metrics and metrics[key] is not None:
                clean[key] = _bounded_percent(metrics[key], field_name=key)
        for key in cls._BOOL_FIELDS:
            if key in metrics and metrics[key] is not None:
                if not isinstance(metrics[key], bool):
                    raise ValueError(f"{key} must be boolean")
                clean[key] = metrics[key]
        return clean

    @classmethod
    def normalize_event(cls, event: dict[str, Any] | None) -> dict[str, Any] | None:
        if event is None:
            return None
        payload = cls.normalize_metrics(dict(event.get("payload") or {}))
        return {
            "event_id": event["event_id"],
            "timestamp": event["timestamp"],
            "metrics": payload,
            "data_classification": event.get("data_classification", "internal"),
            "source": event.get("source"),
            "instruction_trust": "untrusted",
        }

    def latest(self) -> dict[str, Any] | None:
        return self.normalize_event(self.binding.latest(SensorKind.SYSTEM))

    def publish(
        self,
        metrics: dict[str, Any],
        *,
        data_classification: DataClassification | str = DataClassification.INTERNAL,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        event = SensorEvent.create(
            device_id=self.binding.virtual_device_id,
            kind=SensorKind.SYSTEM,
            payload=self.normalize_metrics(metrics),
            data_classification=data_classification,
            source="sensorium-virtual-system",
            correlation_id=correlation_id,
        )
        return self.binding.publish(event)
