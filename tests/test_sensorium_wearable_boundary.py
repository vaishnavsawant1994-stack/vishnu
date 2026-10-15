from __future__ import annotations

import pytest

from sensorium.wearables import WearableSensorium


def test_wearable_registration_maps_real_transport_families_without_sensor_grants():
    sensorium = WearableSensorium()
    apple = sensorium.register(
        "watch-1",
        wearable_type="apple_watch",
        label="Owner Watch",
        capabilities=["motion", "heart_rate"],
    )
    wear = sensorium.register(
        "wear-1",
        wearable_type="wear_os",
        label="Wear watch",
        capabilities=["motion"],
    )
    earbuds = sensorium.register(
        "buds-1",
        wearable_type="earbuds",
        label="Earbuds",
        capabilities=["wear_state", "battery"],
    )
    assert apple["transport"] == "watch_connectivity"
    assert wear["transport"] == "wear_data_layer"
    assert earbuds["transport"] == "bluetooth_audio"
    assert apple["camera_permission_granted"] is False
    assert apple["microphone_permission_granted"] is False
    assert apple["execution_authority"] is False


def test_wearable_ingest_accepts_semantic_transport_evidence_only():
    sensorium = WearableSensorium()
    sensorium.register(
        "watch-1",
        wearable_type="apple_watch",
        label="Owner Watch",
        capabilities=["motion"],
    )
    observed = sensorium.ingest(
        "watch-1",
        source="watch_connectivity",
        payload={"activity": "walking", "steps_delta": 12},
        confidence=0.9,
    )
    assert observed["transport"] == "watch_connectivity"
    assert observed["payload"]["activity"] == "walking"
    assert observed["raw_media_retained"] is False
    assert observed["execution_authority"] is False


def test_wearable_ingest_rejects_raw_camera_audio_and_unexpected_transport():
    sensorium = WearableSensorium()
    sensorium.register(
        "glasses-1",
        wearable_type="smart_glasses",
        label="Glasses",
        capabilities=["camera", "motion"],
    )
    with pytest.raises(PermissionError, match="separately governed"):
        sensorium.ingest(
            "glasses-1",
            source="phone_relay",
            payload={"image_base64": "AAAA"},
        )
    with pytest.raises(PermissionError, match="unexpected transport"):
        sensorium.ingest(
            "glasses-1",
            source="watch_connectivity",
            payload={"head_pose": [0, 0, 0]},
        )


def test_wearable_default_source_resolves_to_registered_transport():
    sensorium = WearableSensorium()
    sensorium.register(
        "wear-1",
        wearable_type="wear_os",
        label="Wear watch",
        capabilities=["motion"],
    )
    observed = sensorium.ingest(
        "wear-1",
        source="wearable",
        payload={"activity": "stationary"},
    )
    assert observed["transport"] == "wear_data_layer"
