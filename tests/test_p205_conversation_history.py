from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from devices.continuity import ContinuityService
from projects.store import ProjectStore
from workspaces.store import WorkspaceStore
from security.pwa_sessions import PwaSessionStore
from server.pwa_conversations import pwa_conversation_router
from server.pwa_session_middleware import PwaSessionMiddleware


class Devices:
    def is_active(self, device_id):
        return device_id == 'device-1'

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope == 'ai:chat'


def stack(tmp_path):
    continuity = ContinuityService(tmp_path / 'threads.sqlite3')
    projects = ProjectStore(tmp_path / 'projects.sqlite3')
    spaces = WorkspaceStore(tmp_path / 'workspaces.sqlite3')
    sessions = PwaSessionStore(tmp_path / 'sessions.sqlite3', ttl_seconds=600)
    app = FastAPI()
    app.add_middleware(PwaSessionMiddleware, sessions=sessions, device_registry=Devices(), cookie_max_age=600)

    @app.post('/iphone/api/access/password/login')
    def login(response: Response):
        response.set_cookie('pa_device', 'device-1', secure=True, httponly=True, samesite='strict', path='/iphone')
        response.set_cookie('pa_token', 'device-token', secure=True, httponly=True, samesite='strict', path='/iphone')
        return {'ok': True}

    app.include_router(pwa_conversation_router({
        'continuity': continuity, 'device_registry': Devices(),
        'base_project_store': projects, 'workspace_store': spaces,
    }))
    return TestClient(app, base_url='https://testserver'), continuity, projects, spaces


def test_history_pinned_tagged_paginated_with_canonical_ids(tmp_path):
    client, ledger, _, _ = stack(tmp_path)
    ids = [ledger.create_thread(f'Topic {i}') for i in range(55)]
    ledger.append(ids[4], device_id='device-1', kind='user_message',
                  payload={'text': 'Searchable message body'})
    assert client.get('/iphone/api/conversations/history/search').status_code == 401
    client.post('/iphone/api/access/password/login')
    page = client.get('/iphone/api/conversations/history/search?limit=20').json()
    assert len(page['conversations']) == 20
    assert page['has_more']
    token = page['next_cursor']
    next_page = client.get('/iphone/api/conversations/history/search',
                           params={'limit': 20, 'cursor_time': token['updated_at'],
                                   'cursor_id': token['id']}).json()
    assert len(next_page['conversations']) == 20
    assert not {x['id'] for x in page['conversations']}.intersection(
        x['id'] for x in next_page['conversations'])
    assert client.get('/iphone/api/conversations/history/search',
                      params={'q': 'Searchable message'}).json()['conversations'][0]['id'] == ids[4]

    res = client.patch(f'/iphone/api/conversations/{ids[4]}/metadata',
                       json={'pinned': True, 'tags': ['Research', 'Research', 'Review'],
                             'summary': 'Verified summary'})
    assert res.status_code == 200, res.text
    assert res.json()['conversation']['context']['history_tags'] == ['Research', 'Review']
    tagged = client.get('/iphone/api/conversations/history/search',
                        params={'pinned': 'true', 'tag': 'research'}).json()
    assert [x['id'] for x in tagged['conversations']] == [ids[4]]
    assert client.patch(f'/iphone/api/conversations/{ids[4]}/metadata',
                        json={'tags': ['bad\ninjection']}).status_code in {409, 422}
    assert ContinuityService(ledger.path).thread(ids[4])['context']['history_summary'] == 'Verified summary'


def test_organize_same_thread_requires_confirm_and_resolves_real_targets(tmp_path):
    client, ledger, projects, spaces = stack(tmp_path)
    client.post('/iphone/api/access/password/login')
    project = projects.create(name='Vishnu Test Project')
    workspace = spaces.create('owner', name='Test Workspace')
    original = ledger.create_thread('Personal notes')
    ledger.append(original, device_id='device-1', kind='user_message',
                  payload={'text': 'private original full message'})
    url = f'/iphone/api/conversations/{original}/organize'
    assert client.post(url, json={'kind': 'project', 'target_id': project['id']}).status_code == 422
    assert client.post(url, json={'kind': 'project', 'target_id': 'forged', 'confirm': True}).status_code == 404
    moved = client.post(url, json={'kind': 'project', 'target_id': project['id'], 'confirm': True})
    assert moved.status_code == 200, moved.text
    assert moved.json()['conversation']['id'] == original
    assert ledger.thread(original)['context']['project_id'] == project['id']
    assert ledger.events_for_thread(original)[0]['payload']['text'] == 'private original full message'
    linked = client.get(f'/iphone/api/conversations/{original}/related').json()
    assert linked['projects'][0]['name'] == 'Vishnu Test Project'
    updated = client.post(url, json={'kind': 'workspace', 'target_id': workspace['id'], 'confirm': True})
    assert updated.status_code == 200, updated.text
    context = ledger.thread(original)['context']
    assert context['workspace_id'] == workspace['id']
    assert 'project_id' not in context
    assert client.get('/iphone/api/conversations/history/search',
                      params={'kind': 'workspace', 'workspace_id': workspace['id']}).json()['conversations'][0]['id'] == original
    assert len(ledger.all_thread_ids()) == 1


def test_archive_restore_detail_export_and_no_hidden_history_write(tmp_path):
    client, ledger, _, _ = stack(tmp_path)
    client.post('/iphone/api/access/password/login')
    ident = ledger.create_thread('Archive candidate')
    ledger.append(ident, device_id='device-1', kind='user_message', payload={'text':'Remember original history'})
    assert client.post(f'/iphone/api/conversations/{ident}/archive').status_code == 200
    assert client.get('/iphone/api/conversations/history/search',
                      params={'status': 'archived'}).json()['conversations'][0]['id'] == ident
    detail = client.get(f'/iphone/api/conversations/{ident}/history-detail')
    assert detail.status_code == 200
    assert detail.json()['events'][0]['payload']['text'] == 'Remember original history'
    assert client.patch(f'/iphone/api/conversations/{ident}/metadata',
                        json={'pinned': True}).status_code == 409
    assert client.post(f'/iphone/api/conversations/{ident}/organize',
                       json={'kind': 'work', 'confirm': True}).status_code == 409
    assert client.post(f'/iphone/api/conversations/{ident}/restore').json()['status'] == 'restored'
    assert ContinuityService(ledger.path).thread(ident)['closed_at'] is None
    assert client.get(f'/iphone/api/conversations/{ident}/export').status_code == 200
    assert len(ledger.events_for_thread(ident)) == 1


def test_search_validates_bad_filters_and_context_authority(tmp_path):
    client, ledger, _, _ = stack(tmp_path)
    client.post('/iphone/api/access/password/login')
    ident = ledger.create_thread('Safe')
    assert client.get('/iphone/api/conversations/history/search',
                      params={'workspace_id': 'forged'}).status_code == 404
    assert client.get('/iphone/api/conversations/history/search',
                      params={'cursor_id': 'forged'}).status_code == 422
    assert client.get('/iphone/api/conversations/history/search',
                      params={'since': '2026-10-23', 'until': '2026-10-22'}).status_code == 422
    assert client.get(f'/iphone/api/conversations/{ident}/history-detail').status_code == 200


def test_cannot_reassign_primary_project_conversation_and_break_project_pointer(tmp_path):
    client, ledger, projects, _ = stack(tmp_path)
    client.post('/iphone/api/access/password/login')
    project = projects.create(name='Primary Project')
    thread_id = ledger.create_thread('Primary Thread', context={
        'conversation_kind': 'project', 'project_id': project['id'],
    })
    projects.update(project['id'], {'conversation_id': thread_id})
    response = client.post(f'/iphone/api/conversations/{thread_id}/organize',
                           json={'kind': 'personal', 'confirm': True})
    assert response.status_code == 409
    assert ledger.thread(thread_id)['context']['project_id'] == project['id']
    assert projects.get(project['id'])['conversation_id'] == thread_id
