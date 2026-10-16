from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from integrations.discovery.mcp import normalize_mcp_server, normalize_trusted_loopback_mcp_server

_PROVIDER_POLICY = "voicestudio"
_RISK_ORDER = {"read": 0, "write": 1, "destructive": 2}
_DESTRUCTIVE_PREFIXES = ("delete", "remove", "revoke", "drop", "purge", "reset", "disable")
_READ_PREFIXES = ("list", "get", "status", "health", "describe", "inspect", "languages", "models", "voices")


def register_voicestudio_mcp_server(catalog, provider=None, *, endpoint: str | None = None) -> dict | None:
    """Persist the configured VoiceStudio MCP endpoint as inert catalog metadata."""
    if endpoint is None:
        if provider is None:
            return None
        endpoint = str(provider.mcp_endpoint)
    endpoint = str(endpoint).rstrip("/")
    parts = urlsplit(endpoint)
    trusted_loopback = False
    try:
        trusted_loopback = ipaddress.ip_address(parts.hostname or "").is_loopback
    except ValueError:
        trusted_loopback = False
    if trusted_loopback:
        descriptor = normalize_trusted_loopback_mcp_server(
            "VoiceStudio",
            endpoint,
            provider=_PROVIDER_POLICY,
        )
    else:
        descriptor = normalize_mcp_server({"name": "VoiceStudio", "url": endpoint})
        descriptor["provider_policy"] = _PROVIDER_POLICY
    catalog.import_mcp_server(descriptor)
    return descriptor


def minimum_voicestudio_risk(tool_name: str) -> str:
    """Return the minimum owner-approval classification for a VoiceStudio MCP tool."""
    normalized = str(tool_name or "").strip().lower().replace("-", "_")
    if not normalized:
        return "write"
    if normalized.startswith(_DESTRUCTIVE_PREFIXES):
        return "destructive"
    if normalized.startswith(_READ_PREFIXES):
        return "read"
    return "write"


def apply_voicestudio_tool_policy(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("VoiceStudio MCP tool entry must be an object")
    minimum = minimum_voicestudio_risk(entry.get("name", ""))
    current = entry.get("risk") if entry.get("risk") in _RISK_ORDER else "write"
    effective = current if _RISK_ORDER[current] >= _RISK_ORDER[minimum] else minimum
    return {
        **entry,
        "provider_policy": _PROVIDER_POLICY,
        "minimum_risk": minimum,
        "risk": effective,
        "trusted_loopback": bool(entry.get("trusted_loopback")),
    }


def risk_meets_minimum(requested: str, minimum: str | None) -> bool:
    if requested not in _RISK_ORDER:
        return False
    if minimum not in _RISK_ORDER:
        return True
    return _RISK_ORDER[requested] >= _RISK_ORDER[minimum]
