"""Bounded MCP Streamable HTTP client for owner-approved tools."""
from __future__ import annotations

import ipaddress
import json
import math
from urllib.parse import urlsplit

import requests

from integrations.discovery.execution import MAX_RESPONSE_BYTES, _BoundedHTTPSession
from integrations.contracts import ConnectorManifest, ConnectorOperation, RetryPolicy
from integrations.gateway import ConnectorError
from integrations.registry import Integration
from tools.contracts import validate_contract
from tools.registry import Risk, Tool


class MCPProtocolError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.safe_message = message


class _BoundedLoopbackSession:
    """Origin-bound MCP transport for an internally trusted loopback provider.

    This transport is deliberately separate from the public HTTPS transport. It
    accepts only IP-literal loopback origins, ignores proxy environment variables,
    blocks redirects and keeps the same response-size cap used by external MCP.
    """

    def __init__(self, base_url: str):
        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("loopback MCP endpoint required")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError as exc:
            raise ValueError("loopback MCP endpoint must use an IP literal") from exc
        if not address.is_loopback:
            raise ValueError("loopback MCP endpoint required")
        self.base_url = base_url
        self.origin = parts.netloc.lower()
        self.prefix = parts.path.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False

    def request(self, method, url, **kwargs):
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or parts.netloc.lower() != self.origin
            or parts.username
            or parts.password
        ):
            raise ConnectorError(
                "destination_denied",
                "The operation destination is not approved.",
                "permission_denied",
                403,
                False,
            )
        try:
            address = ipaddress.ip_address(parts.hostname or "")
        except ValueError as exc:
            raise ConnectorError(
                "destination_denied",
                "The operation destination is not approved.",
                "permission_denied",
                403,
                False,
            ) from exc
        if not address.is_loopback:
            raise ConnectorError(
                "destination_denied",
                "The operation destination is not approved.",
                "permission_denied",
                403,
                False,
            )
        if self.prefix and not (parts.path == self.prefix or parts.path.startswith(self.prefix + "/")):
            raise ConnectorError(
                "destination_denied",
                "The operation path is outside the approved MCP base path.",
                "permission_denied",
                403,
                False,
            )
        kwargs["allow_redirects"] = False
        kwargs["stream"] = True
        kwargs["timeout"] = min(max(float(kwargs.get("timeout", 8)), 0.1), 8.0)
        response = self.session.request(method, url, **kwargs)
        try:
            if 300 <= int(response.status_code) < 400:
                raise ConnectorError(
                    "redirect_denied",
                    "MCP redirects are disabled for this connector.",
                    "permission_denied",
                    502,
                    False,
                )
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_RESPONSE_BYTES:
                raise ConnectorError(
                    "content_too_large",
                    "The MCP response exceeds the size limit.",
                    "degraded",
                    413,
                    False,
                )
            content = bytearray()
            for chunk in response.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ConnectorError(
                        "content_too_large",
                        "The MCP response exceeds the size limit.",
                        "degraded",
                        413,
                        False,
                    )
            response._content = bytes(content)
            response._content_consumed = True
            return response
        except Exception:
            response.close()
            raise


class MCPHTTPClient:
    PROTOCOL_VERSION = "2025-11-25"
    ACCEPT = "application/json, text/event-stream"

    def __init__(
        self,
        endpoint: str,
        bearer_token: str | None = None,
        *,
        timeout: float = 8,
        auth_type: str = "bearer_token",
        allow_loopback: bool = False,
    ):
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.auth_type = auth_type
        self.timeout = min(max(float(timeout), 0.1), 8.0)
        self.session = _BoundedLoopbackSession(endpoint) if allow_loopback else _BoundedHTTPSession(endpoint)
        self.session_id: str | None = None
        self.protocol_version = self.PROTOCOL_VERSION
        self._next_id = 1
        self._initialized = False

    def _headers(self):
        headers = {"Accept": self.ACCEPT, "Content-Type": "application/json"}
        if self.bearer_token:
            if self.auth_type == "api_key_header":
                headers["X-API-Key"] = self.bearer_token
            else:
                headers["Authorization"] = "Bearer " + self.bearer_token
        if self._initialized:
            headers["MCP-Protocol-Version"] = self.protocol_version
            if self.session_id:
                headers["MCP-Session-Id"] = self.session_id
        return headers

    def _post(self, message):
        response = self.session.request("POST", self.endpoint, headers=self._headers(), json=message, timeout=self.timeout)
        if response.status_code >= 400:
            raise MCPProtocolError("http_error", f"MCP server returned HTTP {int(response.status_code)}")
        media_type = str(response.headers.get("Content-Type", "application/json")).split(";", 1)[0].strip().lower()
        if response.headers.get("MCP-Session-Id"):
            session_id = str(response.headers["MCP-Session-Id"])
            if len(session_id) > 512 or any(ord(c) < 0x21 or ord(c) > 0x7e for c in session_id):
                raise MCPProtocolError("invalid_session", "MCP server returned an invalid session identifier")
            self.session_id = session_id
        if not response.content:
            if response.status_code == 202:
                return None
            raise MCPProtocolError("empty_response", "MCP server returned an empty response")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise MCPProtocolError("response_too_large", "MCP response exceeds the size limit")
        if media_type == "application/json":
            try:
                payload = response.json()
            except Exception as exc:
                raise MCPProtocolError("invalid_json", "MCP server returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise MCPProtocolError("invalid_message", "MCP server returned an invalid JSON-RPC message")
            return payload
        if media_type == "text/event-stream":
            for line in response.content.decode("utf-8", errors="replace").splitlines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict) and payload.get("id") == message.get("id"):
                    return payload
            raise MCPProtocolError("missing_response", "MCP event stream did not contain the requested response")
        raise MCPProtocolError("unsupported_content_type", "MCP server returned an unsupported response type")

    def _rpc(self, method: str, params: dict | None = None):
        request_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        response = self._post(message)
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
            raise MCPProtocolError("invalid_response", "MCP server returned a mismatched JSON-RPC response")
        if "error" in response:
            error = response.get("error")
            code = str(error.get("code", "rpc_error")) if isinstance(error, dict) else "rpc_error"
            raise MCPProtocolError(code[:64], "MCP server rejected the request")
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPProtocolError("invalid_result", "MCP server returned an invalid result")
        return result

    def initialize(self):
        result = self._rpc("initialize", {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Vishnu", "version": "0.6.0"},
        })
        version = result.get("protocolVersion")
        if version not in {"2025-11-25", "2025-06-18", "2025-03-26"}:
            raise MCPProtocolError("unsupported_protocol", "MCP server selected an unsupported protocol version")
        self.protocol_version = version
        self._initialized = True
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._post(notification)

    def list_tools(self, *, max_pages: int = 20, max_tools: int = 500):
        if not self._initialized:
            self.initialize()
        tools = []
        cursor = None
        seen = set()
        for _ in range(max_pages):
            params = {"cursor": cursor} if cursor else {}
            result = self._rpc("tools/list", params)
            batch = result.get("tools")
            if not isinstance(batch, list):
                raise MCPProtocolError("invalid_tool_list", "MCP server returned an invalid tool list")
            tools.extend(batch[:max_tools - len(tools)])
            if len(tools) >= max_tools:
                return tools
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
            cursor = str(cursor)
            if len(cursor) > 2048 or cursor in seen:
                raise MCPProtocolError("invalid_cursor", "MCP server returned an invalid pagination cursor")
            seen.add(cursor)
        raise MCPProtocolError("too_many_pages", "MCP tool list exceeds the pagination limit")

    def call_tool(self, name: str, arguments: dict):
        if not self._initialized:
            self.initialize()
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


def _json_safe(value, *, depth=0):
    if depth > 16:
        raise ValueError("MCP arguments exceed the nesting limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("MCP arguments must use finite numbers")
    if isinstance(value, dict):
        if len(value) > 500:
            raise ValueError("MCP object exceeds the size limit")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise ValueError("MCP argument key is invalid")
            _json_safe(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise ValueError("MCP array exceeds the size limit")
        for item in value:
            _json_safe(item, depth=depth + 1)


def attach_approved_mcp_tool(capability: dict, connection: dict, *, tools, integrations, vault, catalog_store):
    risk = capability.get("approved_risk")
    if capability.get("type") != "mcp_tool" or risk not in {"read", "write", "destructive"}:
        raise ValueError("MCP tool must be explicitly owner-approved with a risk classification")
    minimum_risk = capability.get("minimum_risk")
    if minimum_risk in {"read", "write", "destructive"}:
        rank = {"read": 0, "write": 1, "destructive": 2}
        if rank[risk] < rank[minimum_risk]:
            raise ValueError("MCP tool approval is below the provider-enforced minimum risk")
    read_only = risk == "read"
    if not connection or connection.get("status") != "connected":
        raise ValueError("MCP tool connection is not active")
    connector_id = connection["connector_id"]
    operation_name = connector_id + ".call"
    manifest = ConnectorManifest(
        connector_id=connector_id,
        display_name=(capability.get("server_name") or "MCP server")[:200],
        provider="mcp",
        schema_version=1,
        authentication_type=connection["auth_type"],
        operations=(ConnectorOperation(operation_name, "read" if read_only else ("destructive" if risk == "destructive" else "write"), "read_only" if read_only else ("destructive" if risk == "destructive" else "external_side_effect"), approval="none" if read_only else "required", requires_reauth=risk == "destructive", retry=RetryPolicy(max_attempts=1), idempotency_supported=False),),
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

    tool_name = "mcp_" + connector_id.removeprefix("mcp_") + "_call"
    existing = next((item for item in tools.all() if item.name == tool_name), None)
    if existing is not None:
        existing.prohibited = False
        return tool_name

    schema = capability.get("input_schema") or {"type": "object", "properties": {}}

    def validate(parameters):
        _json_safe(parameters)
        validate_contract(parameters, schema, label=f"{tool_name} input")
        return True

    def handler(parameters):
        current = integrations.state_store
        live = catalog_store.connection(capability["id"], include_credential_ref=True)
        if not live or live.get("status") != "connected":
            raise ConnectorError("capability_revoked", "This MCP tool is no longer connected.", "permission_denied", 403, False)
        token = vault.get(live.get("credential_ref")) if live.get("credential_ref") else None
        if live.get("auth_type") in {"bearer_token", "api_key_header"} and not token:
            raise ConnectorError("authentication_required", "The MCP server needs to be reconnected.", "authentication_expired", 401, False)
        from security.request_context import current_trusted_request
        context = current_trusted_request()
        actor = {"device_id": context.device_id, "session_id": context.session_id} if context else {}
        audit_data = {"capability_id": capability["id"], "tool_name": capability["name"], "operation": operation_name}
        current.audit("mcp.execution.started", connector_id=connector_id, **actor, payload=audit_data)
        if capability.get("trusted_loopback") is True and capability.get("provider_policy") == "voicestudio":
            client = MCPHTTPClient(
                live["server_url"],
                token,
                auth_type=live.get("auth_type", "bearer_token"),
                allow_loopback=True,
            )
        else:
            client = MCPHTTPClient(
                live["server_url"],
                token,
                auth_type=live.get("auth_type", "bearer_token"),
            )
        try:
            result = client.call_tool(capability["name"], parameters)
            if result.get("isError") is True:
                raise MCPProtocolError("tool_error", "MCP server reported that the tool call failed")
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_RESPONSE_BYTES:
                raise MCPProtocolError("response_too_large", "MCP tool result exceeds the size limit")
            current.audit("mcp.execution.accepted", connector_id=connector_id, **actor, payload=audit_data)
            return result
        except Exception as exc:
            current.audit("mcp.execution.failed", connector_id=connector_id, **actor,
                          payload={**audit_data, "error_type": type(exc).__name__})
            raise

    tool = Tool(name=tool_name, description=f"Owner-approved MCP tool: {capability.get('description') or capability['name']}",
                handler=handler, risk=Risk.READ_ONLY if read_only else (Risk.DESTRUCTIVE if risk == "destructive" else Risk.EXTERNAL_SIDE_EFFECT), connector_id=connector_id,
                capability=operation_name, input_schema=schema, input_validator=validate,
                requires_reauth=risk == "destructive", idempotency_supported=False)
    tools.register(tool)
    return tool_name
