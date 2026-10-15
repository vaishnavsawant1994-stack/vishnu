from __future__ import annotations

import json

import httpx
import pytest

from sensorium.iot_adapters import HomeAssistantObservationAdapter


class FakeVault:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


def private_resolver(host: str) -> set[str]:
    assert host == "home.local"
    return {"192.168.50.20"}


def test_home_assistant_adapter_requires_explicit_private_http_and_keeps_token_secret(tmp_path):
    vault = FakeVault()
    adapter = HomeAssistantObservationAdapter(
        tmp_path / "iot-adapters.sqlite3",
        vault=vault,
        resolver=private_resolver,
    )
    with pytest.raises(ValueError, match="HTTP is allowed only"):
        adapter.register(
            label="Home",
            base_url="http://home.local:8123",
            bearer_token="long-lived-access-token",
        )
    saved = adapter.register(
        label="Home",
        base_url="http://home.local:8123",
        bearer_token="long-lived-access-token",
        allow_private_http=True,
        verify_tls=False,
    )
    assert saved["credential_stored"] is True
    assert "long-lived-access-token" not in json.dumps(saved)
    assert adapter.list()[0]["execution_authority"] is False
    assert any(key.startswith("sensorium.iot.home_assistant.") for key in vault.values)


def test_home_assistant_observation_is_exact_host_read_only_and_bounded(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "entity_id": "sensor.living_room_temperature",
                "state": "22.4",
                "attributes": {"unit_of_measurement": "°C", "friendly_name": "Living room"},
                "last_changed": "2026-10-15T12:00:00Z",
                "last_updated": "2026-10-15T12:00:01Z",
            },
        )

    vault = FakeVault()
    adapter = HomeAssistantObservationAdapter(
        tmp_path / "iot-adapters.sqlite3",
        vault=vault,
        resolver=private_resolver,
        transport=httpx.MockTransport(handler),
    )
    row = adapter.register(
        label="Home",
        base_url="http://home.local:8123",
        bearer_token="long-lived-access-token",
        allow_private_http=True,
        verify_tls=False,
    )
    observed = adapter.observe_state(row["adapter_id"], entity_id="sensor.living_room_temperature")
    assert seen["url"] == "http://home.local:8123/api/states/sensor.living_room_temperature"
    assert seen["authorization"] == "Bearer long-lived-access-token"
    assert observed["state"] == "22.4"
    assert observed["execution_authority"] is False
    assert observed["action_supported_here"] is False
    assert observed["credential_exposed"] is False


def test_home_assistant_adapter_rejects_redirects_and_dangerous_dns(tmp_path):
    vault = FakeVault()
    redirecting = HomeAssistantObservationAdapter(
        tmp_path / "redirect.sqlite3",
        vault=vault,
        resolver=private_resolver,
        transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})),
    )
    row = redirecting.register(
        label="Home",
        base_url="http://home.local:8123",
        bearer_token="long-lived-access-token",
        allow_private_http=True,
        verify_tls=False,
    )
    with pytest.raises(RuntimeError, match="redirects are forbidden"):
        redirecting.observe_state(row["adapter_id"], entity_id="sensor.temperature")

    mixed = HomeAssistantObservationAdapter(
        tmp_path / "mixed.sqlite3",
        vault=FakeVault(),
        resolver=lambda host: {"192.168.1.10", "8.8.8.8"},
    )
    with pytest.raises(ValueError, match="mixed public/private"):
        mixed.register(
            label="Mixed",
            base_url="https://mixed.example",
            bearer_token="long-lived-access-token",
        )

    link_local = HomeAssistantObservationAdapter(
        tmp_path / "link-local.sqlite3",
        vault=FakeVault(),
        resolver=lambda host: {"169.254.169.254"},
    )
    with pytest.raises(ValueError, match="forbidden network address"):
        link_local.register(
            label="Metadata",
            base_url="https://metadata.invalid",
            bearer_token="long-lived-access-token",
        )


def test_home_assistant_revoke_disables_transport_and_deletes_credential(tmp_path):
    vault = FakeVault()
    adapter = HomeAssistantObservationAdapter(
        tmp_path / "iot-adapters.sqlite3",
        vault=vault,
        resolver=private_resolver,
    )
    row = adapter.register(
        label="Home",
        base_url="http://home.local:8123",
        bearer_token="long-lived-access-token",
        allow_private_http=True,
        verify_tls=False,
    )
    assert adapter.revoke(row["adapter_id"]) is True
    assert not vault.values
    with pytest.raises(PermissionError):
        adapter.observe_state(row["adapter_id"], entity_id="sensor.temperature")
