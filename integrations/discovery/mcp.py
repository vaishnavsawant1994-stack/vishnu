"""Validate MCP server descriptors without starting servers or executing tools."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
from urllib.parse import urlsplit, urlunsplit


def _server_identity(name: str, endpoint: str) -> str:
    return hashlib.sha256((name.strip().casefold() + "\n" + endpoint.casefold()).encode()).hexdigest()[:24]


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
    if any(key in descriptor for key in ("command", "args", "env", "headers", "token", "api_key", "authorization")):
        raise ValueError("Executable commands and secrets cannot be imported from discovery metadata")
    endpoint = url.strip().rstrip("/")
    identity = _server_identity(name, endpoint)
    return {"id": "mcp_server:" + identity, "type": "mcp_server", "name": name.strip(), "url": endpoint, "transport": "streamable-http", "lifecycle": "discovered", "executable": False, "requires_owner_approval": True}


def normalize_trusted_loopback_mcp_server(name: str, url: str, *, provider: str) -> dict:
    """Normalize an internally configured loopback MCP endpoint.

    Public/user-supplied MCP descriptors remain HTTPS-only. This separate path is
    only for a provider that Vishnu itself already configured and whose endpoint
    is an IP-literal loopback origin. It never accepts secrets or executable
    command metadata.
    """
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("MCP server name required")
    if not isinstance(provider, str) or not 1 <= len(provider) <= 64:
        raise ValueError("trusted MCP provider id required")
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("loopback MCP endpoint required")
    try:
        parsed = urlsplit(url.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("loopback MCP endpoint required") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("loopback MCP endpoint required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("trusted loopback MCP endpoint must use an IP literal") from exc
    if not address.is_loopback:
        raise ValueError("trusted MCP endpoint must be loopback-only")
    if port is not None and not 1 <= int(port) <= 65535:
        raise ValueError("invalid loopback MCP port")
    normalized_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    netloc = normalized_host if port is None else f"{normalized_host}:{port}"
    path = parsed.path.rstrip("/") or "/mcp"
    endpoint = urlunsplit((parsed.scheme, netloc, path, "", ""))
    identity = _server_identity(name, endpoint)
    return {
        "id": "mcp_server:" + identity,
        "type": "mcp_server",
        "name": name.strip(),
        "url": endpoint,
        "transport": "streamable-http",
        "lifecycle": "discovered",
        "executable": False,
        "requires_owner_approval": True,
        "trusted_loopback": True,
        "provider_policy": provider,
    }


def normalize_mcp_tool(server_id: str, raw: dict) -> dict:
    """Persist a bounded MCP tool descriptor without granting execution."""
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        raise ValueError("MCP tool name required")
    name = raw["name"].strip()
    if not 1 <= len(name) <= 128:
        raise ValueError("MCP tool name is invalid")
    schema = _safe_schema(raw.get("inputSchema") or {"type": "object", "properties": {}})
    desc = raw.get("description", "")
    description = desc[:1000] if isinstance(desc, str) else ""
    identity = hashlib.sha256((server_id + "\n" + name).encode()).hexdigest()[:24]
    annotations = raw.get("annotations") if isinstance(raw.get("annotations"), dict) else {}
    read_only = annotations.get("readOnlyHint") is True
    destructive = annotations.get("destructiveHint") is True
    return {"id": "mcp:" + identity, "type": "mcp_tool", "server_id": server_id,
            "name": name, "description": description, "input_schema": schema,
            "annotations": {"read_only": read_only, "destructive": destructive,
                            "idempotent": annotations.get("idempotentHint") is True},
            "transport": "streamable-http", "risk": "read" if read_only else ("destructive" if destructive else "write"),
            "lifecycle": "discovered", "executable": False}


def _safe_schema(schema: dict, *, depth: int = 0) -> dict:
    if not isinstance(schema, dict) or depth > 10 or len(json.dumps(schema, default=str)) > 50_000:
        raise ValueError("MCP tool input schema is invalid or too large")
    if "$ref" in schema or "oneOf" in schema or "anyOf" in schema or "allOf" in schema:
        raise ValueError("MCP tool schema uses unsupported references or unions")
    allowed_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
    kind = schema.get("type", "object")
    if kind not in allowed_types:
        raise ValueError("MCP tool schema has an unsupported type")
    out = {"type": kind}
    if kind == "object":
        props = schema.get("properties", {})
        if not isinstance(props, dict) or len(props) > 100:
            raise ValueError("MCP tool schema has too many properties")
        out["properties"] = {str(key)[:128]: _safe_schema(child, depth=depth + 1) for key, child in props.items() if isinstance(key, str) and key}
        required = schema.get("required", [])
        if not isinstance(required, list) or len(required) > 100 or any(not isinstance(item, str) or item not in out["properties"] for item in required):
            raise ValueError("MCP tool schema has invalid required fields")
        out["required"] = required
        out["additionalProperties"] = schema.get("additionalProperties") is not False
    if kind == "array" and isinstance(schema.get("items"), dict):
        out["items"] = _safe_schema(schema["items"], depth=depth + 1)
    if isinstance(schema.get("enum"), list) and len(schema["enum"]) <= 100:
        out["enum"] = [value for value in schema["enum"] if value is None or isinstance(value, (str, int, float, bool)) and (not isinstance(value, float) or math.isfinite(value))]
    for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
        value = schema.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value)):
            out[key] = value
    return out
