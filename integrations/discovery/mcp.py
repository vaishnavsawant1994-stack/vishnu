"""Validate MCP server descriptors without starting servers or executing tools."""
from __future__ import annotations

import hashlib
import json
import math
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
    if any(key in descriptor for key in ("command", "args", "env", "headers", "token", "api_key", "authorization")):
        raise ValueError("Executable commands and secrets cannot be imported from discovery metadata")
    endpoint = url.strip().rstrip("/")
    identity = hashlib.sha256((name.strip().casefold() + "\n" + endpoint.casefold()).encode()).hexdigest()[:24]
    return {"id": "mcp_server:" + identity, "type": "mcp_server", "name": name.strip(), "url": endpoint, "transport": "streamable-http", "lifecycle": "discovered", "executable": False, "requires_owner_approval": True}


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
    return {"id": "mcp:" + identity, "type": "mcp_tool", "server_id": server_id,
            "name": name, "description": description, "input_schema": schema,
            "transport": "streamable-http", "risk": "owner_attested_read",
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
