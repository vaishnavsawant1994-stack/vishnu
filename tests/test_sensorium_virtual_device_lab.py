from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.events import EventBus
from sensorium import (
    DataClassification,
    DeviceState,
    SensorEvent,
    SensorKind,
    VirtualDevice,
    VirtualDeviceLab,
    VirtualScenario,
)


def _device(device_id: str = "virtual-desktop-1") -> VirtualDevice:
    return VirtualDevice(
        device_id=device_id,
        name="CI desktop",
        platform="virtual-windows",
        capabilities=frozenset({SensorKind.SCREEN, SensorKind.CLIPBOARD, SensorKind.SYSTEM}),
        metadata={"fixture": "sensorium-v1"},
    )


def _event(device_id: str, event_id: str, second: int, *, kind: SensorKind = SensorKind.SCREEN) -> SensorEvent:
    return SensorEvent.create(
        event_id=event_id,
        device_id=device_id,
        kind=kind,
        timestamp=datetime(2026, 10, 13, 10, 0, second, tzinfo=timezone.utc),
        payload={"frame": second},
        data_classification=DataClassification.INTERNAL,
        correlation_id="scenario-1",
    )


def test_lab_fails_closed_without_authorization_boundary():
    with pytest.raises(ValueError, match="authorizer"):
        VirtualDeviceLab()


def test_scoped_controller_authorization_is_enforced():
    allowed = {("owner-device", "device:read")}
    lab = VirtualDeviceLab(authorizer=lambda device_id, scope: (device_id, scope) in allowed)
    with pytest.raises(PermissionError, match="device:admin"):
        lab.register_device(_device(), controller_device_id="owner-device")


def test_register_inject_read_and_event_bus_projection():
    emitted: list[dict] = []
    bus = EventBus()
    bus.subscribe("sensorium.sensor_event.injected", emitted.append)
    lab = VirtualDeviceLab(event_bus=bus, trusted_local=True)
    lab.register_device(_device())

    event = _event("virtual-desktop-1", "event-1", 1)
    snapshot = lab.inject_event(event)

    assert snapshot["event_id"] == "event-1"
    assert lab.read_events("virtual-desktop-1") == [snapshot]
    assert emitted[0]["event"] == "sensorium.sensor_event.injected"
    assert emitted[0]["sensor_event"]["device_id"] == "virtual-desktop-1"


def test_device_capability_and_state_are_hard_boundaries():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    with pytest.raises(PermissionError, match="capability"):
        lab.inject_event(_event("virtual-desktop-1", "event-camera", 1, kind=SensorKind.CAMERA))

    lab.set_state("virtual-desktop-1", DeviceState.PAUSED)
    with pytest.raises(RuntimeError, match="online"):
        lab.inject_event(_event("virtual-desktop-1", "event-screen", 2))


def test_payload_bounds_and_timezone_validation():
    with pytest.raises(ValueError, match="payload exceeds"):
        SensorEvent.create(
            event_id="oversized",
            device_id="virtual-desktop-1",
            kind=SensorKind.SYSTEM,
            payload={"value": "x" * (64 * 1024)},
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        SensorEvent(
            event_id="naive-time",
            device_id="virtual-desktop-1",
            kind=SensorKind.SYSTEM,
            timestamp=datetime(2026, 10, 13, 10, 0, 0),
            payload={},
        )


def test_event_round_trip_is_stable():
    event = _event("virtual-desktop-1", "round-trip", 3)
    restored = SensorEvent.from_dict(event.to_dict())
    assert restored == event
    assert restored.timestamp.tzinfo == timezone.utc


def test_replay_and_scenario_order_are_deterministic():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    base = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)
    late = SensorEvent.create(
        event_id="event-z",
        device_id="virtual-desktop-1",
        kind=SensorKind.SCREEN,
        timestamp=base + timedelta(seconds=2),
        payload={"order": 2},
    )
    early_b = SensorEvent.create(
        event_id="event-b",
        device_id="virtual-desktop-1",
        kind=SensorKind.SCREEN,
        timestamp=base + timedelta(seconds=1),
        payload={"order": 1},
    )
    early_a = SensorEvent.create(
        event_id="event-a",
        device_id="virtual-desktop-1",
        kind=SensorKind.SCREEN,
        timestamp=base + timedelta(seconds=1),
        payload={"order": 0},
    )
    scenario = VirtualScenario(
        scenario_id="deterministic-replay",
        device_id="virtual-desktop-1",
        events=(late, early_b, early_a),
    )

    results = lab.run_scenario(scenario)
    assert [item["event_id"] for item in results] == ["event-a", "event-b", "event-z"]
    assert [item["event_id"] for item in lab.read_events("virtual-desktop-1")] == [
        "event-a",
        "event-b",
        "event-z",
    ]


def test_devices_are_isolated_and_removal_clears_events():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device("virtual-a"))
    lab.register_device(_device("virtual-b"))
    lab.inject_event(_event("virtual-a", "a-1", 1))
    lab.inject_event(_event("virtual-b", "b-1", 1))

    assert [item["event_id"] for item in lab.read_events("virtual-a")] == ["a-1"]
    assert [item["event_id"] for item in lab.read_events("virtual-b")] == ["b-1"]

    lab.remove_device("virtual-a")
    with pytest.raises(KeyError, match="not found"):
        lab.read_events("virtual-a")
    assert [item["event_id"] for item in lab.read_events("virtual-b")] == ["b-1"]


def test_duplicate_event_ids_and_missing_cursor_fail_closed():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    event = _event("virtual-desktop-1", "duplicate", 1)
    lab.inject_event(event)
    with pytest.raises(ValueError, match="duplicate"):
        lab.inject_event(event)
    with pytest.raises(KeyError, match="after_event_id"):
        lab.read_events("virtual-desktop-1", after_event_id="missing")
