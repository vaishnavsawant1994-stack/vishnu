import gc
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from projects.store import ProjectStore
from security.request_context import TrustedRequestContext, reset_trusted_request, set_trusted_request
from server.workspaces_api import workspaces_router
from workspaces.store import WorkspaceStore


class Registry:
    def authenticate(self, device, token):
        return device in {'trusted-1', 'trusted-2'} and token == 'ok'

    def authorize(self, device, scope):
        return device == 'trusted-1' and scope == 'ai:chat'


class ContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        cookies = dict(part.strip().split('=', 1) for part in scope.get('headers', [])
                       if part[0] == b'cookie' for part in part[1].decode().split(';') if '=' in part)
        token = None
        if cookies.get('pa_device') == 'trusted-1':
            token = set_trusted_request(TrustedRequestContext('trusted-1', 'session-1'))
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_trusted_request(token)


def make_client(path, project_store=None):
    app = FastAPI()
    app.add_middleware(ContextMiddleware)
    runtime={'device_registry': Registry()}
    if project_store is not None:runtime['base_project_store']=project_store
    app.include_router(workspaces_router(runtime, WorkspaceStore(path)))
    client = TestClient(app)
    client.cookies.set('pa_device', 'trusted-1')
    client.cookies.set('pa_token', 'ok')
    return client


def test_workspace_records_are_durable_owner_scoped_and_separate_from_projects():
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'workspaces.sqlite3'
        store = WorkspaceStore(path)
        workspace = store.create('owner-a', name='Vishnu Development', description='Product and AI work', workspace_type='development')
        assert workspace['status'] == 'active'
        assert workspace['is_demo'] is False
        assert store.get('owner-b', workspace['id']) is None
        reopened = WorkspaceStore(path)
        assert reopened.get('owner-a', workspace['id'])['name'] == 'Vishnu Development'
        assert reopened.list('owner-b') == []


def test_workspace_api_requires_trust_for_reads_and_fresh_trusted_context_for_writes():
    with TemporaryDirectory() as directory:
        client = make_client(Path(directory) / 'workspaces.sqlite3')
        anonymous = TestClient(client.app)
        assert anonymous.get('/iphone/api/workspaces').status_code == 401
        created = client.post('/iphone/api/workspaces', json={
            'name': 'Personal workspace', 'description': 'A genuine persisted owner record', 'workspace_type': 'personal'})
        assert created.status_code == 201, created.text
        record = created.json()['workspace']
        assert record['name'] == 'Personal workspace'
        assert client.get('/iphone/api/workspaces').json()['counts']['all'] == 1
        assert client.post(f"/iphone/api/workspaces/{record['id']}/open").status_code == 200
        assert client.patch(f"/iphone/api/workspaces/{record['id']}", json={'is_pinned': True}).json()['workspace']['is_pinned']
        assert client.patch(f"/iphone/api/workspaces/{record['id']}", json={'status': 'archived'}).status_code == 200
        assert client.get('/iphone/api/workspaces').json()['workspaces'] == []
        assert client.get('/iphone/api/workspaces?status=archived').json()['workspaces'][0]['id'] == record['id']


def test_reference_fixture_is_explicit_idempotent_and_studio_saves_only_layout():
    with TemporaryDirectory() as directory:
        client = make_client(Path(directory) / 'workspaces.sqlite3')
        first = client.post('/iphone/api/workspaces/reference-demo')
        second = client.post('/iphone/api/workspaces/reference-demo')
        assert first.status_code == 201
        assert first.json()['workspace']['is_demo'] is True
        assert 'not a real organization' in first.json()['notice']
        assert first.json()['workspace']['id'] == second.json()['workspace']['id']
        workspace_id = first.json()['workspace']['id']
        saved = client.put(f'/iphone/api/workspaces/{workspace_id}/studio/views', json={
            'name': 'Default', 'layout': {'panels': [{'type':'project','resource_type': 'project', 'resource_id': 'canonical-id', 'x': 0, 'y': 0}]}})
        assert saved.status_code == 200, saved.text
        assert saved.json()['view']['layout']['panels'][0]['resource_id'] == 'canonical-id'
        assert client.get(f'/iphone/api/workspaces/{workspace_id}/studio/views').json()['views'][0]['name'] == 'Default'
        rejected=client.put(f'/iphone/api/workspaces/{workspace_id}/studio/views',json={
            'name':'Unsafe','layout':{'panels':[{'type':'project','resource_type':'project','resource_id':'canonical-id','content':'copied project content'}]}})
        assert rejected.status_code==422


def test_workspace_write_rejects_session_without_trusted_request_context():
    with TemporaryDirectory() as directory:
        app = FastAPI()
        app.include_router(workspaces_router({'device_registry': Registry()}, WorkspaceStore(Path(directory) / 'w.sqlite3')))
        client = TestClient(app)
        client.cookies.set('pa_device', 'trusted-1')
        client.cookies.set('pa_token', 'ok')
        assert client.post('/iphone/api/workspaces', json={'name': 'Blocked'}).status_code == 401


def test_workspace_can_link_a_real_canonical_project_without_copying_it():
    with TemporaryDirectory() as directory:
        projects=ProjectStore(Path(directory)/'projects.sqlite3')
        project=projects.create(name='Patient CRM implementation',goal='Implement the patient CRM')
        client=make_client(Path(directory)/'workspaces.sqlite3',projects)
        workspace=client.post('/iphone/api/workspaces',json={'name':'Healthcare','workspace_type':'business'}).json()['workspace']
        linked=client.post(f"/iphone/api/workspaces/{workspace['id']}/resources",json={'resource_type':'project','resource_id':project['id']})
        assert linked.status_code==201,linked.text
        document=linked.json()
        assert document['workspace']['linked_project_count']==1
        assert document['projects'][0]['project']['id']==project['id']
        assert projects.get(project['id'])['name']=='Patient CRM implementation'
        removed=client.delete(f"/iphone/api/workspaces/{workspace['id']}/resources/projects/{project['id']}")
        assert removed.status_code==200
        assert removed.json()['projects']==[]
        assert projects.get(project['id']) is not None
        gc.collect()


def test_workspace_api_rejects_linking_unknown_project():
    with TemporaryDirectory() as directory:
        projects=ProjectStore(Path(directory)/'projects.sqlite3')
        client=make_client(Path(directory)/'workspaces.sqlite3',projects)
        workspace=client.post('/iphone/api/workspaces',json={'name':'Research'}).json()['workspace']
        result=client.post(f"/iphone/api/workspaces/{workspace['id']}/resources",json={'resource_type':'project','resource_id':'missing'})
        assert result.status_code==404
        gc.collect()
