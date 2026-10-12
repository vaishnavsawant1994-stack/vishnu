"""Offline OpenAPI 3 discovery normalization; does not make network requests."""
from __future__ import annotations

import hashlib
from urllib.parse import urlsplit


def parse_openapi(document: dict, *, max_operations: int = 500) -> list[dict]:
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI paths object required")
    if not str(document.get("openapi", "")).startswith("3."):
        raise ValueError("OpenAPI 3 required")
    if not 1 <= max_operations <= 1000:
        raise ValueError("invalid operation limit")
    paths = document["paths"]
    if len(paths) > 2000:
        raise ValueError("too many paths")
    result = []
    for path, operations in sorted(paths.items()):
        if not isinstance(path, str) or not path.startswith("/") or len(path) > 500 or not isinstance(operations, dict):
            continue
        for method, operation in sorted(operations.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"} or not isinstance(operation, dict):
                continue
            identity = hashlib.sha256((method.upper() + " " + path).encode()).hexdigest()[:24]
            result.append({"id": "openapi:" + identity, "name": str(operation.get("summary") or operation.get("operationId") or method.upper() + " " + path)[:200], "method": method.upper(), "path": path, "description": str(operation.get("description") or "")[:1000], "risk": "read" if method.lower() in {"get", "head", "options"} else "write", "lifecycle": "discovered", "executable": False})
            if len(result) >= max_operations:
                return result
    return result
