"""Offline OpenAPI 3 discovery normalization; does not make network requests."""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit, urlunsplit


def _https_server_url(value: object) -> str | None:
    """Return a normalized HTTPS URL without credentials, query, or fragments.

    This is discovery metadata validation only. Runtime execution must still
    apply its own destination policy before making a request.
    """
    if not isinstance(value, str) or len(value) > 2048 or "{" in value or "}" in value:
        return None
    try:
        parts = urlsplit(value.strip())
        if (parts.scheme.lower() != "https" or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment):
            return None
        _ = parts.port
    except ValueError:
        return None
    return value.strip().rstrip("/")


def parse_openapi(document: dict, *, max_operations: int = 500, source_url: str | None = None) -> list[dict]:
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI paths object required")
    if not str(document.get("openapi", "")).startswith("3."):
        raise ValueError("OpenAPI 3 required")
    if not 1 <= max_operations <= 1000:
        raise ValueError("invalid operation limit")
    paths = document["paths"]
    info = document.get("info") if isinstance(document.get("info"), dict) else {}
    servers = document.get("servers") if isinstance(document.get("servers"), list) else []
    server_urls = [
        normalized for server in servers if isinstance(server, dict)
        if (normalized := _https_server_url(server.get("url"))) is not None
    ]
    origin = _https_server_url(source_url) or (server_urls[0] if server_urls else None)
    if origin:
        parts = urlsplit(origin)
        normalized_origin = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
        source_identity = "server:" + normalized_origin
    else:
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        source_identity = "spec:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if len(paths) > 2000:
        raise ValueError("too many paths")
    result = []
    for path, operations in sorted(paths.items(), key=lambda item: str(item[0])):
        if not isinstance(path, str) or not path.startswith("/") or len(path) > 500 or not isinstance(operations, dict):
            continue
        for method, operation in sorted(operations.items(), key=lambda item: str(item[0])):
            if not isinstance(method, str) or method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"} or not isinstance(operation, dict):
                continue
            operation_name = str(operation.get("operationId") or "")[:200]
            # Normalize a deliberately small JSON request schema. References,
            # composition keywords, nested objects, and unbounded arrays remain
            # discovery-only and are never sent to a provider.
            parameters = []
            raw_parameters = [
                *(operations.get("parameters", []) if isinstance(operations.get("parameters", []), list) else []),
                *(operation.get("parameters", []) if isinstance(operation.get("parameters", []), list) else []),
            ]
            for parameter in raw_parameters[:100]:
                if not isinstance(parameter, dict) or parameter.get("in") not in {"path", "query"}:
                    continue
                name = parameter.get("name")
                schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {}
                kind = schema.get("type", "string")
                if not isinstance(name, str) or not name or len(name) > 100 or kind not in {"string", "integer", "number", "boolean"}:
                    continue
                item = {"name": name, "in": parameter["in"], "type": kind, "required": bool(parameter.get("required")) or parameter["in"] == "path"}
                if isinstance(schema.get("enum"), list) and len(schema["enum"]) <= 50:
                    item["enum"] = [v for v in schema["enum"] if isinstance(v, (str, int, float, bool))][:50]
                if kind == "string":
                    item["max_length"] = max(1, min(int(schema.get("maxLength", 500)) if isinstance(schema.get("maxLength", 500), int) else 500, 2000))
                parameters.append(item)
            body_schema = None
            request_body = operation.get("requestBody")
            content = request_body.get("content") if isinstance(request_body, dict) else None
            json_content = content.get("application/json") if isinstance(content, dict) else None
            raw_schema = json_content.get("schema") if isinstance(json_content, dict) else None
            if isinstance(raw_schema, dict) and not any(key in raw_schema for key in ("$ref", "allOf", "oneOf", "anyOf", "not")):
                properties = raw_schema.get("properties")
                required = raw_schema.get("required", [])
                normalized_properties = {}
                if isinstance(properties, dict) and len(properties) <= 32 and isinstance(required, list):
                    for prop_name, prop_schema in properties.items():
                        if (not isinstance(prop_name, str) or not prop_name or len(prop_name) > 100
                                or not isinstance(prop_schema, dict) or any(k in prop_schema for k in ("$ref", "allOf", "oneOf", "anyOf", "not"))):
                            continue
                        prop_type = prop_schema.get("type")
                        if prop_type not in {"string", "integer", "number", "boolean"}:
                            continue
                        item = {"type": prop_type}
                        if prop_type == "string":
                            item["max_length"] = max(1, min(prop_schema.get("maxLength", 500) if isinstance(prop_schema.get("maxLength", 500), int) else 500, 2000))
                        if isinstance(prop_schema.get("enum"), list) and len(prop_schema["enum"]) <= 50:
                            item["enum"] = [v for v in prop_schema["enum"] if isinstance(v, (str, int, float, bool))][:50]
                        normalized_properties[prop_name] = item
                    body_schema = {"required": [name for name in required if name in normalized_properties][:32],
                                   "properties": normalized_properties, "max_bytes": 65536}
            identity = hashlib.sha256((source_identity + "\n" + method.upper() + " " + path).encode()).hexdigest()[:24]
            result.append({"id": "openapi:" + identity, "name": str(operation.get("summary") or operation_name or method.upper() + " " + path)[:200], "operation_id": operation_name, "method": method.upper(), "path": path, "parameters": parameters, "request_body": body_schema, "description": str(operation.get("description") or "")[:1000], "source_url": origin, "api_title": str(info.get("title") or "")[:200], "api_version": str(info.get("version") or "")[:80], "risk": "read" if method.lower() in {"get", "head", "options"} else "write", "lifecycle": "discovered", "executable": False})
            if len(result) >= max_operations:
                return result
    return result
