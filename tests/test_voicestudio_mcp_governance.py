from __future__ import annotations

from pathlib import Path

import pytest

from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.mcp import normalize_mcp_server, normalize_trusted_loopback_mcp_server
from integrations.discovery.mcp_runtime import MCPHTTPClient, _BoundedLoopbackSession, attach_approved_mcp_tool
from integrations.runtime import _discover_configured_voicestudio_mcp
from voice.voicestudio_mcp import (
    apply_voicestudio_tool_policy,
    minimum_voicestudio_risk,
    register_voicestudio_mcp_server,
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


def test_loopback_mcp_transport_ignores_proxy_environment():
    client = MCPHTTPClient("http://127.0.0.1:3900/mcp", allow_loopback=True)
    assert isinstance(client.session, _BoundedLoopbackSession)
    assert client.session.session.trust_env is False


def test_voicestudio_policy_sets_safe_minimum_risks():
    assert minimum_voicestudio_risk("list_voices") == "read"
    assert minimum_voicestudio_risk("describe_voice") == "read"
    assert minimum_voicestudio_risk("clone_voice") == "write"
    assert minimum_voicestudio_risk("design_voice") == "write"
    assert minimum_voicestudio_risk("transcribe") == "write"
    assert minimum_voicestudio_risk("generate_speech") == "write"
    assert minimum_voicestudio_risk("delete_voice") == "destructive"

    entry = apply_voicestudio_tool_policy(
        {"name": "clone_voice", "risk": "read", "trusted_loopback": True}
    )
    assert entry["minimum_risk"] == "write"
    assert entry["risk"] == "write"
    assert entry["provider_policy"] == "voicestudio"


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
    assert catalog.get(by_name["clone_voice"]["id"])["provider_policy"] == "voicestudio"


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


def test_configured_voicestudio_metadata_discovery_is_persistent_and_non_authorizing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "true")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "http://127.0.0.1:3900")
    remote_tools = [
        {"name": "list_voices", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "clone_voice", "inputSchema": {"type": "object", "properties": {}}},
    ]
    monkeypatch.setattr(MCPHTTPClient, "list_tools", lambda self: remote_tools)
    state = FakeState(tmp_path / "connectors.sqlite3")

    _discover_configured_voicestudio_mcp(object(), state, FakeVault())

    catalog = CapabilityCatalogStore(tmp_path / "capability-catalog.sqlite3")
    servers = catalog.mcp_servers()
    assert len(servers) == 1
    server = servers[0]
    assert server["name"] == "VoiceStudio"
    assert catalog.connection(server["id"])["status"] == "connected"
    tools = catalog.mcp_tools(server["id"])
    assert {tool["name"] for tool in tools} == {"list_voices", "clone_voice"}
    assert all(tool.get("approved_risk") is None for tool in tools)
    assert any(action == "voicestudio.mcp.discovered" for action, _ in state.audits)


def test_configured_voicestudio_discovery_failure_is_fail_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "true")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "http://127.0.0.1:3900")

    def fail(self):
        raise RuntimeError("offline")

    monkeypatch.setattr(MCPHTTPClient, "list_tools", fail)
    state = FakeState(tmp_path / "connectors.sqlite3")

    _discover_configured_voicestudio_mcp(object(), state, FakeVault())

    catalog = CapabilityCatalogStore(tmp_path / "capability-catalog.sqlite3")
    assert len(catalog.mcp_servers()) == 1
    assert catalog.mcp_tools(catalog.mcp_servers()[0]["id"]) == []
    assert any(action == "voicestudio.mcp.discovery_deferred" for action, _ in state.audits)
