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
            identity = hashlib.sha256((source_identity + "\n" + method.upper() + " " + path).encode()).hexdigest()[:24]
            result.append({"id": "openapi:" + identity, "name": str(operation.get("summary") or operation_name or method.upper() + " " + path)[:200], "operation_id": operation_name, "method": method.upper(), "path": path, "description": str(operation.get("description") or "")[:1000], "source_url": origin, "api_title": str(info.get("title") or "")[:200], "api_version": str(info.get("version") or "")[:80], "risk": "read" if method.lower() in {"get", "head", "options"} else "write", "lifecycle": "discovered", "executable": False})
            if len(result) >= max_operations:
                return result
    return result
