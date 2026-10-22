"""Qualification of P2-02D canonical owner-scoped Workspace conversations."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from devices.continuity import ContinuityService
from projects.store import ProjectStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.workspace_conversation_api import workspace_conversation_router
from workspaces.store import WorkspaceStore


class Registry:
    def authenticate(self, device, token):
        return device == 'trusted-1' and token == 'safe-token'

    def authorize(self, device, scope):
        return device == 'trusted-1' and scope == 'ai:chat'

    def is_active(self, device):
        return device == 'trusted-1'


class ContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        cookies = {}
        for key, val in scope.get('headers', []):
            if key == b'cookie':
                for part in val.decode().split(';'):
                    if '=' in part:
                        k, v = part.strip().split('=', 1)
                        cookies[k] = v
        token = None
        if cookies.get('pa_device') == 'trusted-1':
            token = set_trusted_request(TrustedRequestContext('trusted-1', 'session-1'))
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_trusted_request(token)


def make_client(tmp_path: Path, *, reopened=False):
    workspaces = WorkspaceStore(tmp_path / 'workspaces.sqlite3')
    continuity = ContinuityService(tmp_path / 'continuity.sqlite3')
    projects = ProjectStore(tmp_path / 'projects.sqlite3')
    runtime = {
        'device_registry': Registry(),
        'continuity': continuity,
        'workspace_store': workspaces,
        'base_project_store': projects,
    }
    app = FastAPI()
    app.add_middleware(ContextMiddleware)
    app.include_router(workspace_conversation_router(runtime, workspaces))
    client = TestClient(app)
    client.cookies.set('pa_device', 'trusted-1')
    client.cookies.set('pa_token', 'safe-token')
    return client, workspaces, continuity, projects


def test_multiple_workspace_chats_persist_and_never_copy_project_records(tmp_path):
    client, store, ledger, projects = make_client(tmp_path)
    a = store.create('owner', name='Design Lab')
    b = store.create('owner', name='Engineering')
    project = projects.create(name='Authenticated linked Project')
    store.link_project('owner', a['id'], project['id'])
    summary = client.get(f"/iphone/api/workspaces/{a['id']}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()['counts']['projects'] == 1
    assert summary.json()['counts']['members'] is None
    assert summary.json()['counts']['agents'] is None
    assert summary.json()['projects'][0]['name'] == project['name']
    assert client.get(f"/iphone/api/workspaces/{b['id']}/summary").json()['counts']['projects'] == 0

    first = client.post(f"/iphone/api/workspaces/{a['id']}/conversations", json={
        'title': 'Planning', 'request_id': 'workspace-retry-1',
    })
    assert first.status_code == 201, first.text
    ident = first.json()['conversation']['id']
    repeated = client.post(f"/iphone/api/workspaces/{a['id']}/conversations", json={
        'title': 'Planning', 'request_id': 'workspace-retry-1',
    })
    assert repeated.json()['conversation']['id'] == ident
    second = client.post(f"/iphone/api/workspaces/{a['id']}/conversations", json={
        'title': 'Implementation', 'request_id': 'workspace-retry-2',
    })
    assert second.status_code == 201, second.text
    assert second.json()['conversation']['id'] != ident
    assert {row['id'] for row in client.get(
        f"/iphone/api/workspaces/{a['id']}/conversations").json()['conversations']
    } == {ident, second.json()['conversation']['id']}
    assert client.get(f"/iphone/api/workspaces/{b['id']}/conversations/{ident}").status_code == 404
    assert client.get(f"/iphone/api/workspaces/{b['id']}/conversations").json()['conversations'] == []
    assert projects.get(project['id'])['name'] == project['name']
    assert ledger.thread(ident)['context']['workspace_id'] == a['id']

    another_client, _, restarted, _ = make_client(tmp_path)
    assert another_client.get(f"/iphone/api/workspaces/{a['id']}/conversations/{ident}").status_code == 200
    assert restarted.thread(ident)['context']['conversation_kind'] == 'workspace'
    assert ledger.list_threads(kind='personal') == []


def test_workspace_history_filter_happens_before_limit_and_owner_check(tmp_path):
    client, store, ledger, _ = make_client(tmp_path)
    a = store.create('owner', name='Historic')
    b = store.create('owner', name='Other')
    first = client.post(f"/iphone/api/workspaces/{a['id']}/conversations", json={
        'title': 'Old plan'}).json()['conversation']['id']
    for n in range(205):
        ledger.create_thread('Other workspace '+str(n), context={
            'conversation_kind': 'workspace', 'workspace_id': b['id'], 'owner_id': 'owner'})
    result = client.get(f"/iphone/api/workspaces/{a['id']}/conversations?limit=3")
    assert [item['id'] for item in result.json()['conversations']] == [first]
    assert client.get(f"/iphone/api/workspaces/{b['id']}/conversations/{first}").status_code == 404
    assert client.get('/iphone/api/workspaces/not-real/conversations').status_code == 404


def test_workspace_security_archival_and_bad_requests(tmp_path):
    client, store, _, _ = make_client(tmp_path)
    a = store.create('owner', name='Private')
    endpoint = f"/iphone/api/workspaces/{a['id']}/conversations"
    anonymous = TestClient(client.app)
    assert anonymous.get(endpoint).status_code == 401
    assert anonymous.post(endpoint, json={'title': 'Not permitted'}).status_code == 401
    client.cookies.set('pa_device', 'forged')
    assert client.post(endpoint, json={'title': 'Denied'}).status_code == 401
    client.cookies.set('pa_device', 'trusted-1')
    assert client.post(endpoint, json={'title': ''}).status_code == 422
    assert client.get(endpoint+'?limit=2000').status_code == 422
    assert client.get(endpoint+'?q='+('x'*121)).status_code == 422
    store.update('owner', a['id'], {'status': 'archived'})
    assert client.post(endpoint, json={'title': 'Denied'}).status_code == 409
    assert client.get(endpoint).status_code == 200
