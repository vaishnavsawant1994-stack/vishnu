import pytest

from sensorium.core import ProviderMode, StaticSensorProvider, Sensorium


class Events:
    def __init__(self):
        self.items = []

    def emit(self, name, **payload):
        self.items.append((name, payload))


def test_sensorium_observes_simulated_screen_fixture():
    events = Events()
    sensorium = Sensorium(events=events)
    sensorium.register(
        StaticSensorProvider(
            "screen-fixture",
            "screen",
            {"fixture": "login-screen.png", "width": 1179, "height": 2556},
        )
    )

    observation = sensorium.observe("screen-fixture")

    assert observation["kind"] == "screen"
    assert observation["mode"] == "simulated"
    assert observation["simulated"] is True
    assert observation["payload"]["fixture"] == "login-screen.png"
    assert [name for name, _ in events.items][-2:] == [
        "sensorium.observation.started",
        "sensorium.observation.completed",
    ]


def test_disabled_provider_fails_closed():
    sensorium = Sensorium()
    provider = StaticSensorProvider("camera-fixture", "camera", {"frame": 1}, mode=ProviderMode.DISABLED)
    sensorium.register(provider)

    with pytest.raises(RuntimeError, match="disabled"):
        sensorium.observe("camera-fixture")


def test_unavailable_provider_is_visible_but_not_observed_by_kind():
    sensorium = Sensorium()
    provider = StaticSensorProvider("mic-fixture", "microphone", {"clip": "hello.wav"}, mode=ProviderMode.UNAVAILABLE)
    sensorium.register(provider)

    assert sensorium.status() == [
        {"name": "mic-fixture", "kind": "microphone", "mode": "unavailable", "state": "unavailable"}
    ]
    assert sensorium.observe_kind("microphone") == []


def test_sensorium_rejects_unknown_sensor_kind():
    sensorium = Sensorium()

    with pytest.raises(ValueError, match="unsupported sensor provider kind"):
        sensorium.register(StaticSensorProvider("mystery", "unknown", {}))
