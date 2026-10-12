from __future__ import annotations

import json
import time
from fastapi import APIRouter, HTTPException, Path, Request

from apps_tools.projection import AppsToolsProjection
from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.execution import _public_https_url, attach_approved_capability
from integrations.gateway import ConnectorError
from security.request_context import current_trusted_request


def apps_tools_router(runtime):
    """Authorized catalog transport and owner-controlled OpenAPI read bridge."""
    router = APIRouter(prefix='/iphone/api/apps-tools', tags=['apps-tools'])
    devices = runtime['device_registry']
    projection = AppsToolsProjection(runtime['tools'], runtime.get('integrations'), runtime.get('memory'))

    state = getattr(runtime.get('integrations'), 'state_store', None)
    catalog = CapabilityCatalogStore(state.path.parent / 'capability-catalog.sqlite3') if state is not None else None

    def require_owner(scope='device:read'):
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not devices.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
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
            return {'capabilities': catalog.search(query, limit)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

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

    @router.post('/capabilities/{capability_id}/connect')
    async def connect_capability(capability_id: str, request: Request):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        capability = catalog.get(capability_id)
        if capability is None:
            raise HTTPException(404, 'Capability not found')
        if capability.get('method') != 'GET' or capability.get('risk') != 'read':
            raise HTTPException(403, 'Only GET read operations may be connected in this milestone')
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
            if auth_type not in {'none', 'bearer_token'}:
                raise ValueError()
            credential = payload.get('api_key')
            if auth_type == 'bearer_token' and (not isinstance(credential, str) or not credential or len(credential) > 4096):
                raise ValueError()
            if auth_type == 'none' and credential not in (None, ''):
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid connection settings') from exc
        suffix = capability['id'].split(':', 1)[-1]
        connector_id = 'openapi_' + ''.join(ch for ch in suffix.lower() if ch in '0123456789abcdef')[:24]
        if len(connector_id) < 12:
            raise HTTPException(422, 'Invalid capability identifier')
        credential_ref = 'openapi-credential:' + suffix if auth_type == 'bearer_token' else None
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
            attach_approved_capability(capability, connection, tools=runtime['tools'],
                integrations=runtime['integrations'], vault=runtime.get('vault'),
                state_store=getattr(runtime.get('integrations'), 'state_store', None), catalog_store=catalog)
            raw = await request.body()
            if len(raw) > 16_384:
                raise HTTPException(413, 'Operation parameters exceed the size limit')
            payload = json.loads(raw) if raw else {}
            parameters = payload.get('parameters', {}) if isinstance(payload, dict) else None
            tool_name = 'openapi_' + connection['connector_id'].removeprefix('openapi_') + '_get'
            tool = runtime['tools'].get(tool_name)
            decision = runtime['tools'].authorize(tool, parameters=parameters, data_classification='internal')
            if not decision.allowed:
                raise HTTPException(409 if decision.requires_confirmation else 403, decision.reason)
            result = runtime['tools'].dispatch(tool, parameters)
            verification = runtime['tools'].verify_result(tool, parameters, result)
        except HTTPException:
            raise
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, 'Invalid operation parameters') from exc
        except ConnectorError as exc:
            raise HTTPException(exc.http_status, exc.safe_dict()) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, 'API operation failed') from exc
        return {'result': result, 'verified': verification.verified,
                'verification': verification.reason, 'tool': tool_name}

    @router.post('/capabilities/{capability_id}/disconnect')
    def disconnect_capability(capability_id: str):
        context = require_recent_owner()
        if catalog is None:
            raise HTTPException(503, 'Catalog unavailable')
        credential_ref = catalog.revoke(capability_id)
        if credential_ref and runtime.get('vault'):
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
            tool_name = 'openapi_' + connection['connector_id'].removeprefix('openapi_') + '_get'
            for tool in runtime['tools'].all():
                if tool.name == tool_name:
                    tool.prohibited = True
                    break
        return {'connected': False, 'capability_id': capability_id}

    return router
