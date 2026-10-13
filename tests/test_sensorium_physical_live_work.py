from core.events import EventBus
from sensorium.live_work import SensoriumLiveWorkProjection


def test_physical_observation_projects_watching_without_raw_content():
    events = EventBus()
    projection = SensoriumLiveWorkProjection(events)

    events.emit(
        "sensorium.physical.observed",
        controller_device_id="owner-device",
        target_device_id="phone-device",
        platform="mobile",
        sensor="device_info,battery",
        analysis="PRIVATE SCREEN CONTENT",
        text="PRIVATE CLIPBOARD CONTENT",
        parameters={"url": "https://should-never-appear.example"},
        execution_authority=False,
    )

    snapshot = projection.snapshot(limit=1)
    rendered = repr(snapshot)
    assert snapshot["state"] == "watching"
    assert snapshot["events"][0]["metadata"] == {
        "target_device_id": "phone-device",
        "controller_device_id": "owner-device",
        "platform": "mobile",
        "sensor": "device_info,battery",
    }
    assert "PRIVATE SCREEN CONTENT" not in rendered
    assert "PRIVATE CLIPBOARD CONTENT" not in rendered
    assert "should-never-appear" not in rendered
    assert snapshot["execution_authority"] is False
    assert snapshot["raw_sensor_content_exposed"] is False

    projection.close()
