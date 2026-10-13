from core.events import EventBus
from future_intelligence.capability_forge import build_capability_forge


def test_runtime_event_bridge_records_typed_missing_capability(tmp_path):
    events = EventBus()
    forge = build_capability_forge(tmp_path, events=events)

    events.emit(
        "capability.missing",
        error_code="capability_missing",
        capability_name="Invoice PDF parser",
        requested_outcome="Extract normalized invoice fields from an unsupported PDF layout",
        workflow_id="wf-17",
    )

    gaps = forge.store.list_gaps()
    assert len(gaps) == 1
    assert gaps[0].summary == "Invoice PDF parser"
    assert "workflow_id:wf-17" in gaps[0].evidence


def test_runtime_event_bridge_does_not_turn_generic_failures_into_forge_work(tmp_path):
    events = EventBus()
    forge = build_capability_forge(tmp_path, events=events)

    events.emit("workflow.failed", run_id="run-1", error="ordinary provider timeout")

    assert forge.store.list_gaps() == []


def test_runtime_event_bridge_can_be_detached(tmp_path):
    events = EventBus()
    forge = build_capability_forge(tmp_path, events=events)
    forge.detach_event_observers()

    events.emit(
        "tool.unavailable",
        error_code="tool_unavailable",
        capability_name="Detached test capability",
        requested_outcome="Should not be recorded after detach",
    )

    assert forge.store.list_gaps() == []
