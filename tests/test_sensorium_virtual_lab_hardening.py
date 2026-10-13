from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sensorium import SensorEvent, SensorKind, VirtualDevice, VirtualDeviceLab


def _device() -> VirtualDevice:
    return VirtualDevice(
        device_id="atomic-1",
        name="Atomic fixture",
        platform="virtual-linux",
        capabilities=frozenset({SensorKind.SYSTEM}),
        metadata={"nested": {"value": "original"}},
    )


def _event(event_id: str, *, kind: SensorKind = SensorKind.SYSTEM, payload=None) -> SensorEvent:
    return SensorEvent.create(
        event_id=event_id,
        device_id="atomic-1",
        kind=kind,
        timestamp=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc),
        payload=payload or {"nested": {"value": "original"}},
        metadata={"nested": {"value": "original"}},
    )


def test_sensor_event_and_virtual_device_defensively_copy_nested_input_and_output():
    source_payload = {"nested": {"value": "original"}}
    source_metadata = {"nested": {"value": "original"}}
    event = SensorEvent.create(
        event_id="copy-event",
        device_id="atomic-1",
        kind="system",
        payload=source_payload,
        metadata=source_metadata,
    )
    device_metadata = {"nested": {"value": "original"}}
    device = VirtualDevice(
        device_id="copy-device",
        name="Copy fixture",
        platform="virtual-linux",
        capabilities=frozenset({SensorKind.SYSTEM}),
        metadata=device_metadata,
    )

    source_payload["nested"]["value"] = "mutated"
    source_metadata["nested"]["value"] = "mutated"
    device_metadata["nested"]["value"] = "mutated"
    assert event.payload["nested"]["value"] == "original"
    assert event.metadata["nested"]["value"] == "original"
    assert device.metadata["nested"]["value"] == "original"

    event_snapshot = event.to_dict()
    device_snapshot = device.to_dict()
    event_snapshot["payload"]["nested"]["value"] = "changed-output"
    device_snapshot["metadata"]["nested"]["value"] = "changed-output"
    assert event.payload["nested"]["value"] == "original"
    assert device.metadata["nested"]["value"] == "original"


def test_replay_is_atomic_when_any_event_is_invalid():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    valid = _event("valid")
    unsupported = _event("unsupported", kind=SensorKind.CAMERA)

    with pytest.raises(PermissionError, match="capability"):
        lab.replay_events("atomic-1", [valid, unsupported])

    assert lab.read_events("atomic-1") == []


def test_replay_is_atomic_on_duplicate_ids_within_batch():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    first = _event("duplicate")
    second = _event("duplicate", payload={"different": True})

    with pytest.raises(ValueError, match="duplicate"):
        lab.replay_events("atomic-1", [first, second])

    assert lab.read_events("atomic-1") == []


def test_audit_snapshots_cannot_mutate_internal_audit_state():
    lab = VirtualDeviceLab(trusted_local=True)
    lab.register_device(_device())
    first = lab.audit_events()
    first[0]["virtual_device"]["metadata"]["nested"]["value"] = "mutated"
    second = lab.audit_events()
    assert second[0]["virtual_device"]["metadata"]["nested"]["value"] == "original"
