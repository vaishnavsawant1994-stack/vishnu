"""Governed, schema-bounded execution for owner-approved OpenAPI operations."""
from __future__ import annotations

import ipaddress
import math
import re
import socket
import ssl
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

from integrations.contracts import ConnectorManifest, ConnectorOperation, RetryPolicy
from integrations.gateway import ConnectorGateway, ConnectorError
from integrations.registry import Integration
from tools.registry import Risk, Tool

MAX_RESPONSE_BYTES = 1024 * 1024


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    """Resolve and validate every address that the transport may connect to."""
    try:
        addresses = ({ipaddress.ip_address(host)} if _is_ip(host) else {
            ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        })
    except (OSError, ValueError) as exc:
        raise ValueError("server host could not be verified") from exc
    if not addresses or any(not addr.is_global for addr in addresses):
        raise ValueError("server must resolve only to public IP addresses")
    return tuple(sorted((str(addr) for addr in addresses), key=lambda item: (":" in item, item)))


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
    if not _is_ip(host):
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("invalid server host") from exc
        if len(host) > 253 or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise ValueError("invalid server host")
    _resolve_public_addresses(host)
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
    @staticmethod
    def _pinned_session(address: str):
        """Create a one-request transport pinned to a validated DNS answer.

        The connection still uses the original URL hostname for TLS SNI and
        certificate verification; only the TCP destination is pinned.
        """
        from urllib3.connection import HTTPSConnection
        from urllib3.exceptions import NewConnectionError

        class PinnedHTTPSConnection(HTTPSConnection):
            def _new_conn(self):
                try:
                    return socket.create_connection(
                        (address, self.port), self.timeout, source_address=self.source_address,
                    )
                except OSError as exc:
                    raise NewConnectionError(self, "pinned HTTPS connection failed") from exc

        class PinnedHTTPAdapter(HTTPAdapter):
            def _pin(self, pool):
                pool.ConnectionCls = PinnedHTTPSConnection
                return pool

            def get_connection(self, url, proxies=None):
                if proxies and any(proxies.values()):
                    raise ValueError("proxy routing is disabled for external capabilities")
                return self._pin(super().get_connection(url, proxies=None))

            # requests 2.32+ uses this method from send(); older supported
            # versions use get_connection().
            def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
                parent = getattr(super(), "get_connection_with_tls_context", None)
                if parent is None:
                    return self.get_connection(request.url, proxies=proxies)
                if proxies and any(proxies.values()):
                    raise ValueError("proxy routing is disabled for external capabilities")
                return self._pin(parent(request, verify, proxies=None, cert=cert))

        session = requests.Session()
        session.mount("https://", PinnedHTTPAdapter(max_retries=0))
        return session

    def request(self, method, url, **kwargs):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc.lower() != self.origin or parts.username or parts.password:
            raise ConnectorError("destination_denied", "The operation destination is not approved.", "permission_denied", 403, False)
        normalized_origin = _public_https_url(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
        host = (urlsplit(normalized_origin).hostname or "").rstrip(".").lower()
        # Resolve immediately before opening the socket, then make the socket
        # connect to this exact public IP. This closes the validation/connect
        # DNS-rebinding window while retaining hostname-based TLS validation.
        addresses = _resolve_public_addresses(host)
        prefix = urlsplit(self.base_url).path.rstrip("/")
        if prefix and not (parts.path == prefix or parts.path.startswith(prefix + "/")):
            raise ConnectorError("destination_denied", "The operation path is outside the approved API base path.", "permission_denied", 403, False)
        kwargs["allow_redirects"] = False
        kwargs["stream"] = True
        kwargs["timeout"] = min(max(float(kwargs.get("timeout", 8)), 0.1), 8.0)
        # Test doubles used by the fixture suite intentionally do not expose
        # mount(); production requests sessions always use the pinned adapter.
        if hasattr(self.session, "mount"):
            session = self._pinned_session(addresses[0])
            try:
                # Explicit None entries suppress HTTP(S)_PROXY while retaining
                # platform CA-bundle configuration such as REQUESTS_CA_BUNDLE.
                response = session.request(method, url, proxies={"http": None, "https": None}, **kwargs)
            finally:
                session.close()
        else:
            # Injectable fixture transport; production requests.Session always
            # takes the pinned, environment-independent path above.
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


def _validate_parameters(capability: dict, values: dict) -> tuple[str, dict, dict | None]:
    if not isinstance(values, dict):
        raise ValueError("operation parameters must be an object")
    declared = capability.get("parameters") or []
    by_name = {p["name"]: p for p in declared if isinstance(p, dict) and p.get("in") in {"path", "query"}}
    if set(values) - set(by_name) - {"body"}:
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
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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
    decoded_path = unquote(path)
    parsed_path = urlsplit(path)
    if (re.search(r"\{[^{}]+\}", path) or not path.startswith("/")
            or parsed_path.query or parsed_path.fragment or "\\" in decoded_path
            or any(ord(char) < 32 for char in decoded_path)
            or any(segment in {".", ".."} for segment in decoded_path.split("/"))):
        raise ValueError("operation path has unsupported template parameters")
    body = values.get("body")
    schema = capability.get("request_body")
    if body is not None:
        if not isinstance(schema, dict) or not isinstance(body, dict):
            raise ValueError("operation body is unsupported")
        props = schema.get("properties") or {}
        if set(body) - set(props) or set(schema.get("required") or []) - set(body):
            raise ValueError("operation body does not match its approved schema")
        for key, value in body.items():
            spec = props[key]
            kind = spec.get("type")
            valid = ((kind == "string" and isinstance(value, str) and len(value) <= int(spec.get("max_length", 500)))
                     or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
                     or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))
                     or (kind == "boolean" and isinstance(value, bool)))
            if not valid or ("enum" in spec and value not in spec["enum"]):
                raise ValueError(f"invalid request body field: {key}")
        import json
        if len(json.dumps(body, separators=(",", ":")).encode()) > int(schema.get("max_bytes", 65536)):
            raise ValueError("operation body exceeds the size limit")
    elif schema and schema.get("required"):
        raise ValueError("operation body is required")
    return path, query, body


def attach_approved_capability(capability: dict, connection: dict, *, tools, integrations, vault, state_store, catalog_store=None):
    """Rehydrate one approved catalog entry as a governed operation tool."""
    method = str(capability.get("method", "")).upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} or not connection or connection.get("status") != "connected":
        raise ValueError("unsupported or disconnected API operation")
    read_only = method == "GET" and capability.get("risk") == "read"
    connector_id = connection["connector_id"]
    operation_name = connector_id + (".read" if read_only else "." + method.lower())
    manifest = ConnectorManifest(
        connector_id=connector_id,
        display_name=(capability.get("api_title") or "OpenAPI")[:200],
        provider="openapi",
        schema_version=1,
        authentication_type=connection["auth_type"],
        operations=(ConnectorOperation(operation_name, "read" if read_only else ("destructive" if method == "DELETE" else "write"), "read_only" if read_only else ("destructive" if method == "DELETE" else "external_side_effect"), approval="none" if read_only else "required", requires_reauth=method == "DELETE", retry=RetryPolicy(max_attempts=1), idempotency_supported=False),),
        read_only=read_only,
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

    tool_name = "openapi_" + connector_id.removeprefix("openapi_") + "_" + method.lower()
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
        route, query, body = _validate_parameters(capability, parameters)
        destination = live_connection["server_url"]
        headers = {"Accept": "application/json"}
        credential_ref = live_connection.get("credential_ref")
        if credential_ref:
            token = vault.get(credential_ref)
            if not token:
                raise ConnectorError("authentication_required", "The connector needs to be reconnected.", "authentication_expired", 401, False)
            if live_connection.get("auth_type") == "api_key_header":
                headers["X-API-Key"] = token
            else:
                headers["Authorization"] = "Bearer " + token
        from security.request_context import current_trusted_request
        context = current_trusted_request()
        actor = {"device_id": context.device_id, "session_id": context.session_id} if context else {}
        current.audit("capability.execution.started", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name})
        adapter = type("OpenAPIAdapter", (), {"base_url": destination, "granted_scopes": None})()
        gateway = ConnectorGateway(current, session=_BoundedHTTPSession(destination))
        try:
            result = gateway.request(adapter, manifest.operation(operation_name), method, destination.rstrip("/") + route,
                                     parameters={"capability_id": capability["id"], "query_names": sorted(query), "body": body or {}},
                                     headers=headers, params=query, json_body=body, timeout=8, max_response_bytes=MAX_RESPONSE_BYTES,
                                     destination=destination)
            # A successful HTTP status proves only provider acceptance. It does
            # not prove the provider persisted the intended state.
            current.audit("capability.execution.accepted", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name})
            return result
        except Exception as exc:
            current.audit("capability.execution.failed", connector_id=connector_id, **actor, payload={"capability_id": capability["id"], "operation": operation_name, "error_type": type(exc).__name__})
            raise

    tool = Tool(
        name=tool_name,
        description=f"Read {capability.get('name', 'approved API operation')} from an owner-approved API.",
        handler=handler,
        risk=Risk.READ_ONLY if read_only else (Risk.DESTRUCTIVE if method == "DELETE" else Risk.EXTERNAL_SIDE_EFFECT),
        connector_id=connector_id,
        capability=operation_name,
        input_validator=lambda values: _validate_parameters(capability, values) is not None,
        requires_reauth=method == "DELETE",
        verification_required=False,
        idempotency_supported=False,
    )
    tools.register(tool)
    return tool_name
