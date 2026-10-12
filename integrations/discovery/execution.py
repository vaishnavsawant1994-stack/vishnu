"""Governed, read-only execution for owner-approved OpenAPI GET operations."""
from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import requests

from integrations.contracts import ConnectorManifest, ConnectorOperation, RetryPolicy
from integrations.gateway import ConnectorGateway, ConnectorError
from integrations.registry import Integration
from tools.registry import Risk, Tool

MAX_RESPONSE_BYTES = 1024 * 1024


def _public_https_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("HTTPS server URL required")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("HTTPS server URL required")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("invalid server URL") from exc
    if port not in (None, 443):
        raise ValueError("only the standard HTTPS port is supported")
    host = parts.hostname.rstrip(".").lower()
    try:
        addresses = {ipaddress.ip_address(host)} if _is_ip(host) else {
            ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise ValueError("server host could not be verified") from exc
    if not addresses or any(not addr.is_global for addr in addresses):
        raise ValueError("server must resolve only to public IP addresses")
    netloc = f"[{host}]" if ":" in host else host
    path = parts.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _BoundedHTTPSession:
    """An origin-bound, no-redirect HTTPS session with a response size cap."""
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.origin = urlsplit(base_url).netloc.lower()
        self.session = requests.Session()

    def request(self, method, url, **kwargs):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc.lower() != self.origin or parts.username or parts.password:
            raise ConnectorError("destination_denied", "The operation destination is not approved.", "permission_denied", 403, False)
        _public_https_url(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
        prefix = urlsplit(self.base_url).path.rstrip("/")
        if prefix and not (parts.path == prefix or parts.path.startswith(prefix + "/")):
            raise ConnectorError("destination_denied", "The operation path is outside the approved API base path.", "permission_denied", 403, False)
        kwargs["allow_redirects"] = False
        kwargs["stream"] = True
        kwargs["timeout"] = min(max(float(kwargs.get("timeout", 8)), 0.1), 8.0)
        response = self.session.request(method, url, **kwargs)
        try:
            if 300 <= int(response.status_code) < 400:
                raise ConnectorError("redirect_denied", "API redirects are disabled for this connector.", "permission_denied", 502, False)
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_RESPONSE_BYTES:
                raise ConnectorError("content_too_large", "The API response exceeds the size limit.", "degraded", 413, False)
            content = bytearray()
            for chunk in response.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ConnectorError("content_too_large", "The API response exceeds the size limit.", "degraded", 413, False)
            response._content = bytes(content)
            response._content_consumed = True
            return response
        except Exception:
            response.close()
            raise


def _validate_parameters(capability: dict, values: dict) -> tuple[str, dict]:
    if not isinstance(values, dict):
        raise ValueError("operation parameters must be an object")
    declared = capability.get("parameters") or []
    by_name = {p["name"]: p for p in declared if isinstance(p, dict) and p.get("in") in {"path", "query"}}
    if set(values) - set(by_name):
        raise ValueError("operation contains an undeclared parameter")
    path = capability["path"]
    query = {}
    for name, spec in by_name.items():
        value = values.get(name)
        if value is None:
            if spec.get("required"):
                raise ValueError(f"missing required parameter: {name}")
            continue
        kind = spec.get("type", "string")
        if kind == "string":
            if not isinstance(value, str) or len(value) > int(spec.get("max_length", 500)):
                raise ValueError(f"invalid parameter: {name}")
            normalized = value
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"invalid parameter: {name}")
            normalized = value
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"invalid parameter: {name}")
            normalized = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"invalid parameter: {name}")
            normalized = value
        else:
            raise ValueError(f"unsupported parameter: {name}")
        if "enum" in spec and normalized not in spec["enum"]:
            raise ValueError(f"invalid parameter: {name}")
        if spec["in"] == "path":
            path = path.replace("{" + name + "}", quote(str(normalized), safe=""))
        else:
            query[name] = normalized
    if re.search(r"\{[^{}]+\}", path) or not path.startswith("/") or ".." in path.split("/"):
        raise ValueError("operation path has unsupported template parameters")
    return path, query


def attach_approved_capability(capability: dict, connection: dict, *, tools, integrations, vault, state_store, catalog_store=None):
    """Rehydrate an approved catalog entry as one governed read-only tool."""
    if capability.get("method") != "GET" or capability.get("risk") != "read" or not connection or connection.get("status") != "connected":
        raise ValueError("only connected read-only GET operations can be registered")
    connector_id = connection["connector_id"]
    operation_name = connector_id + ".read"
    manifest = ConnectorManifest(
        connector_id=connector_id,
        display_name=(capability.get("api_title") or "OpenAPI")[:200],
        provider="openapi",
        schema_version=1,
        authentication_type=connection["auth_type"],
        operations=(ConnectorOperation(operation_name, "read", "read_only", approval="none", retry=RetryPolicy(max_attempts=1)),),
        read_only=True,
        content_limits=(("response_bytes", MAX_RESPONSE_BYTES),),
    ).validate()
    try:
        integrations.manifests.get(connector_id)
    except KeyError:
        integrations.register_manifest(manifest)
    try:
        integration = integrations.get(connector_id)
        integration.configured = True
    except KeyError:
        integrations.register(Integration(connector_id, manifest.display_name, {operation_name}, manifest=manifest, configured=True))

    tool_name = "openapi_" + connector_id.removeprefix("openapi_") + "_get"
    existing_tool = next((tool for tool in tools.all() if tool.name == tool_name), None)
    if existing_tool is not None:
        existing_tool.prohibited = False
        return tool_name

    def handler(parameters):
        current = integrations.state_store
        if current is None:
            raise ConnectorError("connector_unavailable", "The connector service is unavailable.", "degraded", 503, False)
        live_connection = catalog_store.connection(capability["id"], include_credential_ref=True) if catalog_store is not None else connection
        if not live_connection or live_connection.get("status") != "connected":
            raise ConnectorError("capability_revoked", "This API capability is no longer connected.", "permission_denied", 403, False)
        route, query = _validate_parameters(capability, parameters)
        destination = live_connection["server_url"]
        headers = {"Accept": "application/json"}
        credential_ref = live_connection.get("credential_ref")
        if credential_ref:
            token = vault.get(credential_ref)
            if not token:
                raise ConnectorError("authentication_required", "The connector needs to be reconnected.", "authentication_expired", 401, False)
            headers["Authorization"] = "Bearer " + token
        from security.request_context import current_trusted_request
        context = current_trusted_request()
        actor = {"device_id": context.device_id, "session_id": context.session_id} if context else {}
        current.audit("capability.execution.started", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name})
        adapter = type("OpenAPIAdapter", (), {"base_url": destination, "granted_scopes": None})()
        gateway = ConnectorGateway(current, session=_BoundedHTTPSession(destination))
        try:
            result = gateway.request(adapter, manifest.operation(operation_name), "GET", destination.rstrip("/") + route,
                                     parameters={"capability_id": capability["id"], "query_names": sorted(query)},
                                     headers=headers, params=query, timeout=8, max_response_bytes=MAX_RESPONSE_BYTES,
                                     destination=destination)
            current.audit("capability.execution.succeeded", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name})
            return result
        except Exception as exc:
            current.audit("capability.execution.failed", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name, "error_type": type(exc).__name__})
            raise

    tool = Tool(
        name=tool_name,
        description=f"Read {capability.get('name', 'approved API operation')} from an owner-approved API.",
        handler=handler,
        risk=Risk.READ_ONLY,
        connector_id=connector_id,
        capability=operation_name,
        input_validator=lambda values: _validate_parameters(capability, values) is not None,
    )
    tools.register(tool)
    return tool_name
