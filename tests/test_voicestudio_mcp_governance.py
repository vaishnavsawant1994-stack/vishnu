from __future__ import annotations

from pathlib import Path

import pytest

from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.execution import MAX_RESPONSE_BYTES
from integrations.discovery.mcp import normalize_mcp_server, normalize_trusted_loopback_mcp_server
from integrations.discovery.mcp_runtime import MCPHTTPClient, _BoundedLoopbackSession, attach_approved_mcp_tool
from integrations.gateway import ConnectorError
from integrations.runtime import _discover_configured_voicestudio_mcp
from voice.voicestudio_mcp import (
    apply_voicestudio_tool_policy,
    minimum_voicestudio_risk,
    register_voicestudio_mcp_server,
    risk_meets_minimum,
)


class FakeState:
    def __init__(self, path: Path):
        self.path = path
        self.audits = []

    def audit(self, action, **kwargs):
        self.audits.append((action, kwargs))


class FakeVault:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeResponse:
    def __init__(self, *, status_code=200, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = dict(headers or {})
        self._chunks = list(chunks)
        self._content = b""
        self._content_consumed = False
        self.closed = False

    def iter_content(self, _chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


def test_public_mcp_descriptor_stays_https_only():
    with pytest.raises(ValueError, match="HTTPS MCP endpoint"):
        normalize_mcp_server({"name": "Local", "url": "http://127.0.0.1:3900/mcp"})


def test_trusted_loopback_descriptor_accepts_only_ip_literal_loopback():
    descriptor = normalize_trusted_loopback_mcp_server(
        "VoiceStudio",
        "http://127.0.0.1:3900/mcp/",
        provider="voicestudio",
    )
    assert descriptor["trusted_loopback"] is True
    assert descriptor["provider_policy"] == "voicestudio"
    assert descriptor["url"] == "http://127.0.0.1:3900/mcp"

    with pytest.raises(ValueError, match="loopback"):
        normalize_trusted_loopback_mcp_server(
            "VoiceStudio", "http://192.168.1.10:3900/mcp", provider="voicestudio"
        )
    with pytest.raises(ValueError, match="IP literal"):
        normalize_trusted_loopback_mcp_server(
            "VoiceStudio", "http://localhost:3900/mcp", provider="voicestudio"
        )
    with pytest.raises(ValueError, match="loopback"):
        normalize_trusted_loopback_mcp_server(
            "VoiceStudio", "http://user@127.0.0.1:3900/mcp", provider="voicestudio"
        )
    with pytest.raises(ValueError, match="loopback"):
        normalize_trusted_loopback_mcp_server(
            "VoiceStudio", "http://127.0.0.1:3900/mcp?token=x", provider="voicestudio"
        )


def test_loopback_mcp_transport_ignores_proxy_environment():
    client = MCPHTTPClient("http://127.0.0.1:3900/mcp", allow_loopback=True)
    assert isinstance(client.session, _BoundedLoopbackSession)
    assert client.session.session.trust_env is False


def test_loopback_transport_is_origin_and_path_bound():
    session = _BoundedLoopbackSession("http://127.0.0.1:3900/mcp")

    with pytest.raises(ConnectorError) as wrong_port:
        session.request("POST", "http://127.0.0.1:3901/mcp")
    assert wrong_port.value.code == "destination_denied"

    with pytest.raises(ConnectorError) as wrong_path:
        session.request("POST", "http://127.0.0.1:3900/other")
    assert wrong_path.value.code == "destination_denied"


def test_loopback_transport_blocks_redirects_and_oversize_responses(monkeypatch):
    session = _BoundedLoopbackSession("http://127.0.0.1:3900/mcp")
    redirect = FakeResponse(status_code=302)
    monkeypatch.setattr(session.session, "request", lambda *args, **kwargs: redirect)
    with pytest.raises(ConnectorError) as redirected:
        session.request("POST", "http://127.0.0.1:3900/mcp")
    assert redirected.value.code == "redirect_denied"
    assert redirect.closed is True

    oversized = FakeResponse(
        headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
    )
    monkeypatch.setattr(session.session, "request", lambda *args, **kwargs: oversized)
    with pytest.raises(ConnectorError) as too_large:
        session.request("POST", "http://127.0.0.1:3900/mcp")
    assert too_large.value.code == "content_too_large"
    assert oversized.closed is True


def test_voicestudio_policy_sets_safe_minimum_risks():
    assert minimum_voicestudio_risk("list_voices") == "read"
    assert minimum_voicestudio_risk("describe_voice") == "read"
    assert minimum_voicestudio_risk("clone_voice") == "write"
    assert minimum_voicestudio_risk("design_voice") == "write"
    assert minimum_voicestudio_risk("transcribe") == "write"
    assert minimum_voicestudio_risk("generate_speech") == "write"
    assert minimum_voicestudio_risk("dub_video") == "write"
    assert minimum_voicestudio_risk("unknown_future_tool") == "write"
    assert minimum_voicestudio_risk("delete_voice") == "destructive"

    entry = apply_voicestudio_tool_policy(
        {"name": "clone_voice", "risk": "read", "trusted_loopback": True}
    )
    assert entry["minimum_risk"] == "write"
    assert entry["risk"] == "write"
    assert entry["provider_policy"] == "voicestudio"

    assert risk_meets_minimum("read", "read") is True
    assert risk_meets_minimum("write", "read") is True
    assert risk_meets_minimum("destructive", "write") is True
    assert risk_meets_minimum("read", "write") is False
    assert risk_meets_minimum("write", "destructive") is False


def test_catalog_persists_voicestudio_policy_on_discovered_tools(tmp_path):
    catalog = CapabilityCatalogStore(tmp_path / "catalog.sqlite3")
    server = register_voicestudio_mcp_server(
        catalog, endpoint="http://127.0.0.1:3900/mcp/"
    )
    entries = catalog.import_mcp_tools(
        server["id"],
        [
            {"name": "list_voices", "inputSchema": {"type": "object", "properties": {}}},
            {
                "name": "clone_voice",
                "annotations": {"readOnlyHint": True},
                "inputSchema": {"type": "object", "properties": {}},
            },
        ],
        server_name="VoiceStudio",
        server_url=server["url"],
    )
    by_name = {entry["name"]: entry for entry in entries}
    assert by_name["list_voices"]["minimum_risk"] == "read"
    assert by_name["clone_voice"]["minimum_risk"] == "write"
    assert by_name["clone_voice"]["risk"] == "write"
    assert by_name["clone_voice"]["trusted_loopback"] is True
    persisted = catalog.get(by_name["clone_voice"]["id"])
    assert persisted["provider_policy"] == "voicestudio"
    assert persisted["minimum_risk"] == "write"


def test_provider_minimum_risk_cannot_be_downgraded_during_attachment():
    capability = {
        "id": "mcp:test",
        "type": "mcp_tool",
        "name": "clone_voice",
        "approved_risk": "read",
        "minimum_risk": "write",
    }
    with pytest.raises(ValueError, match="minimum risk"):
        attach_approved_mcp_tool(
            capability,
            {"status": "connected"},
            tools=None,
            integrations=None,
            vault=None,
            catalog_store=None,
        )


def test_configured_voicestudio_registration_is_persistent_and_inert(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "true")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "http://127.0.0.1:3900")

    def must_not_discover(self, *args, **kwargs):
        raise AssertionError("startup must not contact VoiceStudio MCP")

    monkeypatch.setattr(MCPHTTPClient, "list_tools", must_not_discover)
    state = FakeState(tmp_path / "connectors.sqlite3")
    vault = FakeVault({"voicestudio.api_key": "must-not-be-copied"})

    _discover_configured_voicestudio_mcp(object(), state, vault)

    catalog = CapabilityCatalogStore(tmp_path / "capability-catalog.sqlite3")
    servers = catalog.mcp_servers()
    assert len(servers) == 1
    server = servers[0]
    assert server["name"] == "VoiceStudio"
    assert server["trusted_loopback"] is True
    assert server["provider_policy"] == "voicestudio"
    assert catalog.connection(server["id"]) is None
    assert catalog.mcp_tools(server["id"]) == []
    assert vault.values == {"voicestudio.api_key": "must-not-be-copied"}
    assert any(action == "voicestudio.mcp.registered" for action, _ in state.audits)


def test_disabled_voicestudio_does_not_parse_stale_optional_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "false")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "not-a-valid-url")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_TIMEOUT_SECONDS", "not-a-number")
    state = FakeState(tmp_path / "connectors.sqlite3")

    _discover_configured_voicestudio_mcp(object(), state, FakeVault())

    assert state.audits == []
    assert not (tmp_path / "capability-catalog.sqlite3").exists()


def test_invalid_enabled_voicestudio_registration_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "true")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "http://example.com:3900")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ALLOW_REMOTE", "false")
    state = FakeState(tmp_path / "connectors.sqlite3")

    _discover_configured_voicestudio_mcp(object(), state, FakeVault())

    assert any(action == "voicestudio.mcp.registration_failed" for action, _ in state.audits)
    assert not (tmp_path / "capability-catalog.sqlite3").exists()
