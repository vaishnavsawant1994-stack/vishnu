from __future__ import annotations

from core.events import EventBus
from sensorium.live_work import SensoriumLiveWorkProjection


def test_native_evidence_live_work_projection_is_safe_and_verification_only():
    bus = EventBus()
    projection = SensoriumLiveWorkProjection(bus)
    try:
        bus.emit(
            "sensorium.native_device.evidence_recorded",
            evidence_id=17,
            provider="android_emulator",
            platform="android",
            target_id="emulator-5554",
            status="ready",
            metadata={"model": "private-model", "battery_percent": 87},
            raw_output="private-adb-output",
            authorization="Bearer secret-value",
            command="adb shell private-command",
        )
        snapshot = projection.snapshot()
        assert snapshot["state"] == "verifying"
        assert snapshot["execution_authority"] is False
        assert snapshot["raw_sensor_content_exposed"] is False
        event = snapshot["events"][-1]
        assert event["source_event"] == "sensorium.native_device.evidence_recorded"
        assert event["metadata"] == {
            "evidence_id": 17,
            "provider": "android_emulator",
            "platform": "android",
            "target_id": "emulator-5554",
            "status": "ready",
        }
        rendered = repr(snapshot)
        assert "private-model" not in rendered
        assert "private-adb-output" not in rendered
        assert "secret-value" not in rendered
        assert "private-command" not in rendered
    finally:
        projection.close()
