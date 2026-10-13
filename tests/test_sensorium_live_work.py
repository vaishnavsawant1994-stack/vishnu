from __future__ import annotations

from core.events import EventBus
from sensorium.live_work import SensoriumLiveWorkProjection


def test_live_work_maps_existing_runtime_events_without_raw_content():
    bus = EventBus()
    projection = SensoriumLiveWorkProjection(bus)
    secret = "clipboard-secret-never-project"

    bus.emit(
        "sensorium.sensor_event.injected",
        event_id="evt-1",
        kind="clipboard",
        virtual_device_id="virtual-1",
        payload={"text": secret},
    )
    bus.emit(
        "computer.planned",
        step_count=3,
        goal="sensitive user goal that must not project",
    )
    bus.emit(
        "computer.execution.started",
        transaction_id="tx-1",
        goal="another sensitive goal",
        step_count=3,
    )
    bus.emit(
        "computer.step.verified",
        transaction_id="tx-1",
        step=1,
        kind="click",
        params={"text": secret},
    )

    snapshot = projection.snapshot()
    assert snapshot["authority"] == "read_only_projection"
    assert snapshot["presentation_only"] is True
    assert snapshot["execution_authority"] is False
    assert snapshot["reasoning_exposed"] is False
    assert snapshot["raw_sensor_content_exposed"] is False
    assert snapshot["state"] == "verifying"
    assert snapshot["activity"] == "Computer step verified"
    assert secret not in repr(snapshot)
    assert "sensitive user goal" not in repr(snapshot)
    assert snapshot["events"][0]["metadata"] == {
        "event_id": "evt-1",
        "virtual_device_id": "virtual-1",
        "kind": "clipboard",
    }
    assert snapshot["events"][-1]["metadata"]["transaction_id"] == "tx-1"
    assert snapshot["events"][-1]["metadata"]["step"] == 1


def test_live_work_maps_approval_failure_and_completion_states():
    bus = EventBus()
    projection = SensoriumLiveWorkProjection(bus)

    bus.emit("workflow.approval_required", run_id="run-1", tool="computer_execute")
    assert projection.snapshot()["state"] == "waiting_for_approval"

    bus.emit("computer.execution.failed", transaction_id="tx-1", error_type="VerificationError")
    failed = projection.snapshot()
    assert failed["state"] == "blocked"
    assert "VerificationError" not in repr(failed)

    bus.emit("computer.execution.completed", transaction_id="tx-1", goal="private")
    completed = projection.snapshot()
    assert completed["state"] == "completed"
    assert completed["events"][-1]["metadata"] == {"transaction_id": "tx-1"}


def test_live_work_is_bounded_and_can_unsubscribe():
    bus = EventBus()
    projection = SensoriumLiveWorkProjection(bus, max_events=2)
    bus.emit("computer.observed", screenshot="private/path.png")
    bus.emit("computer.planned", step_count=1)
    bus.emit("computer.execution.started", transaction_id="tx-1", step_count=1)

    snapshot = projection.snapshot(limit=50)
    assert len(snapshot["events"]) == 2
    assert [item["state"] for item in snapshot["events"]] == ["thinking", "working"]
    assert "private/path.png" not in repr(snapshot)

    projection.close()
    bus.emit("computer.execution.completed", transaction_id="tx-1")
    assert projection.snapshot()["state"] == "working"
