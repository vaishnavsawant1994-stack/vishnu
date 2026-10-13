from __future__ import annotations

from core.events import EventBus
from sensorium import DataClassification, SensorEvent, SensorKind, VirtualDevice, VirtualDeviceLab


def test_shared_sensor_projection_never_contains_raw_payload():
    emitted: list[dict] = []
    bus = EventBus()
    bus.subscribe("sensorium.sensor_event.injected", emitted.append)
    lab = VirtualDeviceLab(event_bus=bus, trusted_local=True)
    lab.register_device(
        VirtualDevice(
            device_id="virtual-desktop-1",
            name="CI desktop",
            platform="virtual-windows",
            capabilities=frozenset({SensorKind.CLIPBOARD}),
        )
    )
    secret = "clipboard-secret-that-must-not-enter-shared-audit"
    lab.inject_event(
        SensorEvent.create(
            device_id="virtual-desktop-1",
            kind=SensorKind.CLIPBOARD,
            payload={"text": secret, "mime_type": "text/plain"},
            data_classification=DataClassification.SENSITIVE,
            source="security-test",
        )
    )

    assert emitted
    projection = emitted[0]["sensor_event"]
    assert projection["kind"] == "clipboard"
    assert projection["payload_projected"] is False
    assert "payload" not in projection
    assert secret not in repr(emitted[0])

    audit = lab.audit_events()
    assert secret not in repr(audit)

    stored = lab.read_events("virtual-desktop-1")
    assert stored[0]["payload"]["text"] == secret
