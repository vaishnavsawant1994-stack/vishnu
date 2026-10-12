"""Validate MCP server descriptors without starting servers or executing tools."""
from __future__ import annotations

from urllib.parse import urlsplit


def normalize_mcp_server(descriptor: dict) -> dict:
    if not isinstance(descriptor, dict):
        raise ValueError("MCP descriptor must be an object")
    name = descriptor.get("name")
    url = descriptor.get("url")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("MCP server name required")
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("HTTPS MCP endpoint required")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("HTTPS MCP endpoint required")
    except ValueError as exc:
        raise ValueError("HTTPS MCP endpoint required") from exc
    if any(key in descriptor for key in ("command", "args", "env", "headers", "token", "api_key")):
        raise ValueError("Executable commands and secrets cannot be imported from discovery metadata")
    return {"name": name.strip(), "url": url, "transport": "streamable-http", "lifecycle": "discovered", "executable": False, "requires_owner_approval": True}
