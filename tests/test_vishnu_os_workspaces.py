"""Regression tests for the first Vishnu OS Workspace/Studio foundation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import workspaces_os_api as os_api


@pytest.fixture
def store(tmp_path):
    return os_api.WorkspaceStore(tmp_path / 'workspaces.sqlite3')


def test_workspace_create_idempotency_persistence_and_template(store, tmp_path):
    payload = os_api.WorkspaceCreate(
        name='  Vishnu 3D Character  ',
        description=' Models and animation ',
        template_id='3d',
        request_id='retry-key-2026',
    )
    first = store.create('owner', payload)
    repeated = store.create('owner', payload)
    assert first['id'] == repeated['id']
    assert first['name'] == 'Vishnu 3D Character'
    assert first['description'] == 'Models and animation'
    assert first['template_id'] == '3d'
    assert first['linked_counts']['project'] == 0
    reopened = os_api.WorkspaceStore(tmp_path / 'workspaces.sqlite3')
    assert len(reopened.list('owner')) == 1
    assert reopened.get(first['id'], 'owner')['name'] == first['name']


def test_workspace_owner_boundaries_and_pin_archive(store):
    created = store.create('owner', os_api.WorkspaceCreate(name='Research'))
    assert len(store.list('another-owner')) == 0
    with pytest.raises(KeyError):
        store.get(created['id'], 'another-owner')
    updated = store.patch(
        created['id'], 'owner',
        os_api.WorkspacePatch(pinned=True, status='archived'),
    )
    assert updated['pinned'] is True
    assert updated['status'] == 'archived'
    assert store.list('owner')[0]['id'] == created['id']
    with pytest.raises(ValueError):
        store.patch(created['id'], 'owner', os_api.WorkspacePatch(name=' '))


def test_workspace_project_link_is_reference_and_duplicate_safe(store):
    created = store.create('owner', os_api.WorkspaceCreate(name='Development'))
    first = store.link(created['id'], 'owner', 'project', 'project-123')
    second = store.link(created['id'], 'owner', 'project', 'project-123')
    assert first['links'] == second['links']
    assert second['linked_counts']['project'] == 1
    unlinked = store.link(created['id'], 'owner', 'project', 'project-123', remove=True)
    assert unlinked['linked_counts']['project'] == 0


def test_studio_view_persists_references_and_rejects_unknown_panel(store):
    created = store.create('owner', os_api.WorkspaceCreate(name='Design'))
    saved = store.save_view(
        created['id'], 'owner',
        os_api.StudioViewBody(name='Default', layout={
            'panels': [{'kind': 'project', 'resource_id': 'existing-project'}],
        }),
    )
    assert saved['layout']['panels'][0]['resource_id'] == 'existing-project'
    updated = store.save_view(
        created['id'], 'owner',
        os_api.StudioViewBody(name='Review', layout={'panels': []}),
        view_id=saved['id'],
    )
    assert updated['name'] == 'Review'
    assert store.views(created['id'], 'owner')[0]['id'] == saved['id']
    with pytest.raises(ValueError):
        store.save_view(
            created['id'], 'owner',
            os_api.StudioViewBody(name='Unsafe', layout={
                'panels': [{'kind': 'dangerous', 'resource_id': 'x'}],
            }),
        )
    with pytest.raises(ValueError):
        store.save_view(
            created['id'], 'owner',
            os_api.StudioViewBody(name='Too many', layout={
                'panels': [{'kind': 'note'}] * 33,
            }),
        )


def test_router_needs_trusted_active_authorized_device(monkeypatch, store):
    class FakeRegistry:
        active = True
        allowed = True

        def is_active(self, device_id):
            return self.active

        def authorize(self, device_id, permission):
            return self.allowed and permission == 'ai:chat'

    registry = FakeRegistry()
    app = FastAPI()
    app.include_router(os_api.workspaces_os_router({
        'device_registry': registry,
        'project_store': None,
    }, store))
    client = TestClient(app)

    monkeypatch.setattr(os_api, 'current_trusted_request', lambda: None)
    assert client.get('/iphone/api/os/workspaces').status_code == 401

    monkeypatch.setattr(
        os_api, 'current_trusted_request',
        lambda: SimpleNamespace(device_id='device-1'),
    )
    registry.active = False
    assert client.get('/iphone/api/os/workspaces').status_code == 401
    registry.active = True
    registry.allowed = False
    assert client.get('/iphone/api/os/workspaces').status_code == 403
    registry.allowed = True
    created = client.post('/iphone/api/os/workspaces', json={
        'name': 'Product Development', 'template_id': 'product'
    })
    assert created.status_code == 201, created.text
    ident = created.json()['workspace']['id']
    assert client.get('/iphone/api/os/workspaces').json()['workspaces'][0]['id'] == ident
    assert client.get(f'/iphone/api/os/workspaces/{ident}/summary').json()['projects'] == []
    assert client.post(f'/iphone/api/os/workspaces/{ident}/links', json={
        'kind': 'file', 'resource_id': 'unverified-file'
    }).status_code == 409
    assert client.get('/iphone/api/os/workspaces/unknown').status_code == 404
