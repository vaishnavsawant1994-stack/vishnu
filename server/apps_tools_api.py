from __future__ import annotations

import json
import sqlite3
import time
from fastapi import APIRouter, HTTPException, Path, Request

from apps_tools.projection import AppsToolsProjection
from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.execution import _public_https_url, attach_approved_capability
from integrations.discovery.mcp import normalize_mcp_server
from integrations.discovery.mcp_runtime import MCPHTTPClient, MCPProtocolError, attach_approved_mcp_tool
from integrations.gateway import ConnectorError
from security.approvals import ApprovalManager
from security.request_context import current_trusted_request


def apps_tools_router(runtime):
    """Authorized catalog transport and owner-controlled OpenAPI read bridge."""
    router = APIRouter(prefix='/iphone/api/apps-tools', tags=['apps-tools'])
    devices = runtime['device_registry']
    projection = AppsToolsProjection(runtime['tools'], runtime.get('integrations'), runtime.get('memory'))

    state = getattr(runtime.get('integrations'), 'state_store', None)
    catalog = CapabilityCatalogStore(state.path.parent / 'capability-catalog.sqlite3') if state is not None else None
    approval_path = (getattr(getattr(runtime.get('agent_executor'), 'approvals', None), 'path', None)
                     or getattr(runtime['tools'], '_approval_path', None))
    approvals = runtime['agent_executor'].approvals if runtime.get('agent_executor') else (ApprovalManager(path=approval_path) if approval_path else None)

    # Rehydrate owner-approved tools into the existing shared registry after a
    # process restart. Each handler still reads the live connection row before
    # reaching the provider, so revocation fences queued and future calls.
    if catalog is not None:
        try:
            for capability in catalog.all():
                connection = catalog.connection(capability['id'], include_credential_ref=True)
                if not connection or connection.get('status') != 'connected':
                    continue
                try:
                    if capability.get('type') == 'mcp_tool' and capability.get('approved_risk'):
                        attach_approved_mcp_tool(capability, connection, tools=runtime['tools'],
                            integrations=runtime['integrations'], vault=runtime.get('vault'), catalog_store=catalog)
                    elif capability.get('type') != 'mcp_tool' and capability.get('execution_supported', True) and capability.get('method') in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
                        attach_approved_capability(capability, connection, tools=runtime['tools'],
                            integrations=runtime['integrations'], vault=runtime.get('vault'),
                            state_store=state, catalog_store=catalog)
                except (ValueError, KeyError, TypeError):
                    continue
        except (ValueError, sqlite3.Error):
            pass

    def require_owner(scope='device:read'):
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not devices.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if context.auth_type == 'native' and (context.scopes is None or scope not in context.scopes):
            raise HTTPException(403, f'This native session is not scoped for {scope}')
        if not hasattr(devices, 'authorize') or not devices.authorize(context.device_id, scope):
            raise HTTPException(403, f'This device is not permitted to use {scope}')
        return context

    def require_recent_owner():
        context = require_owner('device:admin')
        stamp = context.reauthenticated_at
        try:
            fresh = stamp is not None and 0 <= time.time() - float(stamp) <= 300
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            raise HTTPException(401, 'Recent owner reauthentication required')
        return context

    @router.get('/tools')
    def list_tools():
        require_owner()
        return {'tools': projection.tools_list()}

    @router.get('/tools/{tool_id}')
    def tool_detail(tool_id: str = Path(..., min_length=1, max_length=200)):
        require_owner()
        item = projection.tool_detail(tool_id)
        if item is None:
            raise HTTPException(404, 'Tool not found')
        return {'tool': item}

    @router.get('/apps')
    def list_apps():
        require_owner()
        return {'apps': projection.apps_list()}

    @router.get('/apps/{app_id}')
    def app_detail(app_id: str = Path(..., min_length=1, max_length=200)):
        require_owner()
        item = projection.app_detail(app_id)
        if item is None:
            raise HTTPException(404, 'App not found')
        return {'app': item}

    @router.get('/capabilities')
    def search_capabilities(query: str = '', limit: int = 50):
        require_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        try:
            items = catalog.search(query, limit)
            return {'capabilities': [{**item, 'connection': catalog.connection(item['id'])} for item in items]}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def capability_audit(capability_id: str, limit: int):
        context = require_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        capability = catalog.get(capability_id)
        if capability is None:
            raise HTTPException(404, 'Capability not found')
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        audit = getattr(state_store, 'lifecycle', None)
        if audit is None:
            return {'entries': []}
        server_id = capability.get('server_id') if capability.get('type') == 'mcp_tool' else None
        rows = audit.entries(min(1000, max(100, limit * 10)))
        selected = []
        for row in rows:
            payload = row.get('payload') or {}
            if payload.get('capability_id') != capability_id and payload.get('server_id') != (server_id or capability_id):
                continue
            # Keep the projection to redacted audit data and avoid exposing a
            # different device's activity from a shared connector.
            if payload.get('device_id') not in (None, context.device_id):
                continue
            selected.append({key: row.get(key) for key in ('id', 'action', 'created_at', 'payload', 'entry_hash')})
            if len(selected) >= limit:
                break
        return {'entries': selected}

    @router.get('/capabilities/{capability_id}/history')
    def capability_history(capability_id: str, limit: int = 50):
        if not 1 <= limit <= 100:
            raise HTTPException(422, 'History limit must be between 1 and 100')
        return capability_audit(capability_id, limit)

    @router.get('/capabilities/{capability_id}/audit')
    def capability_audit_log(capability_id: str, limit: int = 50):
        if not 1 <= limit <= 100:
            raise HTTPException(422, 'Audit limit must be between 1 and 100')
        return capability_audit(capability_id, limit)

    @router.get('/capabilities/{capability_id:path}')
    def capability_detail(capability_id: str):
        require_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        try:
            item = catalog.get(capability_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if item is None:
            raise HTTPException(404, 'Capability not found')
        return {'capability': {**item, 'connection': catalog.connection(capability_id)}}

    @router.post('/capabilities/openapi')
    async def discover_openapi(request: Request):
        require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        raw = await request.body()
        if len(raw) > 1_000_000:
            raise HTTPException(413, 'OpenAPI document exceeds the 1 MB limit')
        try:
            payload = json.loads(raw)
            document = payload.get('document') if isinstance(payload, dict) else None
            source_url = payload.get('source_url') if isinstance(payload, dict) else None
            if source_url is not None:
                source_url = _public_https_url(source_url)
            count = catalog.import_openapi(document, source_url=source_url)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid OpenAPI document or source URL') from exc
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            ctx = current_trusted_request()
            state_store.audit('capability.discovered', device_id=ctx.device_id, session_id=ctx.session_id, payload={'operations': count})
        return {'discovered': count, 'executable': False}

    @router.get('/mcp/servers')
    def list_mcp_servers():
        require_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        servers = []
        for server in catalog.mcp_servers():
            connection = catalog.connection(server['id'])
            tools = catalog.mcp_tools(server['id'])
            servers.append({**server, 'connection': connection,
                            'tools': [{**tool, 'connection': catalog.connection(tool['id'])} for tool in tools]})
        return {'servers': servers}

    @router.post('/mcp/servers')
    async def add_mcp_server(request: Request):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(413, 'MCP server descriptor exceeds the size limit')
        try:
            descriptor = normalize_mcp_server(json.loads(raw))
            descriptor['url'] = _public_https_url(descriptor['url'])
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid MCP server descriptor') from exc
        catalog.import_mcp_server(descriptor)
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            state_store.audit('mcp.server.discovered', device_id=context.device_id, session_id=context.session_id,
                              payload={'server_id': descriptor['id'], 'server_name': descriptor['name']})
        return {'server': {**descriptor, 'connection': catalog.connection(descriptor['id']), 'tools': []}}

    @router.post('/mcp/servers/{server_id}/discover')
    async def discover_mcp_tools(server_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        server = catalog.get(server_id)
        if server is None or server.get('type') != 'mcp_server':
            raise HTTPException(404, 'MCP server not found')
        server_connection = catalog.connection(server_id)
        if server_connection and server_connection.get('status') == 'connected':
            raise HTTPException(409, 'MCP server is already connected')
        if not getattr(runtime.get('integrations'), 'state_store', None) or not runtime.get('vault'):
            raise HTTPException(503, 'Secure connector services unavailable')
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(413, 'MCP connection settings exceed the size limit')
        try:
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError()
            auth_type = payload.get('auth_type', 'none')
            token = payload.get('api_key')
            if auth_type not in {'none', 'bearer_token', 'api_key_header'} or (auth_type in {'bearer_token', 'api_key_header'} and (not isinstance(token, str) or not token or len(token) > 4096)):
                raise ValueError()
            if auth_type == 'none' and token not in (None, ''):
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid MCP connection settings') from exc
        credential_ref = 'mcp-credential:' + server_id.split(':', 1)[-1] if auth_type in {'bearer_token', 'api_key_header'} else None
        vault = runtime['vault']
        if credential_ref:
            vault.set(credential_ref, token)
        state_store = runtime['integrations'].state_store
        try:
            remote_tools = MCPHTTPClient(server['url'], token, auth_type=auth_type).list_tools()
            entries = catalog.import_mcp_tools(server_id, remote_tools, server_name=server['name'], server_url=server['url'])
            connector_id = 'mcpserver_' + server_id.split(':', 1)[-1]
            catalog.connect(server_id, server_url=server['url'], auth_type=auth_type, credential_ref=credential_ref,
                            approved_by=context.device_id, approved_at=time.time(), connector_id=connector_id)
        except MCPProtocolError as exc:
            if credential_ref:
                vault.delete(credential_ref)
            state_store.audit('mcp.server.discovery_failed', device_id=context.device_id, session_id=context.session_id,
                              payload={'server_id': server_id, 'error_code': exc.code})
            raise HTTPException(502, exc.safe_message) from exc
        except Exception as exc:
            if credential_ref:
                vault.delete(credential_ref)
            raise HTTPException(502, 'MCP server could not be reached') from exc
        state_store.audit('mcp.server.connected', connector_id=connector_id, device_id=context.device_id,
                          session_id=context.session_id, payload={'server_id': server_id, 'tools_discovered': len(entries)})
        return {'server_id': server_id, 'connected': True, 'tools': [{**entry, 'connection': None} for entry in entries]}

    @router.post('/mcp/capabilities/{capability_id}/approve')
    async def approve_mcp_tool(capability_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        capability = catalog.get(capability_id)
        if capability is None or capability.get('type') != 'mcp_tool':
            raise HTTPException(404, 'MCP tool not found')
        raw = await request.body()
        try:
            payload = json.loads(raw) if raw else {}
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid approval request') from exc
        if not isinstance(payload, dict):
            raise HTTPException(422, 'MCP approval classification is required')
        requested_risk = payload.get('risk')
        if requested_risk is None and payload.get('read_only_attested') is True:
            requested_risk = 'read'
        if requested_risk not in {'read', 'write', 'destructive'} or payload.get('reviewed') is not True and requested_risk != 'read':
            raise HTTPException(422, 'Owner must explicitly classify the MCP tool as read, write, or destructive')
        if requested_risk == 'read' and payload.get('read_only_attested') is not True:
            raise HTTPException(422, 'Owner must attest that a read-classified MCP tool is read-only')
        server_connection = catalog.connection(capability['server_id'], include_credential_ref=True)
        if not server_connection or server_connection.get('status') != 'connected':
            raise HTTPException(409, 'Connect and discover this MCP server first')
        connector_id = 'mcp_' + capability_id.split(':', 1)[-1]
        approved = {**capability, 'approved_risk': requested_risk, 'read_only_attested': requested_risk == 'read'}
        try:
            catalog.update_payload(capability_id, approved)
            catalog.connect(capability_id, server_url=server_connection['server_url'], auth_type=server_connection['auth_type'],
                            credential_ref=server_connection.get('credential_ref'), approved_by=context.device_id,
                            approved_at=time.time(), connector_id=connector_id)
            connection = catalog.connection(capability_id, include_credential_ref=True)
            tool_name = attach_approved_mcp_tool(approved, connection, tools=runtime['tools'],
                integrations=runtime['integrations'], vault=runtime['vault'], catalog_store=catalog)
        except Exception as exc:
            catalog.revoke(capability_id)
            catalog.update_payload(capability_id, {**capability, 'approved_risk': None, 'read_only_attested': False})
            try:
                runtime['integrations'].get(connector_id).configured = False
            except (AttributeError, KeyError):
                pass
            for tool in runtime['tools'].all():
                if tool.name == 'mcp_' + capability_id.split(':', 1)[-1] + '_call':
                    tool.prohibited = True
                    break
            raise HTTPException(422, 'MCP tool could not be approved') from exc
        state_store = runtime['integrations'].state_store
        state_store.audit('mcp.capability.approved', connector_id=connector_id, device_id=context.device_id,
                          session_id=context.session_id, payload={'capability_id': capability_id, 'tool': tool_name})
        return {'approved': True, 'capability_id': capability_id, 'tool': tool_name,
                'connection': catalog.connection(capability_id)}

    @router.post('/mcp/servers/{server_id}/disconnect')
    def disconnect_mcp_server(server_id: str):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        server = catalog.get(server_id)
        if server is None or server.get('type') != 'mcp_server':
            raise HTTPException(404, 'MCP server not found')
        secret_ref = catalog.revoke(server_id)
        if secret_ref and runtime.get('vault'):
            runtime['vault'].delete(secret_ref)
        for capability in catalog.mcp_tools(server_id):
            cap_ref = catalog.revoke(capability['id'])
            connection = catalog.connection(capability['id'])
            if connection:
                try:
                    runtime['integrations'].get(connection['connector_id']).configured = False
                except (AttributeError, KeyError):
                    pass
                tool_name = 'mcp_' + connection['connector_id'].removeprefix('mcp_') + '_call'
                for tool in runtime['tools'].all():
                    if tool.name == tool_name:
                        tool.prohibited = True
                        break
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            state_store.audit('mcp.server.revoked', device_id=context.device_id, session_id=context.session_id,
                              payload={'server_id': server_id})
        return {'connected': False, 'server_id': server_id}

    @router.post('/capabilities/{capability_id}/connect')
    async def connect_capability(capability_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        capability = catalog.get(capability_id)
        if capability is None:
            raise HTTPException(404, 'Capability not found')
        if capability.get('method') not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
            raise HTTPException(403, 'This OpenAPI operation uses an unsupported HTTP method')
        if capability.get('execution_supported') is False:
            raise HTTPException(403, 'This OpenAPI operation uses an unsupported request parameter or body schema')
        if capability.get('method') != 'GET' and not capability.get('request_body') and capability.get('method') not in {'DELETE'}:
            raise HTTPException(403, 'This write operation has no supported bounded JSON request schema')
        existing_connection = catalog.connection(capability_id)
        if existing_connection and existing_connection.get('status') == 'connected':
            raise HTTPException(409, 'Capability is already connected; disconnect it before changing credentials')
        if not getattr(runtime.get('integrations'), 'state_store', None) or not runtime.get('vault'):
            raise HTTPException(503, 'Secure connector services unavailable')
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(413, 'Connection settings exceed the size limit')
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError()
            server_url = _public_https_url(payload.get('server_url') or capability.get('source_url'))
            source_url = capability.get('source_url')
            if source_url and server_url != _public_https_url(source_url):
                raise ValueError()
            auth_type = payload.get('auth_type', 'none')
            if auth_type not in {'none', 'bearer_token', 'api_key_header'}:
                raise ValueError()
            credential = payload.get('api_key')
            if auth_type in {'bearer_token', 'api_key_header'} and (not isinstance(credential, str) or not credential or len(credential) > 4096):
                raise ValueError()
            if auth_type == 'none' and credential not in (None, ''):
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid connection settings') from exc
        suffix = capability['id'].split(':', 1)[-1]
        connector_id = 'openapi_' + ''.join(ch for ch in suffix.lower() if ch in '0123456789abcdef')[:24]
        if len(connector_id) < 12:
            raise HTTPException(422, 'Invalid capability identifier')
        credential_ref = 'openapi-credential:' + suffix if auth_type in {'bearer_token', 'api_key_header'} else None
        vault = runtime['vault']
        state_store = runtime['integrations'].state_store
        if credential_ref:
            vault.set(credential_ref, credential)
        try:
            catalog.connect(capability_id, server_url=server_url, auth_type=auth_type,
                            credential_ref=credential_ref, approved_by=context.device_id,
                            approved_at=time.time(), connector_id=connector_id)
            connection = catalog.connection(capability_id, include_credential_ref=True)
            tool_name = attach_approved_capability(capability, connection, tools=runtime['tools'],
                integrations=runtime['integrations'], vault=vault, state_store=state_store, catalog_store=catalog)
            state_store.set_health(connector_id, 'disconnected')
        except Exception as exc:
            catalog.revoke(capability_id)
            if credential_ref:
                vault.delete(credential_ref)
            raise HTTPException(503, 'Capability could not be registered') from exc
        state_store.audit('capability.approved', connector_id=connector_id, device_id=context.device_id,
                          session_id=context.session_id, payload={'capability_id': capability_id, 'tool': tool_name, 'auth_type': auth_type})
        return {'connected': True, 'capability_id': capability_id, 'connector_id': connector_id,
                'tool': tool_name, 'connection': catalog.connection(capability_id)}

    @router.post('/capabilities/{capability_id}/execute')
    async def execute_capability(capability_id: str, request: Request):
        context = require_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        capability = catalog.get(capability_id)
        connection = catalog.connection(capability_id, include_credential_ref=True)
        if capability is None or not connection:
            raise HTTPException(404, 'Connected capability not found')
        if connection.get('status') != 'connected':
            raise HTTPException(409, 'Capability is not connected')
        try:
            if capability.get('type') == 'mcp_tool':
                attach_approved_mcp_tool(capability, connection, tools=runtime['tools'],
                    integrations=runtime['integrations'], vault=runtime.get('vault'), catalog_store=catalog)
            else:
                attach_approved_capability(capability, connection, tools=runtime['tools'],
                    integrations=runtime['integrations'], vault=runtime.get('vault'),
                    state_store=getattr(runtime.get('integrations'), 'state_store', None), catalog_store=catalog)
            raw = await request.body()
            if len(raw) > 16_384:
                raise HTTPException(413, 'Operation parameters exceed the size limit')
            payload = json.loads(raw) if raw else {}
            parameters = payload.get('parameters', {}) if isinstance(payload, dict) else None
            method = str(capability.get('method', 'GET')).lower()
            tool_name = ('mcp_' + connection['connector_id'].removeprefix('mcp_') + '_call'
                         if capability.get('type') == 'mcp_tool'
                         else 'openapi_' + connection['connector_id'].removeprefix('openapi_') + '_' + method)
            tool = runtime['tools'].get(tool_name)
            approval_id = payload.get('approval_id') if isinstance(payload, dict) else None
            write_operation = ((capability.get('type') == 'mcp_tool' and capability.get('approved_risk') in {'write', 'destructive'})
                               or (capability.get('type') != 'mcp_tool' and method != 'get'))
            if write_operation:
                if method == 'delete' or capability.get('approved_risk') == 'destructive':
                    require_recent_owner()
                if not approvals or not isinstance(approval_id, str):
                    raise HTTPException(409, {'code': 'owner_approval_required', 'message': 'Create and approve a one-use approval for these exact operation parameters before execution.'})
                try:
                    approvals.approve(approval_id, 'capability:' + capability_id, tool_name, parameters,
                        owner_id='owner', device_id=context.device_id, session_id=context.session_id,
                        security_epoch=approvals.current_security_epoch(), destination=connection['server_url'],
                        data_classification='internal')
                except PermissionError as exc:
                    raise HTTPException(409, {'code': 'approval_invalid', 'message': str(exc)}) from exc
            decision = runtime['tools'].authorize(tool, confirmed=write_operation, parameters=parameters, data_classification='internal')
            if not decision.allowed:
                raise HTTPException(409 if decision.requires_confirmation else 403, decision.reason)
            if write_operation:
                dispatch = approvals.begin_dispatch(approval_id, worker_id='capability-api')
                if not dispatch.get('dispatch'):
                    raise HTTPException(409, {'code': 'approval_unavailable', 'message': 'This one-use approval is no longer available for dispatch.'})
            try:
                result = runtime['tools'].dispatch(tool, parameters)
            except Exception:
                if write_operation and approvals:
                    approvals.mark_recovery_required(approval_id, 'capability_dispatch_outcome_uncertain')
                raise
            if write_operation and approvals:
                approvals.complete_dispatch(approval_id, {'status': 'dispatched', 'capability_id': capability_id})
            verification = runtime['tools'].verify_result(tool, parameters, result)
        except HTTPException:
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid operation parameters') from exc
        except ConnectorError as exc:
            raise HTTPException(exc.http_status, exc.safe_dict()) from exc
        except MCPProtocolError as exc:
            raise HTTPException(502, {'code': exc.code, 'message': exc.safe_message}) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, 'API operation failed') from exc
        return {'result': result, 'verified': verification.verified,
                'verification': verification.reason, 'tool': tool_name}

    @router.post('/capabilities/{capability_id}/execution-approvals')
    async def create_execution_approval(capability_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None or approvals is None:
            raise HTTPException(503, 'Durable approval service unavailable')
        capability = catalog.get(capability_id)
        connection = catalog.connection(capability_id)
        if not capability or not connection or connection.get('status') != 'connected':
            raise HTTPException(404, 'Connected capability not found')
        is_mcp = capability.get('type') == 'mcp_tool'
        method = ('mcp:' + str(capability.get('approved_risk') or 'unapproved')) if is_mcp else str(capability.get('method', '')).lower()
        if is_mcp and capability.get('approved_risk') not in {'write', 'destructive'}:
            raise HTTPException(422, 'Only write-classified MCP tools require execution approval')
        if not is_mcp and method not in {'post', 'put', 'patch', 'delete'}:
            raise HTTPException(422, 'Only write operations require execution approval')
        if method == 'delete' or method.endswith('destructive'):
            require_recent_owner()
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(413, 'Operation parameters exceed the size limit')
        try:
            payload = json.loads(raw) if raw else {}
            parameters = payload.get('parameters', {}) if isinstance(payload, dict) else None
            if not isinstance(parameters, dict):
                raise ValueError()
            connector_id = connection['connector_id']
            if is_mcp:
                tool_name = 'mcp_' + connector_id.removeprefix('mcp_') + '_call'
                attach_approved_mcp_tool(capability, connection, tools=runtime['tools'], integrations=runtime['integrations'], vault=runtime['vault'], catalog_store=catalog)
            else:
                tool_name = 'openapi_' + connector_id.removeprefix('openapi_') + '_' + method
                attach_approved_capability(capability, {**connection, 'status': 'connected'}, tools=runtime['tools'],
                    integrations=runtime['integrations'], vault=runtime['vault'],
                    state_store=getattr(runtime.get('integrations'), 'state_store', None), catalog_store=catalog)
            tool = runtime['tools'].get(tool_name)
            runtime['tools'].validate_input(tool, parameters)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid operation parameters') from exc
        except KeyError as exc:
            raise HTTPException(503, 'Capability execution tool is unavailable') from exc
        ticket = approvals.create('capability:' + capability_id, tool_name, parameters, owner_id='owner',
            device_id=context.device_id, session_id=context.session_id,
            security_epoch=approvals.current_security_epoch(), destination=connection['server_url'],
            data_classification='internal')
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            state_store.audit('capability.execution_approval.requested', connector_id=connection['connector_id'],
                device_id=context.device_id, session_id=context.session_id,
                payload={'capability_id': capability_id, 'tool': tool_name, 'method': method, 'approval_id': ticket.id})
        return {'approval_id': ticket.id, 'status': 'pending', 'expires_at': ticket.expires_at,
                'capability_id': capability_id, 'operation': method.upper()}

    @router.post('/capabilities/{capability_id}/execution-approvals/{approval_id}/approve')
    async def approve_execution(capability_id: str, approval_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None or approvals is None:
            raise HTTPException(503, 'Durable approval service unavailable')
        capability = catalog.get(capability_id)
        connection = catalog.connection(capability_id)
        if not capability or not connection or connection.get('status') != 'connected':
            raise HTTPException(404, 'Connected capability not found')
        is_mcp = capability.get('type') == 'mcp_tool'
        method = ('mcp:' + str(capability.get('approved_risk') or 'unapproved')) if is_mcp else str(capability.get('method', '')).lower()
        if is_mcp and capability.get('approved_risk') not in {'write', 'destructive'}:
            raise HTTPException(422, 'Only write-classified MCP tools require execution approval')
        if method == 'delete' or method.endswith('destructive'):
            require_recent_owner()
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(413, 'Operation parameters exceed the size limit')
        try:
            payload = json.loads(raw) if raw else {}
            parameters = payload.get('parameters', {}) if isinstance(payload, dict) else None
            if not isinstance(parameters, dict):
                raise ValueError()
            tool_name = ('mcp_' + connection['connector_id'].removeprefix('mcp_') + '_call' if is_mcp else
                         'openapi_' + connection['connector_id'].removeprefix('openapi_') + '_' + method)
            record = approvals.record(approval_id)
            ticket = record.get('ticket') if record else None
            if not ticket or ticket.execution_id != 'capability:' + capability_id:
                raise PermissionError('approval is missing or scoped to another operation')
            result = approvals.approve(approval_id, 'capability:' + capability_id, tool_name, parameters,
                owner_id='owner', device_id=context.device_id, session_id=context.session_id,
                security_epoch=approvals.current_security_epoch(), destination=connection['server_url'],
                data_classification='internal')
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid approval parameters') from exc
        except PermissionError as exc:
            raise HTTPException(409, {'code': 'approval_invalid', 'message': str(exc)}) from exc
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            state_store.audit('capability.execution_approval.approved', connector_id=connection['connector_id'],
                device_id=context.device_id, session_id=context.session_id,
                payload={'capability_id': capability_id, 'approval_id': approval_id, 'method': method})
        return {'approval_id': approval_id, 'status': result['status'], 'approved': result['status'] == 'approved'}

    @router.post('/capabilities/{capability_id}/disconnect')
    def disconnect_capability(capability_id: str):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        credential_ref = catalog.revoke(capability_id)
        capability = catalog.get(capability_id)
        if credential_ref and runtime.get('vault') and (not capability or capability.get('type') != 'mcp_tool'):
            runtime['vault'].delete(credential_ref)
        if credential_ref is None and catalog.connection(capability_id) is None:
            raise HTTPException(404, 'Connected capability not found')
        connection = catalog.connection(capability_id)
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store and connection:
            state_store.set_health(connection['connector_id'], 'revoked')
            state_store.audit('capability.revoked', connector_id=connection['connector_id'], device_id=context.device_id,
                              session_id=context.session_id, payload={'capability_id': capability_id})
        if connection:
            try:
                runtime['integrations'].get(connection['connector_id']).configured = False
            except (AttributeError, KeyError):
                pass
            tool_name = ('mcp_' + connection['connector_id'].removeprefix('mcp_') + '_call'
                         if capability and capability.get('type') == 'mcp_tool'
                         else 'openapi_' + connection['connector_id'].removeprefix('openapi_') + '_get')
            for tool in runtime['tools'].all():
                if tool.name == tool_name:
                    tool.prohibited = True
                    break
        return {'connected': False, 'capability_id': capability_id}

    @router.post('/capabilities/{capability_id}/credentials/rotate')
    async def rotate_capability_credential(capability_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None or runtime.get('vault') is None:
            raise HTTPException(503, 'Secure credential service unavailable')
        capability = catalog.get(capability_id)
        connection = catalog.connection(capability_id, include_credential_ref=True)
        if not capability or capability.get('type') == 'mcp_tool' or not connection or connection.get('status') != 'connected':
            raise HTTPException(404, 'Connected OpenAPI capability not found')
        raw = await request.body()
        if len(raw) > 8192:
            raise HTTPException(413, 'Credential payload exceeds the size limit')
        try:
            payload = json.loads(raw)
            auth_type = payload.get('auth_type') if isinstance(payload, dict) else None
            secret = payload.get('api_key') if isinstance(payload, dict) else None
            if auth_type not in {'bearer_token', 'api_key_header'} or not isinstance(secret, str) or not secret or len(secret) > 4096:
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'A valid bearer token or API key is required') from exc
        credential_ref = connection.get('credential_ref') or ('openapi-credential:' + capability_id.split(':', 1)[-1])
        runtime['vault'].set(credential_ref, secret)
        catalog.connect(capability_id, server_url=connection['server_url'], auth_type=auth_type,
            credential_ref=credential_ref, approved_by=context.device_id, approved_at=time.time(),
            connector_id=connection['connector_id'])
        state_store = getattr(runtime.get('integrations'), 'state_store', None)
        if state_store:
            state_store.audit('capability.credential.rotated', connector_id=connection['connector_id'],
                device_id=context.device_id, session_id=context.session_id,
                payload={'capability_id': capability_id, 'auth_type': auth_type})
        return {'rotated': True, 'capability_id': capability_id, 'auth_type': auth_type}

    return router
