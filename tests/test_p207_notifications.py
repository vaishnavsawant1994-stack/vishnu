"""P2-07 existing NotificationService, approval projection and device privacy regression."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from notifications.service import NotificationService
from security.approvals import ApprovalManager
from security.request_context import TrustedRequestContext, set_trusted_request, reset_trusted_request
from server.notifications_center_api import notifications_center_router


class Registry:
    def __init__(self):
        self.revoked = False
        self.scopes = {'ai:chat'}
        self.values = {}

    def authenticate(self, device, token):
        return not self.revoked and device == 'd1' and token == 'token1'

    def is_active(self, device):
        return not self.revoked and device == 'd1'

    def authorize(self, device, scope):
        return device == 'd1' and scope in self.scopes

    def list(self):
        return [{'id': 'd1', 'revoked': False}]

    def metadata(self, device):
        return self.values

    def set_metadata(self, device, key, val):
        self.values[key] = val
        return True


class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = set_trusted_request(TrustedRequestContext('d1', 'session1'))
        try:
            return await call_next(request)
        finally:
            reset_trusted_request(token)


def setup(tmp_path):
    registry = Registry()
    notifications = NotificationService(tmp_path / 'notifications.sqlite3', registry, start_scheduler=False)
    approvals = ApprovalManager(path=tmp_path / 'approvals.sqlite3')
    runtime = {'device_registry': registry, 'notifications': notifications,
               'agent_executor': SimpleNamespace(approvals=approvals)}
    app = FastAPI()
    app.add_middleware(ContextMiddleware)
    app.include_router(notifications_center_router(runtime))
    client = TestClient(app)
    client.cookies.set('pa_device', 'd1')
    client.cookies.set('pa_token', 'token1')
    return client, registry, notifications, approvals


def test_notification_legacy_migration_pins_dismisses_and_bulk_read(tmp_path):
    path = tmp_path / 'notifications.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE notifications(
            id TEXT PRIMARY KEY,device_id TEXT NOT NULL,dedupe_key TEXT NOT NULL,
            category TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,
            created_at TEXT NOT NULL,read_at TEXT,UNIQUE(device_id,dedupe_key))''')
        con.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?,?,NULL)',
                    ('legacy', 'd1', 'legacy', 'work_completed', 'Completed', 'Good', '2026-10-21T10:00:00Z'))
    registry = Registry()
    service = NotificationService(path, registry, start_scheduler=False)
    try:
        assert len(service.list('d1')) == 1
        assert service.pin('d1', 'legacy', True)
        assert service.list('d1')[0]['pinned_at']
        assert service.mark_all_read('d1') == 1
        assert service.mark_all_read('d1') == 0
        assert service.mark_all_read('other') == 0
        assert service.dismiss('d1', 'legacy')
        assert service.list('d1') == []
        assert not service.detail('other', 'legacy')
        assert service.list('d1', include_dismissed=True)[0]['dismissed_at']
        with sqlite3.connect(path) as con:
            assert con.execute('PRAGMA user_version').fetchone()[0] == 2
    finally:
        service.close()
    again = NotificationService(path, registry, start_scheduler=False)
    try:
        assert again.list('d1') == []
        assert again.list('d1', include_dismissed=True)[0]['pinned_at']
    finally:
        again.close()


def test_real_device_scoped_notification_actions_and_filters(tmp_path):
    client, registry, service, approvals = setup(tmp_path)
    try:
        service._insert('d1', 'n1', 'needs_review', 'Needs your review', 'Governed work is blocked',
                        event_type='work.order.waiting_approval', project_id='p1', priority='high')
        service._insert('d1', 'n2', 'work_completed', 'Work completed', 'Verified workflow',
                        event_type='work.order.completed', project_id='p2')
        service._insert('other', 'n3', 'work_completed', 'Other', 'Hidden')
        response = client.get('/iphone/api/notifications-center')
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['counts']['all'] == 2
        assert data['counts']['unread'] == 2
        assert not any(x['title'] == 'Other' for x in data['notifications'])
        high = client.get('/iphone/api/notifications-center', params={'priority': True}).json()
        assert high['matched_count'] == 1
        scoped = client.get('/iphone/api/notifications-center', params={'project_id': 'p1'}).json()
        assert [x['title'] for x in scoped['notifications']] == ['Needs your review']
        id1 = scoped['notifications'][0]['id']
        assert client.get('/iphone/api/notifications-center/'+id1).status_code == 200
        assert client.post('/iphone/api/notifications-center/'+id1+'/pin', json={'pinned': True}).json()['pinned']
        assert client.post('/iphone/api/notifications-center/'+id1+'/read').status_code == 200
        assert client.post('/iphone/api/notifications-center/read-bulk',
                           json={'scope': 'all'}).json()['marked_read'] == 1
        assert client.get('/iphone/api/notifications-center').json()['counts']['unread'] == 0
        assert client.post('/iphone/api/notifications-center/'+id1+'/dismiss').status_code == 200
        assert client.get('/iphone/api/notifications-center/'+id1).status_code == 404
        assert client.get('/iphone/api/notifications-center').json()['counts']['all'] == 1
        registry.revoked = True
        assert client.get('/iphone/api/notifications-center').status_code == 401
    finally:
        service.close()


def test_canonical_approval_is_not_a_notification_decision(tmp_path):
    client, registry, service, approvals = setup(tmp_path)
    try:
        ticket = approvals.create('execution1', 'external_call',
                                  {'password': 'never expose'}, device_id='d1',
                                  session_id='session1', destination='destination')
        response = client.get('/iphone/api/notifications-center')
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['counts']['pending_approvals'] == 1
        row = next(x for x in data['notifications'] if x['kind'] == 'approval')
        assert row['id'] == 'approval:'+ticket.id
        assert row['read_supported'] is False
        assert 'never expose' not in response.text
        detail = client.get('/iphone/api/notifications-center/approval:'+ticket.id)
        assert detail.status_code == 200
        assert detail.json()['authority'] == 'approval_manager'
        assert client.post('/iphone/api/notifications-center/approval:'+ticket.id+'/read').status_code == 409
        assert client.post('/iphone/api/notifications-center/approval:'+ticket.id+'/dismiss').status_code == 409
        assert client.post('/iphone/api/notifications-center/read-bulk',
                           json={'scope': 'all'}).json()['marked_read'] == 0
        assert approvals.record(ticket.id)['status'] == 'pending'
    finally:
        service.close()


def test_explicit_approval_session_scope_must_match(tmp_path):
    client, _, service, approvals = setup(tmp_path)
    try:
        ticket = approvals.create('execX', 'bounded_tool', {}, device_id='d1', session_id='other')
        response = client.get('/iphone/api/notifications-center')
        assert response.status_code == 200
        assert not any(row['source_id'] == ticket.id for row in response.json()['notifications'])
        assert client.get('/iphone/api/notifications-center/approval:'+ticket.id).status_code == 404
    finally:
        service.close()
