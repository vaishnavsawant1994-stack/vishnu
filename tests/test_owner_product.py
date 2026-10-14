from types import SimpleNamespace
import io
import zipfile
import time
from pathlib import Path

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from automation.engine import AutomationEngine
from core.preferences import Preferences
from devices.registry import DeviceRegistry
from knowledge.store import KnowledgeStore
from memory.second_brain import SecondBrain
from memory.store import MemoryStore
from qualification.program import P3QualificationProgram
from projects.store import ProjectStore
from server.owner_product import owner_product_router
from server.owner_product import stage_owner_data_deletion
from recovery.backup import BackupService
from notifications.service import NotificationService
from security.request_context import TrustedRequestContext, set_trusted_request, reset_trusted_request


class Executor:
    def __init__(self):
        self.cancelled = []

    def chat(self, prompt, cancel_event=None, **kwargs):
        return f'done:{prompt}'

    def cancel_active_turns(self, *, reason='emergency_stop'):
        self.cancelled.append(reason)
        return 1


class Models:
    def status(self):
        return {'state': 'configured', 'primary_provider': 'test'}


class Tools:
    emergency_stop = False

    def all(self):
        return []

    def set_emergency_stop(self, enabled):
        self.emergency_stop = bool(enabled)
        return self.emergency_stop


class SessionStoreProbe:
    def __init__(self):
        self.revoked_devices = []

    def revoke_device(self, device_id):
        self.revoked_devices.append(device_id)
        return 1


class GatewayProbe:
    def __init__(self):
        self.disconnected = []

    def disconnect(self, device_id):
        self.disconnected.append(device_id)


def make_client(tmp_path, *, reauthenticated_at=None):
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3')
    device, token = registry.enroll('Owner iPhone', 'ios-pwa')
    registry.set_permissions(device['id'], registry.OWNER_SCOPES)
    memory = MemoryStore(tmp_path / 'memory.sqlite3')
    executor = Executor()
    automations = AutomationEngine(tmp_path / 'workflows.sqlite3', executor=executor)
    runtime = {
        'device_registry': registry,
        'memory': memory,
        'second_brain': SecondBrain(memory),
        'knowledge': KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects'),
        'project_store': ProjectStore(tmp_path / 'projects.sqlite3'),
        'automations': automations,
        'executor': executor,
        'pwa_sessions': SessionStoreProbe(),
        'cloud_sessions': SessionStoreProbe(),
        'device_gateway': GatewayProbe(),
        'p3_qualification': P3QualificationProgram(tmp_path / 'qualification.sqlite3'),
        'models': Models(),
        'tools': Tools(),
        'integrations': SimpleNamespace(list=lambda: []),
        'future_intelligence': SimpleNamespace(status=lambda: {}),
        'preferences': Preferences(tmp_path / 'preferences.json'),
        'settings': SimpleNamespace(owner_google_email='', google_signin_client_id=''),
    }
    runtime['notifications'] = NotificationService(tmp_path / 'notifications.sqlite3', registry, owner_preferences=runtime['preferences'], start_scheduler=False)
    app = FastAPI()
    fresh_at = time.time() if reauthenticated_at is None else reauthenticated_at
    class TrustedContextMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            device_id = request.cookies.get('pa_device') or device['id']
            token = set_trusted_request(TrustedRequestContext(device_id, 'test-session', fresh_at))
            try:
                return await call_next(request)
            finally:
                reset_trusted_request(token)
    app.add_middleware(TrustedContextMiddleware)
    app.include_router(owner_product_router(runtime))
    client = TestClient(app, base_url='https://testserver')
    client.cookies.set('pa_device', device['id'])
    client.cookies.set('pa_token', token)
    return client, runtime, device


def test_owner_memory_lifecycle_and_audit(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    created = client.post('/iphone/api/memory', json={
        'type': 'project',
        'subject': 'Aurora',
        'content': 'Aurora is active',
        'sensitivity': 'normal',
    })
    assert created.status_code == 200
    memory_id = created.json()['id']
    assert client.get('/iphone/api/memory/graph').json()['nodes'][0]['id'] == memory_id
    assert client.get('/iphone/api/memory/tree').json()['roots'][0]['id'] == memory_id
    corrected = client.patch(f'/iphone/api/memory/{memory_id}', json={'content': 'Aurora is paused'})
    assert corrected.status_code == 200
    assert corrected.json()['content'] == 'Aurora is paused'
    assert client.get('/iphone/api/memory/export').json()['memories'][0]['id'] == memory_id
    assert client.delete(f'/iphone/api/memory/{memory_id}').status_code == 409
    assert client.delete(f'/iphone/api/memory/{memory_id}?confirm=true').status_code == 200
    actions = [row['action'] for row in runtime['memory'].audit_entries('owner-product')]
    assert 'memory.created' in actions
    assert 'memory.corrected' in actions
    assert 'memory.removed' in actions


def test_owner_memory_preferences_removal_restore_and_context_gate(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    created = client.post('/iphone/api/memory', json={
        'type': 'preference', 'subject': 'Writing', 'content': 'Use clear steps',
    })
    memory_id = created.json()['id']
    assert runtime['second_brain'].context('clear steps')
    assert client.get('/iphone/api/memory/preferences').json() == {
        'memory_enabled': True, 'review_before_saving': True,
    }
    assert client.patch('/iphone/api/memory/preferences', json={
        'memory_enabled': False, 'review_before_saving': False,
    }).json() == {'memory_enabled': False, 'review_before_saving': False}
    assert runtime['second_brain'].context('clear steps') == []
    assert client.get('/iphone/api/memory?q=clear').json()['memories'][0]['id'] == memory_id

    assert client.delete(f'/iphone/api/memory/{memory_id}?confirm=true').status_code == 200
    assert client.get('/iphone/api/memory').json()['memories'] == []
    assert client.get('/iphone/api/memory/removed').json()['memories'][0]['id'] == memory_id
    restored = client.post(f'/iphone/api/memory/{memory_id}/restore')
    assert restored.status_code == 200
    assert client.get('/iphone/api/memory').json()['memories'][0]['id'] == memory_id
    assert client.delete(f'/iphone/api/memory/{memory_id}/permanent?confirm=true').status_code == 200
    assert client.get('/iphone/api/memory/removed').json()['memories'] == []


def test_project_memory_scope_is_validated_and_excluded_from_global_retrieval(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    project = runtime['project_store'].create(name='Atlas')
    created = client.post('/iphone/api/memory', json={
        'type': 'decision', 'subject': 'Atlas decision',
        'content': 'Keep Atlas workspace scoped.', 'scope': 'project',
        'project_id': project['id'],
    })
    assert created.status_code == 200
    memory_id = created.json()['id']
    assert runtime['second_brain'].context('Keep Atlas workspace scoped.') == []
    assert runtime['second_brain'].context('Keep Atlas workspace scoped.', project_id=project['id'])
    assert client.patch(f'/iphone/api/memory/{memory_id}', json={
        'scope': 'project', 'project_id': 'not-authorized-or-missing',
    }).status_code == 404
    assert runtime['second_brain'].context('Keep Atlas workspace scoped.') == []
    assert client.patch(f'/iphone/api/memory/{memory_id}', json={'scope': 'personal'}).status_code == 200
    assert runtime['second_brain'].context('Keep Atlas workspace scoped.')


def test_owner_api_refuses_to_create_or_mark_durable_never_store_memory(tmp_path):
    client, runtime, _ = make_client(tmp_path)

    refused = client.post('/iphone/api/memory', json={
        'type': 'fact',
        'subject': 'Temporary secret',
        'content': 'Do not retain this',
        'sensitivity': 'never_store',
    })
    assert refused.status_code == 409
    assert runtime['memory'].graph()['nodes'] == []

    created = client.post('/iphone/api/memory', json={
        'type': 'fact', 'subject': 'Stored', 'content': 'Owner chose to retain this',
    })
    memory_id = created.json()['id']
    update = client.patch(
        f'/iphone/api/memory/{memory_id}', json={'sensitivity': 'never_store'}
    )
    assert update.status_code == 409
    assert runtime['memory'].get(memory_id)['sensitivity'] == 'normal'


def test_owner_knowledge_lifecycle_and_citations(tmp_path):
    client, _, _ = make_client(tmp_path)
    created = client.post('/iphone/api/knowledge', json={
        'filename': 'facts.txt',
        'text': 'The approved launch city is Berlin.',
        'source': 'owner:test-case',
    })
    assert created.status_code == 200
    document_id = created.json()['id']
    search = client.get('/iphone/api/knowledge/search?q=launch+city').json()['results'][0]
    assert search['citation']['document_id'] == document_id
    assert search['citation']['source'] == 'owner:test-case'
    assert client.patch(f'/iphone/api/knowledge/{document_id}', json={'title': 'Launch facts'}).json()['title'] == 'Launch facts'
    assert client.delete(f'/iphone/api/knowledge/{document_id}').status_code == 409
    assert client.delete(f'/iphone/api/knowledge/{document_id}?confirm=true').status_code == 200


def test_owner_knowledge_collections_availability_and_unfetched_links(tmp_path):
    client, _, _ = make_client(tmp_path)
    collection = client.post('/iphone/api/knowledge/collections', json={
        'title': 'Personal AI project', 'description': 'Project reference files',
    })
    assert collection.status_code == 201, collection.text
    collection_id = collection.json()['id']
    document = client.post('/iphone/api/knowledge', json={
        'filename': 'brief.txt', 'title': 'Launch brief',
        'text': 'The launch brief includes the workspace review checklist.',
        'item_kind': 'note', 'collection_id': collection_id,
    })
    assert document.status_code == 200, document.text
    document_id = document.json()['id']
    assert client.get('/iphone/api/knowledge/collections').json()['collections'][0]['item_count'] == 1
    assert client.get('/iphone/api/knowledge/search?q=workspace+review').json()['results']
    assert client.patch(f'/iphone/api/knowledge/{document_id}/availability', json={
        'available_to_vishnu': False,
    }).status_code == 200
    assert client.get('/iphone/api/knowledge/search?q=workspace+review').json()['results'] == []
    assert client.patch(f'/iphone/api/knowledge/{document_id}/availability', json={
        'available_to_vishnu': True,
    }).status_code == 200
    assert client.get('/iphone/api/knowledge/search?q=workspace+review').json()['results']

    link = client.post('/iphone/api/knowledge', json={
        'filename': 'saved-link.txt', 'title': 'Vishnu reference', 'item_kind': 'link',
        'link_url': 'https://example.com/reference',
    })
    assert link.status_code == 200, link.text
    assert link.json()['metadata']['link_status'] == 'saved_only'
    assert link.json()['metadata']['available_to_vishnu'] is False
    assert client.patch(f"/iphone/api/knowledge/{link.json()['id']}/availability", json={
        'available_to_vishnu': True,
    }).status_code == 409
    deleted = client.delete(f'/iphone/api/knowledge/collections/{collection_id}?confirm=true')
    assert deleted.json()['items_retained'] is True
    assert client.get(f'/iphone/api/knowledge/{document_id}').status_code == 200


def test_owner_markdown_note_editor_links_versions_and_portable_export(tmp_path):
    client, _, _ = make_client(tmp_path)
    target = client.post('/iphone/api/knowledge/notes', json={
        'title': 'Project Decisions', 'content': '# Approved\nLaunch on Friday.', 'tags': ['project', 'launch'],
    })
    assert target.status_code == 201, target.text
    target_id = target.json()['id']
    source = client.post('/iphone/api/knowledge/notes', json={
        'title': 'Meeting', 'content': 'See [[Project Decisions|the decision]] and [[Unwritten Note]].',
    })
    assert source.status_code == 201, source.text
    source_id = source.json()['id']
    assert client.get('/iphone/api/knowledge/notes?q=Meeting').json()['notes'][0]['content'].startswith('See')
    links = client.get(f'/iphone/api/knowledge/notes/{source_id}/links').json()
    assert links['outgoing'] == [{'id': target_id, 'title': 'Project Decisions', 'label': 'the decision'}]
    assert links['unresolved'] == [{'target': 'Unwritten Note', 'label': 'Unwritten Note'}]

    update = client.put(f'/iphone/api/knowledge/notes/{source_id}', json={
        'title': 'Meeting Notes', 'content': 'Updated [[Project Decisions]].', 'tags': ['meeting'],
    })
    assert update.status_code == 200, update.text
    assert update.json()['version'] == 2
    assert update.json()['content'] == 'Updated [[Project Decisions]].'
    archive = client.get('/iphone/api/knowledge/portable-export')
    assert archive.status_code == 200
    assert archive.headers['content-type'].startswith('application/zip')
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert 'manifest.json' in bundle.namelist()
        assert any(path.startswith(f'notes/{target_id}/') for path in bundle.namelist())
    deleted = client.delete(f'/iphone/api/knowledge/{target_id}?confirm=true')
    assert deleted.status_code == 200
    restored = client.post('/iphone/api/knowledge/portable-import', content=archive.content, headers={'Content-Type': 'application/zip'})
    assert restored.status_code == 200, restored.text
    assert restored.json()['imported_count'] == 1
    assert {item['title'] for item in client.get('/iphone/api/knowledge/notes').json()['notes']} == {'Project Decisions', 'Meeting Notes'}


def test_note_endpoints_preserve_device_access_boundaries(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    limited, limited_token = runtime['device_registry'].enroll('Read only browser', 'web')
    runtime['device_registry'].set_permissions(limited['id'], ['knowledge:read'])
    limited_client = client.__class__(client.app, base_url='https://testserver')
    limited_client.cookies.set('pa_device', limited['id'])
    limited_client.cookies.set('pa_token', limited_token)

    hidden = client.post('/iphone/api/knowledge/notes', json={
        'title': 'Private Note', 'content': 'owner only', 'access_class': 'private',
    }).json()
    assert limited_client.get('/iphone/api/knowledge/notes').json()['notes'] == []
    assert limited_client.get(f"/iphone/api/knowledge/notes/{hidden['id']}/links").status_code == 404
    assert limited_client.post('/iphone/api/knowledge/notes', json={'title': 'Blocked'}).status_code == 403
    archive = client.get('/iphone/api/knowledge/portable-export')
    assert limited_client.post('/iphone/api/knowledge/portable-import', content=archive.content, headers={'Content-Type': 'application/zip'}).status_code == 403


def test_owner_can_manage_other_device_and_revocation_is_immediate(tmp_path):
    client, runtime, owner = make_client(tmp_path)
    other, other_token = runtime['device_registry'].enroll('Desktop browser', 'web')

    listed = client.get('/iphone/api/devices')
    assert listed.status_code == 200
    assert listed.json()['current_device_id'] == owner['id']
    assert {row['id'] for row in listed.json()['devices']} == {owner['id'], other['id']}

    scopes = client.patch(
        f"/iphone/api/devices/{other['id']}/permissions",
        json={'scopes': ['ai:chat', 'memory:read']},
    )
    assert scopes.status_code == 200
    assert scopes.json()['scopes'] == ['ai:chat', 'memory:read']
    revoked = client.post(f"/iphone/api/devices/{other['id']}/revoke", json={'confirm': True})
    assert revoked.status_code == 200
    assert runtime['device_registry'].authenticate(other['id'], other_token) is False
    assert runtime['pwa_sessions'].revoked_devices == [other['id']]
    assert runtime['cloud_sessions'].revoked_devices == [other['id']]
    assert runtime['device_gateway'].disconnected == [other['id']]
    assert revoked.json()['revoked_sessions'] == {'pwa_sessions': 1, 'cloud_sessions': 1}


def test_workflow_permission_revocation_cancels_device_bound_work(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    other, _ = runtime['device_registry'].enroll('Workflow browser', 'web')
    runtime['device_registry'].set_permissions(other['id'], {'ai:chat', 'workflow:write'})

    cancelled = []
    runtime['automations'].cancel_device_runs = (
        lambda device_id, *, reason='device_revoked':
        cancelled.append((device_id, reason)) or 2
    )

    response = client.patch(
        f"/iphone/api/devices/{other['id']}/permissions",
        json={'scopes': ['ai:chat']},
    )

    assert response.status_code == 200
    assert response.json()['cancelled_turns'] == 0
    assert response.json()['cancelled_workflows'] == 2
    assert cancelled == [(other['id'], 'workflow_permission_revoked')]


def test_ui_preferences_are_scoped_to_the_trusted_device_and_persist(tmp_path):
    client, runtime, owner = make_client(tmp_path)

    defaults = client.get('/iphone/api/preferences')
    assert defaults.json() == {
        'continuous_voice': True,
        'voice_rate': 1.0,
        'quiet_hours': True,
        'privacy_memory_enabled': True,
        'privacy_review_before_saving': True,
        'privacy_allow_project_context_general': False,
        'privacy_save_conversations': True,
        'privacy_retention': 'until_deleted',
        'privacy_share_anonymous_usage_data': False,
        'profile_display_name': '',
        'appearance_theme': 'dark',
        'appearance_accent': 'blue',
        'appearance_density': 'comfortable',
        'appearance_motion': 'standard',
        'appearance_text_size': 'default',
        'chat_enter_sends': True,
        'chat_keep_composer_visible': True,
        'chat_response_detail': 'detailed',
        'chat_response_style': 'clear_step_by_step',
        'chat_show_sources': True,
        'chat_show_timestamps': True,
        'chat_show_actions': True,
        'chat_message_spacing': 'comfortable',
        'chat_new_context': 'general',
        'chat_project_context_enabled': False,
        'locale_app_language': 'en',
        'locale_region': 'IN',
        'locale_time_zone': 'Asia/Kolkata',
        'locale_use_device_time_zone': False,
        'locale_date_format': 'day_month_year',
        'locale_time_format': '12h',
        'locale_week_start': 'monday',
        'locale_number_format': 'indian',
        'locale_temperature': 'celsius',
        'locale_measurement': 'metric',
        'pinned_sidebar_items': [],
    }
    updated = client.put('/iphone/api/preferences', json={
        'continuous_voice': False,
        'voice_rate': 1.15,
        'quiet_hours': False,
        'locale_region': 'US',
        'locale_time_zone': 'America/New_York',
        'locale_date_format': 'numeric',
        'locale_number_format': 'western',
        'pinned_sidebar_items': ['chat:conversation-1', 'project:project-1'],
    })
    assert updated.status_code == 200
    assert client.get('/iphone/api/preferences').json() == updated.json()
    assert 'ui.preferences' in runtime['device_registry'].metadata(owner['id'])
    assert client.get('/iphone/api/preferences').json()['locale_region'] == 'US'

    other, token = runtime['device_registry'].enroll('Other browser', 'web')
    other_client = TestClient(client.app, base_url='https://testserver')
    other_client.cookies.set('pa_device', other['id'])
    other_client.cookies.set('pa_token', token)
    assert other_client.get('/iphone/api/preferences').json()['continuous_voice'] is True
    assert other_client.get('/iphone/api/preferences').json()['privacy_memory_enabled'] is True


def test_profile_metadata_account_id_and_photo_use_authenticated_owner_services(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    metadata = client.get('/iphone/api/profile/metadata')
    assert metadata.status_code == 200
    profile = metadata.json()
    assert profile['account_id_masked'].startswith('•••• ')
    assert 'account_id' not in profile
    copied = client.post('/iphone/api/profile/account-id/copy', json={})
    assert copied.status_code == 200
    assert copied.json()['account_id'].endswith(profile['account_id_masked'][-4:])
    assert client.get('/iphone/api/profile/metadata').json()['account_id_masked'] == profile['account_id_masked']

    # A valid 1×1 PNG keeps this endpoint test focused on the upload path.
    pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=='
    uploaded = client.put('/iphone/api/profile/avatar', json={'media_type': 'image/png', 'data_base64': pixel})
    assert uploaded.status_code == 200
    assert client.get('/iphone/api/profile/metadata').json()['avatar_available'] is True
    avatar_response = client.get('/iphone/api/profile/avatar')
    assert avatar_response.status_code == 200, avatar_response.text
    assert avatar_response.headers['content-type'] == 'image/png'

    unauthorized = TestClient(client.app, base_url='https://testserver')
    assert unauthorized.get('/iphone/api/profile/metadata').status_code == 401
    assert unauthorized.post('/iphone/api/profile/account-id/copy', json={}).status_code == 401


def test_profile_update_persists_and_validates_names(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    payload = {'first_name': 'Taylor', 'last_name': 'Rao', 'display_name': 'Tay'}
    assert client.put('/iphone/api/profile', json=payload).status_code == 200
    metadata = client.get('/iphone/api/profile/metadata').json()
    assert (metadata['first_name'], metadata['last_name'], metadata['display_name']) == ('Taylor', 'Rao', 'Tay')
    assert runtime['preferences'].get('preferred_name') == 'Tay'
    assert client.put('/iphone/api/profile', json={**payload, 'first_name': '  '}).status_code == 422
    unauthorized = TestClient(client.app, base_url='https://testserver')
    assert unauthorized.put('/iphone/api/profile', json=payload).status_code == 401


def test_notification_preferences_are_authenticated_validated_and_persistent(tmp_path):
    client, runtime, device = make_client(tmp_path)
    loaded = client.get('/iphone/api/notifications/preferences')
    assert loaded.status_code == 200
    prefs = loaded.json()['preferences']
    prefs['events']['needs_review'] = {'enabled': True, 'channels': ['in_app']}
    prefs['quiet_hours'] = {'enabled': True, 'start': '22:00', 'end': '08:00', 'timezone': 'Asia/Kolkata'}
    saved = client.put('/iphone/api/notifications/preferences', json=prefs)
    assert saved.status_code == 200
    assert client.get('/iphone/api/notifications/preferences').json()['preferences'] == prefs
    assert runtime['preferences'].get('notifications_preferences')['events']['needs_review']['channels'] == ['in_app']
    other, _ = runtime['device_registry'].enroll('Other trusted browser', 'web')
    assert runtime['notifications'].preferences(other['id']) == prefs
    invalid = {**prefs, 'events': {**prefs['events'], 'needs_review': {'enabled': True, 'channels': ['email']}}}
    assert client.put('/iphone/api/notifications/preferences', json=invalid).status_code == 422
    unknown = {**prefs, 'quiet_hours': {'enabled': True, 'start': '22:00', 'end': '08:00', 'timezone': 'Mars/Olympus'}}
    assert client.put('/iphone/api/notifications/preferences', json=unknown).status_code == 422
    unauthorized = TestClient(client.app, base_url='https://testserver')
    assert unauthorized.get('/iphone/api/notifications/preferences').status_code == 401
    assert unauthorized.get('/iphone/api/notifications/inbox').status_code == 401


def test_account_deletion_stages_only_the_configured_owner_data_directory(tmp_path):
    data_dir = tmp_path / 'owner-data'
    data_dir.mkdir()
    (data_dir / 'private.sqlite3').write_text('owner data')
    tombstone = stage_owner_data_deletion(data_dir)
    assert not data_dir.exists()
    assert tombstone.is_dir()
    assert (tombstone / 'private.sqlite3').read_text() == 'owner data'
    with pytest.raises(ValueError, match='unsafe'):
        stage_owner_data_deletion(Path('/'))


def test_privacy_preferences_persist_and_validate_for_authenticated_device(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    response = client.put('/iphone/api/preferences', json={
        'continuous_voice': True,
        'voice_rate': 1.0,
        'quiet_hours': True,
        'privacy_memory_enabled': False,
        'privacy_review_before_saving': True,
        'privacy_allow_project_context_general': False,
        'privacy_save_conversations': True,
        'privacy_retention': 'until_deleted',
        'privacy_share_anonymous_usage_data': False,
    })
    assert response.status_code == 200
    saved = client.get('/iphone/api/preferences').json()
    assert saved['privacy_memory_enabled'] is False
    assert saved['privacy_save_conversations'] is True
    assert saved['privacy_share_anonymous_usage_data'] is False
    updated = client.put('/iphone/api/preferences', json={**saved, 'appearance_theme': 'system', 'appearance_accent': 'teal', 'chat_enter_sends': False, 'chat_message_spacing': 'compact'})
    assert updated.status_code == 200
    persisted = client.get('/iphone/api/preferences').json()
    updated_name = client.put('/iphone/api/preferences', json={**persisted, 'profile_display_name': 'Vaishnav'})
    assert updated_name.status_code == 200
    assert client.get('/iphone/api/preferences').json()['profile_display_name'] == 'Vaishnav'
    assert runtime['preferences'].get('preferred_name') == 'Vaishnav'
    assert persisted['appearance_theme'] == 'system'
    assert persisted['appearance_accent'] == 'teal'
    assert persisted['chat_enter_sends'] is False
    assert persisted['chat_message_spacing'] == 'compact'

    invalid = client.put('/iphone/api/preferences', json={
        **saved,
        'privacy_retention': 'forever-unless-deleted-by-admin',
    })
    assert invalid.status_code == 422
    unsupported = client.put('/iphone/api/preferences', json={
        **saved,
        'privacy_allow_project_context_general': True,
    })
    assert unsupported.status_code == 422


def test_privacy_export_is_authenticated_and_contains_only_supported_data(tmp_path):
    client, _, _ = make_client(tmp_path)
    unauthenticated = TestClient(client.app, base_url='https://testserver')
    assert unauthenticated.get('/iphone/api/privacy/export').status_code == 401

    response = client.get('/iphone/api/privacy/export')
    assert response.status_code == 200
    payload = response.json()
    assert payload['format'] == 'vishnu-account-data-v1'
    assert set(payload) == {'format', 'exported_at', 'preferences', 'memories', 'knowledge', 'conversations'}
    assert 'password' not in str(payload).lower()


def test_ui_preferences_reject_unsafe_voice_rate(tmp_path):
    client, _, _ = make_client(tmp_path)

    response = client.put('/iphone/api/preferences', json={
        'continuous_voice': True,
        'voice_rate': 4,
        'quiet_hours': True,
    })

    assert response.status_code == 422


def test_ui_preferences_validate_language_region_and_iana_time_zone(tmp_path):
    client, _, _ = make_client(tmp_path)
    base = client.get('/iphone/api/preferences').json()
    assert client.put('/iphone/api/preferences', json={**base, 'locale_time_zone': 'Not/A_Zone'}).status_code == 422
    assert client.put('/iphone/api/preferences', json={**base, 'locale_app_language': 'hi'}).status_code == 422
    assert client.put('/iphone/api/preferences', json={**base, 'locale_region': 'XX'}).status_code == 422


def test_p3_stage_evidence_endpoint_records_but_does_not_self_award(tmp_path):
    client, _, _ = make_client(tmp_path)
    started = client.post('/iphone/api/qualification/stages', json={
        'stage': 'P3.5',
        'evidence_class': 'real_device',
        'environment': {'os': 'iOS 26.6.1', 'browser': 'Safari'},
    })
    assert started.status_code == 200
    session_id = started.json()['session_id']
    trial = client.post(f'/iphone/api/qualification/sessions/{session_id}/trials', json={
        'task': 'recall owner project',
        'passed': True,
        'latency_ms': 120,
        'metrics': {
            'recall_relevant': True,
            'conflict_resolved': True,
            'temporal_answer_correct': True,
            'source_traceable': True,
            'fabricated_memory': False,
            'deleted_history_on_supersession': False,
        },
        'evidence': {'artifact': 'owner-screen-recording-1'},
    })
    assert trial.status_code == 200
    client.post(f'/iphone/api/qualification/sessions/{session_id}/finish', json={'duration_seconds': 60})
    result = client.get('/iphone/api/qualification').json()['P3.5']
    assert result['trials'] == 1
    assert result['passed'] is False
    assert any('need 50 trials' in item for item in result['failures'])


def test_limited_trusted_device_cannot_read_sensitive_memory_or_private_knowledge(tmp_path):
    owner_client, runtime, _ = make_client(tmp_path)
    sensitive = owner_client.post('/iphone/api/memory', json={
        'type': 'fact',
        'subject': 'Private fact',
        'content': 'Owner-only memory',
        'sensitivity': 'sensitive',
    })
    assert sensitive.status_code == 200
    private = owner_client.post('/iphone/api/knowledge', json={
        'filename': 'private.txt',
        'text': 'Owner-only document',
        'access_class': 'private',
    })
    assert private.status_code == 200

    limited, token = runtime['device_registry'].enroll('Limited browser', 'web')
    limited_client = TestClient(owner_client.app, base_url='https://testserver')
    limited_client.cookies.set('pa_device', limited['id'])
    limited_client.cookies.set('pa_token', token)

    assert limited_client.get('/iphone/api/memory').json()['memories'] == []
    assert limited_client.get('/iphone/api/knowledge').json()['documents'] == []
    assert limited_client.get(f"/iphone/api/memory/{sensitive.json()['id']}").status_code == 404
    assert limited_client.get(f"/iphone/api/knowledge/{private.json()['id']}").status_code == 404
    assert limited_client.post('/iphone/api/memory', json={
        'type': 'fact', 'subject': 'Blocked', 'content': 'Sensitive', 'sensitivity': 'sensitive',
    }).status_code == 403
    assert limited_client.get('/iphone/api/qualification').status_code == 403


def test_legacy_owner_pwa_permissions_migrate_without_new_login(tmp_path):
    path = tmp_path / 'devices.sqlite3'
    registry = DeviceRegistry(path)
    device, token = registry.enroll('Legacy owner iPhone', 'ios-pwa')
    with registry._con() as con:
        con.execute('DELETE FROM device_permissions WHERE device_id=?', (device['id'],))
    restarted = DeviceRegistry(path)
    assert restarted.authenticate(device['id'], token) is True
    assert restarted.authorize(device['id'], 'device:admin') is True


def test_retention_removes_memory_and_vector(tmp_path):
    class Vector:
        def __init__(self): self.deleted = []
        def delete(self, memory_id): self.deleted.append(memory_id)

    store = MemoryStore(tmp_path / 'retention.sqlite3')
    vector = Vector()
    brain = SecondBrain(store, vector_store=vector)
    memory_id = store.remember(type='note', subject='old', content='old', source='test')
    with store.con() as con:
        con.execute("UPDATE memories SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (memory_id,))
    result = brain.apply_retention(older_than_days=1, dry_run=False)
    assert result['matched'] == 1
    assert store.get(memory_id) is None
    assert vector.deleted == [memory_id]


def test_stage8_owner_emergency_stop_cancels_canonical_turns(tmp_path):
    client, runtime, _ = make_client(tmp_path)

    stopped = client.post('/iphone/api/system/emergency-stop', json={'enabled': True})
    assert stopped.status_code == 200
    assert runtime['tools'].emergency_stop is True
    assert runtime['executor'].cancelled == ['emergency_stop']

    resumed = client.post('/iphone/api/system/emergency-stop', json={'enabled': False})
    assert resumed.status_code == 200
    assert runtime['tools'].emergency_stop is False
    assert runtime['executor'].cancelled == ['emergency_stop']


def test_stage8_stale_reauthentication_blocks_security_controls(tmp_path):
    client, runtime, _ = make_client(tmp_path, reauthenticated_at=time.time() - 1000)
    other, _ = runtime['device_registry'].enroll('Other', 'web')

    permissions = client.patch(
        f"/iphone/api/devices/{other['id']}/permissions",
        json={'scopes': ['ai:chat']},
    )
    assert permissions.status_code == 401
    assert permissions.json()['detail']['code'] == 'reauthentication_required'

    revoke = client.post(f"/iphone/api/devices/{other['id']}/revoke", json={'confirm': True})
    assert revoke.status_code == 401
    assert runtime['device_registry'].is_active(other['id']) is True

    runtime['tools'].set_emergency_stop(True)
    release = client.post('/iphone/api/system/emergency-stop', json={'enabled': False})
    assert release.status_code == 401
    assert runtime['tools'].emergency_stop is True

    stop_again = client.post('/iphone/api/system/emergency-stop', json={'enabled': True})
    assert stop_again.status_code == 200
    assert runtime['tools'].emergency_stop is True


def test_stage8_owner_manual_workflow_retry_reuses_one_durable_run(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    created = client.post('/iphone/api/workflows', json={
        'title': 'Idempotent owner run',
        'trigger': {'type': 'manual'},
        'steps': [{'kind': 'set', 'key': 'ok', 'value': True}],
    })
    assert created.status_code == 200
    workflow_id = created.json()['id']

    missing = client.post(f'/iphone/api/workflows/{workflow_id}/run', json={'context': {}})
    assert missing.status_code == 422

    body = {'context': {'source': 'owner-ui'}, 'idempotency_key': 'owner-run-request-0001'}
    first = client.post(f'/iphone/api/workflows/{workflow_id}/run', json=body)
    second = client.post(f'/iphone/api/workflows/{workflow_id}/run', json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['run_id'] == second.json()['run_id']
    matching = [row for row in runtime['automations'].runs(workflow_id, 20) if row['idempotency_key'] == body['idempotency_key']]
    assert len(matching) == 1


def test_stage8_owner_workflow_payloads_are_bounded(tmp_path):
    client, _, _ = make_client(tmp_path)
    nested = {}
    cursor = nested
    for _ in range(12):
        cursor['next'] = {}
        cursor = cursor['next']

    create = client.post('/iphone/api/workflows', json={
        'title': 'nested',
        'trigger': nested,
        'steps': [{'kind': 'set', 'key': 'ok', 'value': True}],
    })
    assert create.status_code == 413

    valid = client.post('/iphone/api/workflows', json={
        'title': 'valid',
        'trigger': {'type': 'manual'},
        'steps': [{'kind': 'set', 'key': 'ok', 'value': True}],
    })
    assert valid.status_code == 200
    run = client.post(
        f"/iphone/api/workflows/{valid.json()['id']}/run",
        json={'context': nested, 'idempotency_key': 'owner-run-request-0002'},
    )
    assert run.status_code == 413


def test_stage8_owner_structured_metadata_is_bounded(tmp_path):
    client, _, _ = make_client(tmp_path)
    nested = {}
    cursor = nested
    for _ in range(12):
        cursor['next'] = {}
        cursor = cursor['next']

    knowledge = client.post('/iphone/api/knowledge', json={
        'filename': 'bounded.txt',
        'text': 'safe content',
        'metadata': nested,
    })
    assert knowledge.status_code == 413

    qualification = client.post('/iphone/api/qualification/stages', json={
        'stage': 'P3.5',
        'evidence_class': 'real_device',
        'environment': nested,
    })
    assert qualification.status_code == 413


def test_stage8_owner_workflow_read_respects_persisted_device_session_binding(tmp_path):
    client, runtime, owner = make_client(tmp_path)
    owner_token = client.cookies.get('pa_token')
    engine = runtime['automations']
    workflow_id = engine.create_workflow(
        'Stage8 owner-bound visibility',
        {'type': 'manual'},
        [{'kind': 'set', 'key': 'stage8', 'value': 'owner-only-run'}],
    )
    run_id = engine.run_workflow(
        workflow_id,
        background=False,
        owner_id='owner',
        device_id=owner['id'],
        session_id='test-session',
        idempotency_key='stage8-owner-visibility-run',
    )

    own = client.get('/iphone/api/workflows')
    assert own.status_code == 200
    assert run_id in {row['id'] for row in own.json()['runs']}

    foreign, foreign_token = runtime['device_registry'].enroll('Foreign workflow browser', 'web')
    runtime['device_registry'].set_permissions(
        foreign['id'],
        {'workflow:read', 'workflow:approve'},
    )
    client.cookies.set('pa_device', foreign['id'])
    client.cookies.set('pa_token', foreign_token)

    foreign_list = client.get('/iphone/api/workflows')
    assert foreign_list.status_code == 200
    assert run_id not in {row['id'] for row in foreign_list.json()['runs']}

    foreign_approve = client.post(f'/iphone/api/workflows/runs/{run_id}/approve')
    foreign_reject = client.post(f'/iphone/api/workflows/runs/{run_id}/reject')
    for response in (foreign_approve, foreign_reject):
        assert response.status_code == 403
        assert run_id not in response.text
        assert 'not waiting' not in response.text.lower()

    # Positive control: the correctly bound owner gets the real run-state answer.
    client.cookies.set('pa_device', owner['id'])
    client.cookies.set('pa_token', owner_token)
    own_approve = client.post(f'/iphone/api/workflows/runs/{run_id}/approve')
    assert own_approve.status_code == 409
    assert 'not waiting' in own_approve.text.lower()


def test_stage8_owner_workflow_approval_state_hidden_from_foreign_device(tmp_path):
    client, runtime, owner = make_client(tmp_path)
    owner_token = client.cookies.get('pa_token')
    engine = runtime['automations']
    workflow_id = engine.create_workflow(
        'Stage8 owner-bound approval state',
        {'type': 'manual'},
        [{'kind': 'set', 'key': 'stage8', 'value': 'completed'}],
    )
    run_id = engine.run_workflow(
        workflow_id,
        background=False,
        owner_id='owner',
        device_id=owner['id'],
        session_id='test-session',
        idempotency_key='stage8-owner-approval-state',
    )

    foreign, foreign_token = runtime['device_registry'].enroll('Foreign approval browser', 'web')
    runtime['device_registry'].set_permissions(foreign['id'], {'workflow:approve'})
    client.cookies.set('pa_device', foreign['id'])
    client.cookies.set('pa_token', foreign_token)

    approve = client.post(f'/iphone/api/workflows/runs/{run_id}/approve')
    reject = client.post(f'/iphone/api/workflows/runs/{run_id}/reject')
    for response in (approve, reject):
        assert response.status_code == 403
        assert run_id not in response.text
        assert 'not waiting' not in response.text.lower()

    client.cookies.set('pa_device', owner['id'])
    client.cookies.set('pa_token', owner_token)
    own = client.post(f'/iphone/api/workflows/runs/{run_id}/approve')
    assert own.status_code == 409
    assert 'not waiting' in own.text.lower()


def test_owner_backup_create_verify_and_download_are_authenticated(tmp_path):
    class RootKey:
        def get_or_create(self):
            return b'k' * 32

    client, runtime, _ = make_client(tmp_path)
    data_dir = tmp_path / 'backup-source'
    data_dir.mkdir()
    (data_dir / 'owner-note.txt').write_text('owner data', encoding='utf-8')
    runtime['backups'] = BackupService(data_dir, RootKey())

    listing = client.get('/iphone/api/owner/backups')
    assert listing.status_code == 200
    assert listing.json()['backups'] == []

    created = client.post('/iphone/api/owner/backups', json={})
    assert created.status_code == 200
    backup = created.json()['backup']
    assert backup['encrypted'] is True
    assert backup['status'] == 'verified'
    assert backup['size_bytes'] > 0

    verify = client.post(f"/iphone/api/owner/backups/{backup['id']}/verify", json={})
    assert verify.status_code == 200
    assert verify.json()['ok'] is True
    assert verify.json()['encrypted'] is True

    download = client.get(f"/iphone/api/owner/backups/{backup['id']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b'PAIBACKUP2\n')
    assert 'no-store' in download.headers['cache-control']

    rows = client.get('/iphone/api/owner/backups').json()['backups']
    assert len(rows) == 1
    assert rows[0]['id'] == backup['id']


def test_owner_backup_routes_reject_untrusted_clients(tmp_path):
    client, runtime, _ = make_client(tmp_path)
    runtime['backups'] = SimpleNamespace(backup_dir=tmp_path / 'backups')
    client.cookies.delete('pa_token')
    assert client.get('/iphone/api/owner/backups').status_code == 401
    assert client.post('/iphone/api/owner/backups', json={}).status_code == 401
