from pathlib import Path
import base64
import time
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events import EventBus
from agent.executor import ConfirmationRequired
from devices.continuity import ContinuityService
from server.iphone_pwa import iphone_pwa_router
from models.router import ModelTimeout, ModelUnavailable
from core.preferences import Preferences
from onboarding.first_run import FirstRunCoordinator
from recovery.backup import BackupService
from recovery.disaster_recovery import DisasterRecoveryService, encrypt_recovery_key_file, generate_recovery_key
from security.owner_access import OwnerAccessStore
from security.pwa_sessions import PwaSessionStore
from server.pwa_session_middleware import PwaSessionMiddleware


class Registry:
    def __init__(self):
        self.tokens = {}
        self.platforms = {}
        self.active = set()
        self.sequence = 0
        self.joins = {}
    def enroll(self, name, platform):
        self.sequence += 1
        device_id = f'iphone-{self.sequence}'
        token = f'token-{self.sequence}'
        self.tokens[device_id] = token
        self.platforms[device_id] = platform
        self.active.add(device_id)
        return {'id': device_id, 'name': name, 'platform': platform}, token
    def enroll_with_credential(self, device_id, token, name, platform):
        existing = self.tokens.get(device_id)
        if existing is not None:
            if existing != token or device_id not in self.active:
                raise ValueError('Device ID is already registered')
            return {'id': device_id, 'name': name, 'platform': platform}, token
        self.tokens[device_id] = token
        self.active.add(device_id)
        return {'id': device_id, 'name': name, 'platform': platform}, token
    def authenticate(self, device_id, token):
        return device_id in self.active and self.tokens.get(device_id) == token
    def is_active(self, device_id):
        return device_id in self.active
    def revoke(self, device_id):
        if device_id not in self.active:
            return False
        self.active.remove(device_id)
        return True
    def list(self):
        return [{'id': device_id, 'name': 'Device', 'platform': self.platforms.get(device_id, 'test')}
                for device_id in sorted(self.active)]
    def request_join(self, name, platform='web-pwa', *, ttl_seconds=600):
        request_id, device_id, token = str(uuid.uuid4()), str(uuid.uuid4()), 'join-token-' + uuid.uuid4().hex * 2
        result = {'request_id': request_id, 'device_id': device_id, 'device_token': token,
                  'verification_code': '123456', 'expires_at': time.time() + ttl_seconds}
        self.joins[request_id] = {**result, 'name': name, 'platform': platform, 'status': 'pending'}
        return result
    def pending_joins(self):
        return [{k: v for k, v in item.items() if k in {'request_id', 'device_id', 'name', 'platform', 'verification_code', 'expires_at'}}
                for item in self.joins.values() if item['status'] == 'pending']
    def decide_join(self, request_id, *, approve, decided_by):
        item = self.joins.get(request_id)
        if not item or item['status'] != 'pending' or item['expires_at'] < time.time(): return False
        item['status'] = 'approved' if approve else 'denied'
        return True
    def join_status(self, request_id, token):
        item = self.joins.get(request_id)
        if not item or item['device_token'] != token: return None
        return {'status': item['status']}
    def complete_join(self, request_id, token):
        item = self.joins.get(request_id)
        if not item or item['status'] != 'approved' or item['device_token'] != token: return None
        item['status'] = 'completed'
        self.tokens[item['device_id']] = token
        self.active.add(item['device_id'])
        return {'id': item['device_id'], 'name': item['name'], 'platform': item['platform']}


class Executor:
    def chat(self, text, cancel_event=None, device_id=None, conversation_id=None, conversation_history=None):
        return f'reply:{text}:{device_id}'


class Recorder:
    def __init__(self):
        self.started = False
        self.environment = None
    def start_session(self, **kwargs):
        if self.started:
            raise RuntimeError('voice qualification session already active')
        self.started = True
        self.kwargs = kwargs
        self.environment = kwargs.get('environment')
        return 'session-1'
    def active_session(self):
        if not self.started:
            return None
        return {
            'id': 'session-1',
            'evidence_class': 'real_device',
            'environment': self.environment or {},
        }
    def stop_session(self):
        if not self.started:
            raise RuntimeError('no active voice qualification session')
        self.started = False
        return {'turns': 1, 'barge_trials': 0, 'barge_success_rate': 0.0, 'passed': False}
    def close_active_sessions(self, *, reason):
        closed = ['session-1'] if self.started else []
        self.started = False
        self.closed_reason = reason
        return closed
    def sessions(self):
        return [{'id': 'session-1'}]


def make_client(tmp_path: Path, allow_insecure=False, google_signin=False, server_sessions=False, include_legacy_runtime_routes=True, *, bootstrap_secret='', runtime_overrides=None):
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=allow_insecure,
        owner_bootstrap_secret=bootstrap_secret,
        google_signin_client_id='google-client.apps.googleusercontent.com' if google_signin else '',
        owner_google_email='owner@example.com' if google_signin else '',
    )
    events = EventBus()
    runtime = {
        'device_registry': Registry(),
        'executor': Executor(),
        'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
    }
    if server_sessions:
        runtime['pwa_sessions'] = PwaSessionStore(tmp_path / 'pwa-sessions.sqlite3', ttl_seconds=600)
    app = FastAPI()
    if server_sessions:
        app.add_middleware(
            PwaSessionMiddleware,
            sessions=runtime['pwa_sessions'],
            device_registry=runtime['device_registry'],
            cookie_max_age=600,
        )
    runtime.update(runtime_overrides or {})
    app.include_router(iphone_pwa_router(runtime, settings, include_legacy_runtime_routes=include_legacy_runtime_routes))
    return TestClient(app, base_url='https://testserver'), runtime


def test_production_router_can_exclude_legacy_canonical_runtime_overlaps(tmp_path):
    client, _ = make_client(tmp_path, include_legacy_runtime_routes=False)
    enrolled = client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert enrolled.status_code == 200

    # These method/path signatures are owned by the Stage 2/3 canonical routers
    # in cloud_app. Inspect the actual route table because a legitimate
    # non-overlapping method on the same path can correctly produce HTTP 405.
    registered = {
        (method, getattr(route, 'path', ''))
        for route in client.app.routes
        for method in (getattr(route, 'methods', None) or ())
    }
    forbidden = {
        ('POST', '/iphone/api/voice/turn'),
        ('POST', '/iphone/api/approval/{approval_id}/approve'),
        ('POST', '/iphone/api/approval/{approval_id}/reject'),
        ('GET', '/iphone/api/conversations'),
        ('GET', '/iphone/api/conversations/{conversation_id}'),
        ('POST', '/iphone/api/voice/barge'),
        ('POST', '/iphone/api/voice/client-event'),
    }
    assert registered.isdisjoint(forbidden)
    # Non-overlapping owner-access routes remain available.
    assert client.get('/iphone/api/status').status_code == 200


def test_first_run_browser_adapter_is_served_by_the_existing_pwa(tmp_path):
    client, _ = make_client(tmp_path)
    demo_entry = client.get('/iphone/campaign-demo', follow_redirects=False)
    assert demo_entry.status_code == 302
    assert demo_entry.headers['location'] == '/iphone/?campaignDemo=1'
    page = client.get('/iphone/')
    assert page.status_code == 200
    assert '/iphone/first-run.js' in page.text
    assert '/iphone/first-run-actions.js' in page.text
    assert '/iphone/neural-sphere.js' in page.text
    assert '/iphone/runtime-assistant.js' in page.text
    assert '/iphone/runtime-assistant.css' in page.text
    for asset, expected in (
        ('neural-sphere.js', 'vishnuNeuralSphere'),
        ('runtime-assistant.js', 'vishnuRuntimeAssistant'),
        ('runtime-assistant.css', 'runtime-host'),
    ):
        response = client.get('/iphone/' + asset)
        assert response.status_code == 200
        assert expected in response.text

    adapter = client.get('/iphone/first-run.js')
    actions = client.get('/iphone/first-run-actions.js')
    assert adapter.status_code == 200 and 'Create my Vishnu' in adapter.text
    assert 'Restore Vishnu' in adapter.text
    assert 'data-genesis-restore' in adapter.text
    assert 'Step ${journeyStep} of 3' in adapter.text
    assert actions.status_code == 200 and '/first-run/create' in actions.text
    assert "setupApi('/first-run/complete'" in actions.text

    # The local visual preview, Search, and Command Center modules must be served by the
    # FastAPI runtime itself (the existing browser test server can otherwise
    # hide missing production routes by injecting those files).
    for path, marker in (
        ('/iphone/genesis-welcome.css', 'vw-sphere'),
        ('/iphone/genesis-neural-sphere.js', 'mountNeuralSphere'),
        ('/iphone/genesis-identity.css', 'genesis-identity'),
        ('/iphone/genesis-identity.js', 'mountIdentityScreen'),
        ('/iphone/genesis-security.css', 'genesis-security'),
        ('/iphone/genesis-security.js', 'mountSecurityScreen'),
        ('/iphone/genesis-recovery.css', 'vr-code-grid'),
        ('/iphone/genesis-recovery.js', 'mountRecoveryScreen'),
        ('/iphone/genesis-login.css', 'vl-panel'),
        ('/iphone/genesis-login.js', 'mountLoginScreen'),
        ('/iphone/genesis-connect.css', 'vc-method'),
        ('/iphone/genesis-connect.js', 'mountConnectScreen'),
        ('/iphone/genesis-recovery-options.css', 'vo-choice'),
        ('/iphone/genesis-recovery-options.js', 'mountRecoveryOptionsScreen'),
        ('/iphone/genesis-verification.css', 'v8-method'),
        ('/iphone/genesis-verification.js', 'mountRecoveryVerificationScreen'),
        ('/iphone/assets/genesis/avatar-blue.svg', '<svg'),
        ('/iphone/assets/genesis/avatar-mountain.svg', '<svg'),
        ('/iphone/assets/genesis/avatar-forest.svg', '<svg'),
        ('/iphone/assets/genesis/avatar-horizon.svg', '<svg'),
        ('/iphone/campaign-demo.js', 'campaignDemo'),
        ('/iphone/campaign-demo.css', 'vishnuCampaignDemo'),
        ('/iphone/campaign-demo-data.js', 'Rudra Health Care'),
        ('/iphone/global-search.js', 'globalSearch'),
        ('/iphone/global-search.css', 'global-search'),
        ('/iphone/command-center.js', 'vishnuOpenCommandCenter'),
        ('/iphone/command-center.css', 'cc-page-mode'),
        ('/iphone/workspaces-ui.js', 'vishnuRenderWorkspaces'),
        ('/iphone/workspaces-ui.css', 'ws-page'),
    ):
        asset = client.get(path)
        assert asset.status_code == 200, path
        assert marker.lower() in asset.text.lower(), path

def test_owner_enrollment_requires_correct_code_and_sets_secure_cookies(tmp_path):
    client, _ = make_client(tmp_path)
    bad = client.post('/iphone/api/enroll', json={'code': 'wrong'})
    assert bad.status_code == 401
    response = client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert response.status_code == 200
    assert response.json()['device_id'] == 'iphone-1'
    cookies = response.headers.get_list('set-cookie')
    assert any('pa_device=' in c and 'HttpOnly' in c and 'Secure' in c and 'SameSite=strict' in c for c in cookies)
    assert any('pa_token=' in c and 'HttpOnly' in c and 'Secure' in c and 'SameSite=strict' in c for c in cookies)
    assert all('Max-Age=31536000' in c for c in cookies)


def test_missing_browser_trust_returns_clear_web_sign_in_guidance(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get('/iphone/api/conversations')
    assert response.status_code == 401
    message = response.json()['detail']
    assert 'web browser' in message.lower()
    assert 'sign in again' in message.lower()
    assert 'not been deleted' in message.lower()
    assert 'iphone' not in message.lower()


def test_status_renews_existing_browser_trust_without_reenrollment(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})

    response = client.get('/iphone/api/status')

    assert response.status_code == 200
    cookies = response.headers.get_list('set-cookie')
    assert len(cookies) == 2
    assert all('Max-Age=31536000' in cookie for cookie in cookies)
    assert len(runtime['device_registry'].tokens) == 1


def test_owner_password_unlocks_a_new_browser_after_trusted_setup(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    owner_device, owner_token = client.cookies.get('pa_device'), client.cookies.get('pa_token')
    assert client.post('/iphone/api/access/password/setup', json={
        'password': 'correct horse battery staple',
    }).status_code == 200
    client.post('/iphone/api/logout', json={})

    assert client.post('/iphone/api/access/password/login', json={
        'password': 'wrong password',
    }).status_code == 401
    requester = TestClient(client.app, base_url='https://testserver')
    login = requester.post('/iphone/api/access/password/login', json={
        'password': 'correct horse battery staple',
        'name': 'Safari with password',
    })
    assert login.status_code == 200
    pending = login.json()
    assert pending['status'] == 'approval_required'
    assert len(runtime['device_registry'].active) == 1
    assert requester.post('/iphone/api/access/join/status', json={
        'request_id': pending['request_id'],
    }).json()['status'] == 'pending'
    # A trusted owner browser must verify its password and approve the exact
    # request before the new browser receives any device credentials.
    client.cookies.set('pa_device', owner_device)
    client.cookies.set('pa_token', owner_token)
    requests = client.get('/iphone/api/access/join/requests').json()['requests']
    assert requests[0]['verification_code'] == pending['verification_code']
    assert client.post(f"/iphone/api/access/join/{pending['request_id']}/decision", json={
        'password': 'correct horse battery staple', 'approve': True,
    }).status_code == 200
    completed = requester.post('/iphone/api/access/join/status', json={
        'request_id': pending['request_id'],
    })
    assert completed.json()['status'] == 'complete'
    assert len(runtime['device_registry'].active) == 2



def test_join_request_cancel_requires_original_join_cookie_and_invalidates_request(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert client.post('/iphone/api/access/password/setup', json={
        'password': 'correct horse battery staple',
    }).status_code == 200
    # A second, untrusted browser authenticates only the owner identity.
    requester = TestClient(client.app, base_url='https://testserver')
    pending = requester.post('/iphone/api/access/password/login', json={
        'password': 'correct horse battery staple', 'name': 'Untrusted browser',
    }).json()
    assert pending['status'] == 'approval_required'
    request_id = pending['request_id']
    assert len(runtime['device_registry'].active) == 1

    # Without the HttpOnly pa_join cookie, even knowing the public request ID
    # does not allow an attacker to cancel someone else's join.
    unauthenticated = TestClient(client.app, base_url='https://testserver')
    denied = unauthenticated.post('/iphone/api/access/join/cancel', json={
        'request_id': request_id,
    })
    assert denied.status_code == 401
    attacker = TestClient(client.app, base_url='https://testserver')
    attacker.cookies.set('pa_join', 'wrong-random-credential')
    assert attacker.post('/iphone/api/access/join/cancel', json={
        'request_id': request_id,
    }).status_code == 404

    cancelled = requester.post('/iphone/api/access/join/cancel', json={
        'request_id': request_id,
    })
    assert cancelled.status_code == 200
    assert cancelled.json() == {'status': 'cancelled'}
    assert len(runtime['device_registry'].active) == 1
    assert requester.post('/iphone/api/access/join/status', json={
        'request_id': request_id,
    }).status_code == 404
    assert requester.post('/iphone/api/access/join/cancel', json={
        'request_id': request_id,
    }).status_code in {401, 404, 409}
    assert not runtime['device_registry'].decide_join(
        request_id, approve=True, decided_by='iphone-1',
    )


def test_recovery_code_unlocks_once_and_cannot_be_replayed(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    generated = client.post('/iphone/api/access/recovery/regenerate', json={}).json()['codes']
    client.post('/iphone/api/logout', json={})

    recovered = client.post('/iphone/api/access/recovery/login', json={'code': generated[0]})
    assert recovered.status_code == 200
    assert recovered.json()['recovery_result']['identityStatus'] == 'completed'
    assert recovered.json()['recovery_result']['dataStatus'] == 'not_applicable'
    assert recovered.json()['recovery_result']['deviceStatus'] == 'completed'
    client.post('/iphone/api/logout', json={})
    assert client.post('/iphone/api/access/recovery/login', json={'code': generated[0]}).status_code == 401


def test_web_portable_restore_preserves_identity_restores_data_and_secures_replacement_device(tmp_path, monkeypatch):
    monkeypatch.setenv('PERSONAL_AI_ROOT_KEY', base64.b64encode(b'R' * 32).decode('ascii'))
    source = tmp_path / 'source'
    target = tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    source_owner = OwnerAccessStore(source / 'owner-access.sqlite3')
    identity, _ = source_owner.initialize_identity(
        first_name='Asha', last_name='Patel', display_name='Asha Patel',
    )
    (source / 'conversation-sample.json').write_text('{"message":"recoverable test data"}', encoding='utf-8')
    recovery_key = generate_recovery_key()
    archive = tmp_path / 'asha.vdr'
    DisasterRecoveryService(BackupService(source)).create_bundle(
        archive, recovery_key=recovery_key, owner_id=identity['owner_id'], key_id='web-recovery-test',
    )
    key_file = tmp_path / 'asha.vrk'
    key_file.write_bytes(encrypt_recovery_key_file(recovery_key, 'correct horse battery staple'))

    target_preferences = Preferences(target / 'preferences.json')

    class Models:
        def set_owner_privacy(self, _value):
            return None

    class Tools:
        def set_autonomy_mode(self, _value):
            return None

    setup = FirstRunCoordinator(target)
    client, runtime = make_client(
        target, allow_insecure=True, bootstrap_secret='B' * 48,
        runtime_overrides={
            'preferences': target_preferences,
            'models': Models(),
            'tools': Tools(),
            'backups': BackupService(target),
            'first_run_setup': setup,
        },
    )
    setup.bind_runtime(runtime)

    headers = {'X-Vishnu-Setup-Code': 'B' * 48, 'Content-Type': 'application/octet-stream'}
    staged_archive = client.post(
        '/iphone/api/first-run/restore/archive', content=archive.read_bytes(), headers=headers,
    )
    assert staged_archive.status_code == 200, staged_archive.text
    session = staged_archive.json()['session_id']
    staged_key = client.post(
        f'/iphone/api/first-run/restore/key?session_id={session}',
        content=key_file.read_bytes(), headers=headers,
    )
    assert staged_key.status_code == 200, staged_key.text
    scheduled = client.post('/iphone/api/first-run/restore/schedule', json={
        'session_id': session,
        'bootstrap_secret': 'B' * 48,
        'passphrase': 'correct horse battery staple',
    })
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()['status'] == 'restart_required'
    assert not (target / '.web-recovery-staging' / session).exists()

    restored = FirstRunCoordinator.apply_pending_restore(target)
    assert restored['ok'] is True and restored['portable_disaster_recovery'] is True
    assert (target / 'conversation-sample.json').read_text(encoding='utf-8') == '{"message":"recoverable test data"}'
    restored_identity = runtime['owner_access'].identity()
    assert restored_identity['owner_id'] == identity['owner_id']
    assert restored_identity['vishnu_id'] == identity['vishnu_id']
    assert runtime['owner_access'].password_configured() is False
    assert runtime['owner_access'].recovery_codes_remaining() == 0

    secured = client.post('/iphone/api/first-run/restore/secure-device', json={
        'bootstrap_secret': 'B' * 48,
        'password': 'a fresh replacement-device password',
        'device_name': 'Development web browser',
    })
    assert secured.status_code == 200, secured.text
    assert secured.json()['identity']['owner_id'] == identity['owner_id']
    assert secured.json()['identity']['vishnu_id'] == identity['vishnu_id']
    assert len(secured.json()['recovery_codes']) >= 4
    assert runtime['owner_access'].password_configured() is True
    assert runtime['owner_access'].recovery_codes_remaining() == len(secured.json()['recovery_codes'])

    saved = client.post('/iphone/api/first-run/recovery-saved', json={'saved': True})
    assert saved.status_code == 200, saved.text
    configured = client.post('/iphone/api/first-run/model', json={'provider_id': 'skip'})
    assert configured.status_code == 200, configured.text
    complete = client.post('/iphone/api/first-run/complete', json={
        'recovery_saved': True, 'privacy_mode': 'local_only',
        'autonomy_mode': 'ask', 'passkey_unavailable_confirmed': True,
    })
    assert complete.status_code == 200, complete.text
    assert complete.json()['recovery_result']['recoveryType'] == 'encrypted_data'
    assert complete.json()['recovery_result']['identityStatus'] == 'completed'
    assert complete.json()['recovery_result']['deviceStatus'] == 'completed'
    assert complete.json()['recovery_result']['dataStatus'] in {'completed', 'partial', 'pending'}
    assert setup.ready is True
    assert runtime['owner_access'].identity()['owner_id'] == identity['owner_id']


def test_password_join_requires_approval_on_an_existing_session(tmp_path):
    owner, runtime = make_client(tmp_path, server_sessions=True)
    assert owner.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'}).status_code == 200
    assert owner.post('/iphone/api/access/password/setup', json={
        'password': 'correct horse battery staple',
    }).status_code == 200
    requester = TestClient(owner.app, base_url='https://testserver')

    request = requester.post('/iphone/api/access/password/login', json={
        'password': 'correct horse battery staple', 'name': 'Development browser',
    }).json()
    assert request['status'] == 'approval_required'
    assert len(runtime['device_registry'].active) == 1
    assert requester.cookies.get('pa_device') is None
    assert requester.cookies.get('pa_session') is None
    assert requester.cookies.get('pa_join')
    assert request.get('device_token') is None

    assert owner.get('/iphone/api/access/join/requests').json()['requests'][0]['request_id'] == request['request_id']
    decision = owner.post(f"/iphone/api/access/join/{request['request_id']}/decision", json={
        'password': 'correct horse battery staple', 'approve': True,
    })
    assert decision.status_code == 200
    completed = requester.post('/iphone/api/access/join/status', json={
        'request_id': request['request_id'],
    })
    assert completed.json()['status'] == 'complete'
    assert requester.cookies.get('pa_session')
    assert requester.get('/iphone/api/status').status_code == 200
    assert len(runtime['device_registry'].active) == 2


def test_join_denial_and_bad_approver_password_never_enroll_new_device(tmp_path):
    owner, runtime = make_client(tmp_path, server_sessions=True)
    assert owner.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'}).status_code == 200
    assert owner.post('/iphone/api/access/password/setup', json={
        'password': 'correct horse battery staple',
    }).status_code == 200

    requester = TestClient(owner.app, base_url='https://testserver')
    login = requester.post('/iphone/api/access/password/login', json={
        'password': 'correct horse battery staple', 'name': 'Unknown browser',
    })
    assert login.status_code == 200
    pending = login.json()
    assert pending['status'] == 'approval_required'
    assert requester.cookies.get('pa_join') is not None
    assert requester.cookies.get('pa_session') is None
    assert len(runtime['device_registry'].active) == 1

    bad = owner.post(f"/iphone/api/access/join/{pending['request_id']}/decision", json={
        'password': 'incorrect password', 'approve': True,
    })
    assert bad.status_code == 401
    assert requester.post('/iphone/api/access/join/status', json={
        'request_id': pending['request_id'],
    }).json()['status'] == 'pending'

    denial = owner.post(f"/iphone/api/access/join/{pending['request_id']}/decision", json={
        'password': 'correct horse battery staple', 'approve': False,
    })
    assert denial.status_code == 200
    assert denial.json()['status'] == 'denied'
    final = requester.post('/iphone/api/access/join/status', json={
        'request_id': pending['request_id'],
    })
    assert final.status_code == 200
    assert final.json()['status'] == 'denied'
    assert requester.cookies.get('pa_device') is None
    assert requester.cookies.get('pa_session') is None
    assert len(runtime['device_registry'].active) == 1
    assert owner.post(f"/iphone/api/access/join/{pending['request_id']}/decision", json={
        'password': 'correct horse battery staple', 'approve': True,
    }).status_code == 409


def test_access_options_and_passkey_registration_require_owner_trust(tmp_path):
    client, _ = make_client(tmp_path)
    options = client.get('/iphone/api/access/options').json()
    assert options == {
        'creation_available': False,
        'restore_available': False,
        'local_setup_available': False,
        'setup_in_progress': False,
        'restore_setup_in_progress': False,
        'restore_restart_required': False,
        'restore_report': None,
        'setup_resume_step': None,
        'setup_recovery_saved': False,
        'model_setup_complete': False,
        'passkey_available': False,
        'password_available': False,
        'recovery_available': False,
        'enrollment_available': True,
        'google_available': False,
        'google_client_id': '',
    }
    assert client.post('/iphone/api/access/passkey/register/options', json={}).status_code == 401
    assert client.post('/iphone/api/access/passkey/login/options', json={}).status_code == 409

    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    registration = client.post('/iphone/api/access/passkey/register/options', json={})
    assert registration.status_code == 200
    public_key = registration.json()['public_key']
    assert public_key['rp']['id'] == 'testserver'
    assert public_key['authenticatorSelection']['userVerification'] == 'required'


def test_password_failures_are_rate_limited(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    client.post('/iphone/api/access/password/setup', json={'password': 'correct horse battery staple'})
    client.post('/iphone/api/logout', json={})
    for _ in range(5):
        assert client.post('/iphone/api/access/password/login', json={'password': 'wrong'}).status_code == 401
    assert client.post('/iphone/api/access/password/login', json={'password': 'wrong'}).status_code == 429


def test_verified_configured_google_owner_unlocks_new_browser(tmp_path, monkeypatch):
    client, runtime = make_client(tmp_path, google_signin=True)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    calls = []

    def verify(token, request, audience):
        calls.append((token, audience))
        return {
            'sub': 'google-owner-subject',
            'email': 'OWNER@example.com',
            'email_verified': True,
        }

    monkeypatch.setattr('server.iphone_pwa.google_id_token.verify_oauth2_token', verify)
    options = client.get('/iphone/api/access/options').json()
    assert options['google_available'] is True
    assert options['google_client_id'] == 'google-client.apps.googleusercontent.com'

    requester = TestClient(client.app, base_url='https://testserver')
    response = requester.post('/iphone/api/access/google/login', json={
        'credential': 'g' * 120,
        'name': 'Owner Google Safari',
    })

    assert response.status_code == 200
    assert response.json()['status'] == 'approval_required'
    assert calls == [('g' * 120, 'google-client.apps.googleusercontent.com')]
    assert len(runtime['device_registry'].tokens) == 1
    join_cookie = response.headers.get_list('set-cookie')
    assert len(join_cookie) == 1 and 'pa_join=' in join_cookie[0] and 'HttpOnly' in join_cookie[0]


def test_google_login_rejects_other_or_unverified_accounts(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, google_signin=True)

    monkeypatch.setattr(
        'server.iphone_pwa.google_id_token.verify_oauth2_token',
        lambda *_: {'sub': 'someone-else', 'email': 'other@example.com', 'email_verified': True},
    )
    assert client.post('/iphone/api/access/google/login', json={'credential': 'x' * 120}).status_code == 401

    monkeypatch.setattr(
        'server.iphone_pwa.google_id_token.verify_oauth2_token',
        lambda *_: {'sub': 'owner', 'email': 'owner@example.com', 'email_verified': False},
    )
    assert client.post('/iphone/api/access/google/login', json={'credential': 'y' * 120}).status_code == 401


def test_google_login_fails_closed_when_not_configured(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post('/iphone/api/access/google/login', json={'credential': 'x' * 120})
    assert response.status_code == 503


def test_voice_turn_uses_enrolled_device_and_existing_executor(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    response = client.post('/iphone/api/voice/turn', json={'transcript': 'hello'})
    assert response.status_code == 200
    assert response.json()['reply'] == 'reply:hello:iphone-1'


def test_voice_tool_request_returns_owner_approval_instead_of_http_500(tmp_path):
    client, runtime = make_client(tmp_path)

    class ApprovalExecutor:
        def chat(self, text, cancel_event=None, device_id=None, conversation_id=None, conversation_history=None):
            raise ConfirmationRequired(
                'web_search_browser',
                {'query': text},
                'Search the web for the requested information',
                approval_id='approval-1',
                execution_id='execution-1',
                expires_at=12345.0,
            )

        def approve(self, approval_id):
            assert approval_id == 'approval-1'
            return 'The approved search completed.'

        def reject(self, approval_id):
            assert approval_id == 'approval-1'
            return 'Action cancelled.'

    runtime['executor'] = ApprovalExecutor()
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})

    response = client.post('/iphone/api/voice/turn', json={'transcript': 'search the web'})

    assert response.status_code == 202
    assert response.json()['status'] == 'approval_required'
    assert response.json()['approval']['tool'] == 'web_search_browser'
    assert 'query' not in response.json()['approval']
    approved = client.post('/iphone/api/approval/approval-1/approve', json={})
    assert approved.status_code == 200
    assert approved.json()['reply'] == 'The approved search completed.'


def test_pwa_approval_recovers_from_ephemeral_cache_loss_using_canonical_context(tmp_path):
    client, runtime = make_client(tmp_path)

    class DurableApprovalExecutor:
        def __init__(self):
            self.pending = False

        def chat(self, text, cancel_event=None, device_id=None, conversation_id=None, conversation_history=None):
            self.pending = True
            raise ConfirmationRequired(
                'web_search_browser',
                {'query': text},
                'Search the web for the requested information',
                approval_id='approval-durable',
                execution_id='execution-durable',
                expires_at=12345.0,
            )

        def approval_context(self, approval_id):
            if self.pending and approval_id == 'approval-durable':
                return {
                    'approval_id': approval_id,
                    'device_id': 'iphone-1',
                    'conversation_id': None,
                    'tool': 'web_search_browser',
                }
            return None

        def approve(self, approval_id):
            assert approval_id == 'approval-durable'
            self.pending = False
            return 'Recovered durable approval completed.'

        def reject(self, approval_id):
            self.pending = False
            return 'Action cancelled.'

    executor = DurableApprovalExecutor()
    runtime['executor'] = executor
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    pending = client.post('/iphone/api/voice/turn', json={'transcript': 'search the web'})
    assert pending.status_code == 202

    # Recreate the router to simulate process/router-local cache loss while the
    # canonical durable approval remains pending.
    reloaded = FastAPI()
    reloaded.include_router(iphone_pwa_router(runtime, settings))
    reloaded_client = TestClient(reloaded, base_url='https://testserver')
    reloaded_client.cookies.update(client.cookies)
    approved = reloaded_client.post('/iphone/api/approval/approval-durable/approve', json={})
    assert approved.status_code == 200
    assert approved.json()['reply'] == 'Recovered durable approval completed.'


def test_pwa_approval_cache_cannot_cross_device_binding(tmp_path):
    client, runtime = make_client(tmp_path)

    class BoundApprovalExecutor:
        def approval_context(self, approval_id):
            return {
                'approval_id': approval_id,
                'device_id': 'different-device',
                'conversation_id': None,
                'tool': 'web_search_browser',
            }

        def approve(self, approval_id):
            raise AssertionError('cross-device approval must not execute')

    runtime['executor'] = BoundApprovalExecutor()
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    response = client.post('/iphone/api/approval/approval-durable/approve', json={})
    assert response.status_code == 404


def test_unavailable_tool_returns_safe_error_instead_of_http_500(tmp_path):
    client, runtime = make_client(tmp_path)

    class BrokenToolExecutor:
        def chat(self, *args, **kwargs):
            raise RuntimeError('Library libxcb.so not found at internal path')

    runtime['executor'] = BrokenToolExecutor()
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})

    response = client.post('/iphone/api/voice/turn', json={'transcript': 'look at the server screen'})

    assert response.status_code == 502
    assert response.json()['detail']['code'] == 'tool_error'
    assert 'libxcb' not in response.text


def test_cancelled_http_error_is_not_reclassified_as_tool_error(tmp_path):
    client, runtime = make_client(tmp_path)

    class CancelledExecutor:
        def chat(self, text, cancel_event=None, **kwargs):
            cancel_event.set()
            return 'stale reply'

    runtime['executor'] = CancelledExecutor()
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    response = client.post('/iphone/api/voice/turn', json={'transcript': 'cancel'})
    assert response.status_code == 409
    assert response.json()['detail'] == 'turn_cancelled'


def test_p3_session_records_ios_pwa_environment_but_does_not_self_award(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    start = client.post('/iphone/api/qualification/start', json={'environment': {'noise': 'quiet'}})
    assert start.status_code == 200
    recorder = runtime['voice_qualification']
    assert recorder.kwargs['evidence_class'] == 'real_device'
    assert recorder.kwargs['environment']['platform'] == 'ios-pwa'
    stop = client.post('/iphone/api/qualification/stop', json={})
    assert stop.status_code == 200
    assert stop.json()['passed'] is False


def test_second_stop_is_idempotent_and_user_safe(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    client.post('/iphone/api/qualification/start', json={'environment': {}})
    assert client.post('/iphone/api/qualification/stop', json={}).status_code == 200
    second = client.post('/iphone/api/qualification/stop', json={})
    assert second.status_code == 200
    assert second.json() == {
        'ok': True,
        'status': 'already_stopped',
        'message': 'Session already stopped',
    }


def test_repeated_start_resumes_active_session_after_page_refresh(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    first = client.post('/iphone/api/qualification/start', json={'environment': {'noise': 'quiet'}})
    assert first.status_code == 200
    assert first.json()['status'] == 'started'

    resumed = client.post('/iphone/api/qualification/start', json={'environment': {'noise': 'quiet'}})
    assert resumed.status_code == 200
    assert resumed.json() == {
        'session_id': 'session-1',
        'evidence_class': 'real_device',
        'status': 'already_active',
        'message': 'Existing session resumed',
    }


def test_status_restores_the_active_session_for_hands_free_ui(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    client.post('/iphone/api/qualification/start', json={'environment': {}})

    status = client.get('/iphone/api/status')

    assert status.status_code == 200
    assert status.json()['active_qualification']['session_id'] == 'session-1'


def test_trusted_owner_can_explicitly_replace_other_device_stale_session(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    recorder = runtime['voice_qualification']
    recorder.started = True
    recorder.environment = {'device_id': 'old-browser'}

    blocked = client.post('/iphone/api/qualification/start', json={'environment': {}})
    assert blocked.status_code == 409
    takeover = client.post('/iphone/api/qualification/takeover', json={
        'confirm': True,
        'environment': {'noise': 'quiet'},
    })

    assert takeover.status_code == 200
    assert takeover.json()['closed_session_ids'] == ['session-1']
    assert recorder.environment['device_id'] == 'iphone-1'
    assert 'Owner-confirmed takeover' in recorder.closed_reason


def test_home_uses_one_touch_voice_instead_of_four_test_buttons(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get('/iphone/')

    assert page.status_code == 200
    assert 'id="micButton"' in page.text
    assert 'Tap once to talk continuously' in page.text
    assert '>Start Session<' not in page.text
    assert '>Start Listening<' not in page.text
    assert '>Interrupt<' not in page.text
    assert 'Continue here' in page.text


def test_reference_today_module_is_defined_and_loaded_as_a_page(tmp_path):
    client, _ = make_client(tmp_path)
    script = client.get('/iphone/reference-pages.js')
    assert script.status_code == 200
    assert 'function todayPage()' in script.text
    assert "name==='today'?todayPage()" in script.text
    assert 'function bindToday()' in script.text
    # Reference pages now return their complete shell, so render mounts the
    # page directly instead of wrapping a second shell around its content.
    assert "const page=name==='today'?todayPage()" in script.text
    assert 'root.innerHTML=page' in script.text


def test_client_tts_failure_is_recorded_as_voice_error(tmp_path):
    client, runtime = make_client(tmp_path)
    errors = []
    runtime['events'].subscribe('voice.error', errors.append)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    client.post('/iphone/api/qualification/start', json={'environment': {}})

    response = client.post('/iphone/api/voice/client-event', json={
        'event': 'tts_error',
        'detail': 'start_timeout',
    })

    assert response.status_code == 200
    assert errors[0]['error'] == 'tts_error'
    assert errors[0]['detail'] == 'start_timeout'


def test_model_unavailable_is_a_safe_explicit_state(tmp_path):
    client, runtime = make_client(tmp_path)

    class UnavailableExecutor:
        def chat(self, *args, **kwargs):
            raise ModelUnavailable('connection refused', provider='self_hosted')

    runtime['executor'] = UnavailableExecutor()
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    response = client.post('/iphone/api/voice/turn', json={'transcript': 'hello'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'model_unavailable'
    assert '127.0.0.1' not in response.text


def test_model_timeout_is_not_reported_as_http_500(tmp_path):
    client, runtime = make_client(tmp_path)

    class TimeoutExecutor:
        def chat(self, *args, **kwargs):
            raise ModelTimeout('timed out', provider='self_hosted')

    runtime['executor'] = TimeoutExecutor()
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )))
    client = TestClient(app, base_url='https://testserver')
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    response = client.post('/iphone/api/voice/turn', json={'transcript': 'hello'})
    assert response.status_code == 504
    assert response.json()['detail']['code'] == 'model_timeout'


def test_plain_http_enrollment_fails_closed(tmp_path):
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='this-is-a-long-owner-code',
        iphone_pwa_allow_insecure=False,
    )
    events = EventBus()
    runtime = {
        'device_registry': Registry(),
        'executor': Executor(),
        'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
    }
    app = FastAPI(); app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='http://testserver')
    response = client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert response.status_code == 400


def test_conversation_survives_reload_and_continues_across_trusted_browsers(tmp_path):
    first, runtime = make_client(tmp_path)
    second = TestClient(first.app, base_url='https://testserver')
    first.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code', 'name': 'Safari'})
    second.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code', 'name': 'Installed PWA'})

    initial = first.post('/iphone/api/voice/turn', json={'transcript': 'Plan my kitchen project'})
    conversation_id = initial.json()['conversation_id']
    reloaded = first.get('/iphone/api/status').json()['conversation']
    assert reloaded['thread']['id'] == conversation_id
    assert [event['payload']['text'] for event in reloaded['events']] == [
        'Plan my kitchen project',
        'reply:Plan my kitchen project:iphone-1',
    ]

    shared = second.post(
        f'/iphone/api/conversations/{conversation_id}/activate',
        json={},
    )
    assert shared.status_code == 200
    continued = second.post('/iphone/api/voice/turn', json={
        'transcript': 'Continue with the budget',
        'conversation_id': conversation_id,
    })
    assert continued.status_code == 200

    final = first.get(f'/iphone/api/conversations/{conversation_id}').json()
    assert [event['device_id'] for event in final['events']] == [
        'iphone-1', 'iphone-1', 'iphone-2', 'iphone-2',
    ]
    assert final['events'][-1]['payload']['text'] == 'reply:Continue with the budget:iphone-2'


def test_conversation_history_can_be_created_listed_and_searched(tmp_path):
    client, _ = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    created = client.post('/iphone/api/conversations', json={'title': 'Renovation notes'}).json()
    conversation_id = created['conversation']['id']
    client.post('/iphone/api/voice/turn', json={
        'transcript': 'Compare flooring options',
        'conversation_id': conversation_id,
    })

    found = client.get('/iphone/api/conversations?q=flooring').json()
    assert [item['id'] for item in found['conversations']] == [conversation_id]
    renamed = client.patch(
        f'/iphone/api/conversations/{conversation_id}',
        json={'title': 'Home renovation'},
    )
    assert renamed.status_code == 200
    assert renamed.json()['conversation']['title'] == 'Home renovation'



def test_conversation_options_export_and_confirmed_delete_are_owner_gated(tmp_path):
    client, _ = make_client(tmp_path)
    unauthenticated = TestClient(client.app, base_url='https://testserver')
    assert client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'}).status_code == 200
    created = client.post('/iphone/api/conversations', json={'title': 'Private transcript'}).json()
    thread_id = created['conversation']['id']
    assert client.post('/iphone/api/voice/turn', json={
        'transcript': 'Remember the room measurements',
        'conversation_id': thread_id,
    }).status_code == 200
    path = f'/iphone/api/conversations/{thread_id}'

    assert unauthenticated.get(path + '/export').status_code == 401
    assert unauthenticated.delete(path + '?confirm=true').status_code == 401
    exported = client.get(path + '/export')
    assert exported.status_code == 200
    assert exported.json()['conversation']['title'] == 'Private transcript'
    assert exported.json()['events']
    assert client.delete(path).status_code == 422
    assert client.get(path).status_code == 200

    deleted = client.delete(path + '?confirm=true')
    assert deleted.status_code == 200
    assert deleted.json() == {'deleted': True, 'conversation_id': thread_id}
    assert client.get(path).status_code == 404
    assert client.get(path + '/export').status_code == 404
    assert client.delete(path + '?confirm=true').status_code == 404


def test_conversation_options_render_in_pwa_shell(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get('/iphone/').text
    assert 'id="chatMenuButton"' in page
    assert 'id="chatActionMenu"' in page
    assert 'id="chatRename"' in page
    assert 'id="chatShare"' in page
    assert 'id="chatCopy"' in page
    assert 'id="chatExport"' in page
    assert 'id="chatDelete"' in page
    assert 'function syncChatMenuAvailability()' in page


def test_normal_chat_is_not_blocked_by_other_browser_qualification(tmp_path):
    first, runtime = make_client(tmp_path)
    second = TestClient(first.app, base_url='https://testserver')
    first.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    second.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert first.post('/iphone/api/qualification/start', json={'environment': {}}).status_code == 200

    response = second.post('/iphone/api/voice/turn', json={'transcript': 'hello from browser two'})

    assert response.status_code == 200
    assert response.json()['reply'] == 'reply:hello from browser two:iphone-2'
    assert runtime['voice_qualification'].active_session()['environment']['device_id'] == 'iphone-1'


def test_normal_chat_does_not_automatically_start_qualification(tmp_path):
    client, runtime = make_client(tmp_path)
    client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})

    assert client.post('/iphone/api/voice/turn', json={'transcript': 'normal chat'}).status_code == 200
    assert runtime['voice_qualification'].active_session() is None


def test_pwa_home_is_conversation_first_and_qualification_lives_in_advanced(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get('/iphone/').text

    assert 'id="messageStream"' in page
    assert 'id="attachmentButton"' in page
    assert 'id="appDrawer"' in page
    assert 'id="appConversations"' in page
    assert 'data-app-module="memory"' in page
    assert '<nav class="nav"' not in page
    assert 'id="moreSheet"' not in page
    assert 'data-owner-module="settings"' in page
    assert 'Models &amp; Intelligence' in page
    assert "renderSettings('advanced')" in page
    assert '<details class="session-details">' not in page
    assert 'id="startSession"' not in page
    assert 'id="stopSession"' not in page
    assert 'Continue with Face ID' in page
    assert 'Use owner password' in page
    assert 'Having trouble?' in page
    assert 'Use enrollment code' in page
    assert 'Trust this iPhone' not in page
    assert 'localStorage' not in page
    assert 'sessionStorage' not in page


def test_browser_cannot_stop_another_browsers_qualification_session(tmp_path):
    first, runtime = make_client(tmp_path)
    second = TestClient(first.app, base_url='https://testserver')
    first.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    second.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    first.post('/iphone/api/qualification/start', json={'environment': {}})

    blocked = second.post('/iphone/api/qualification/stop', json={})

    assert blocked.status_code == 409
    assert blocked.json()['detail']['code'] == 'qualification_session_owned_by_other_device'
    assert runtime['voice_qualification'].active_session() is not None


def test_stage8_stale_server_reauth_blocks_owner_credential_changes(tmp_path):
    client, runtime = make_client(tmp_path, server_sessions=True)
    enrolled = client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert enrolled.status_code == 200

    session_id = next(iter(runtime['pwa_sessions'].active_for_device(enrolled.json()['device_id']))).id
    assert runtime['pwa_sessions'].mark_reauthenticated(session_id, at=time.time() - 1000)

    password = client.post('/iphone/api/access/password/setup', json={
        'password': 'correct horse battery staple',
    })
    assert password.status_code == 401
    assert password.json()['detail']['code'] == 'reauthentication_required'

    recovery = client.post('/iphone/api/access/recovery/regenerate', json={})
    assert recovery.status_code == 401

    passkey = client.post('/iphone/api/access/passkey/register/options', json={})
    assert passkey.status_code == 401

    assert runtime['owner_access'].password_configured() is False
    assert runtime['owner_access'].recovery_codes_remaining() == 0


def test_web_first_run_creates_canonical_owner_and_first_browser_device(tmp_path):
    bootstrap = 'B' * 40
    events = EventBus()
    registry = Registry()
    runtime = {
        'device_registry': registry,
        'executor': Executor(),
        'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
        'preferences': Preferences(tmp_path / 'preferences.json'),
        'models': SimpleNamespace(set_owner_privacy=lambda mode: None,
                                  set_default_provider=lambda provider: {'provider': provider},
                                  connect_owner_provider=lambda provider, key, model: {'provider': provider, 'model': model},
                                  status=lambda: {'state': 'unconfigured'}),
        'tools': SimpleNamespace(set_autonomy_mode=lambda mode: None),
    }
    setup = FirstRunCoordinator(tmp_path, runtime=runtime)
    setup.should_run()
    runtime['first_run_setup'] = setup
    runtime['pwa_sessions'] = PwaSessionStore(tmp_path / 'pwa-sessions.sqlite3', ttl_seconds=600)
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='',
        iphone_pwa_allow_insecure=False,
        owner_bootstrap_secret=bootstrap,
        google_signin_client_id='', owner_google_email='',
    )
    app = FastAPI()
    app.add_middleware(PwaSessionMiddleware, sessions=runtime['pwa_sessions'],
                       device_registry=registry, cookie_max_age=600,
                       first_run_setup=setup)
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='https://testserver')

    assert client.get('/iphone/api/access/options').json()['creation_available'] is True
    denied = client.post('/iphone/api/first-run/create', json={
        'bootstrap_secret': 'wrong' * 8, 'first_name': 'A',
        'password': 'a sufficiently long password',
    })
    assert denied.status_code == 401
    assert runtime['owner_access'].identity() is None

    created = client.post('/iphone/api/first-run/create', json={
        'bootstrap_secret': bootstrap, 'first_name': 'Ada', 'last_name': 'Lovelace',
        'display_name': 'Ada', 'password': 'a sufficiently long password',
        'device_name': 'Ada phone browser',
    })
    assert created.status_code == 200, created.text
    assert 'no-store' in created.headers['cache-control']
    assert created.headers['pragma'] == 'no-cache'
    result = created.json()
    identity = runtime['owner_access'].identity()
    assert result['identity']['owner_id'] == identity['owner_id']
    assert identity['vishnu_id'].startswith('VISHNU-')
    assert result['device']['id'] == 'iphone-1'
    assert 'pa_token' not in result
    assert len(result['recovery_codes']) >= 4
    assert client.cookies.get('pa_setup_claim')
    assert client.cookies.get('pa_session')
    assert runtime['owner_access'].recovery_codes_remaining() == len(result['recovery_codes'])
    # Explicit regeneration atomically invalidates the old hashed credentials,
    # and must never happen on refresh or retry.
    original_codes = list(result['recovery_codes'])
    regenerated = client.post('/iphone/api/first-run/recovery-codes')
    assert regenerated.status_code == 200, regenerated.text
    assert 'no-store' in regenerated.headers['cache-control']
    replacements = regenerated.json()['recovery_codes']
    assert replacements and replacements != original_codes
    assert runtime['owner_access'].recovery_codes_remaining() == len(replacements)
    assert runtime['owner_access'].consume_recovery_code(original_codes[0]) is False
    assert all('recovery_codes' not in str(event) for event in events.history() if isinstance(event, dict)) if hasattr(events, 'history') else True

    assert client.get('/iphone/api/status').status_code == 423
    # Profile pictures must be authorized by the SAME first-device setup
    # ceremony, bound to the canonical owner and private to trusted devices.
    stranger = TestClient(app, base_url='https://testserver')
    assert stranger.put('/iphone/api/first-run/avatar', json={
        'source': 'preset', 'preset_id': 'blue',
    }).status_code == 401
    assert stranger.get('/iphone/api/access/profile/avatar').status_code == 401
    saved_avatar = client.put('/iphone/api/first-run/avatar', json={
        'source': 'preset', 'preset_id': 'forest',
    })
    assert saved_avatar.status_code == 200, saved_avatar.text
    assert saved_avatar.json()['saved'] is True
    assert client.get('/iphone/api/access/profile/avatar').json() == {
        'source': 'preset', 'preset_id': 'forest',
    }
    assert client.get('/iphone/api/access/profile/avatar/image').status_code == 404
    import io
    from PIL import Image
    content = io.BytesIO()
    Image.new('RGB', (8, 8), (40, 200, 255)).save(content, format='JPEG')
    uploaded = client.put('/iphone/api/first-run/avatar', json={
        'source': 'upload', 'image_b64': base64.b64encode(content.getvalue()).decode(),
    })
    assert uploaded.status_code == 200, uploaded.text
    image = client.get('/iphone/api/access/profile/avatar/image')
    assert image.status_code == 200 and image.content.startswith(b'\x89PNG')
    assert image.headers['cache-control'] == 'private, no-store'
    assert stranger.get('/iphone/api/access/profile/avatar/image').status_code == 401
    invalid = client.put('/iphone/api/first-run/avatar', json={
        'source': 'upload', 'image_b64': base64.b64encode(b'<svg/>').decode(),
    })
    assert invalid.status_code == 422
    assert client.get('/iphone/api/access/profile/avatar/image').content == image.content
    model_choice = client.post('/iphone/api/first-run/model', json={
        'provider_id': 'deepseek', 'model': 'deepseek-chat',
        'api_key': 'secret-test-provider-key-1234567890',
    })
    assert model_choice.status_code == 200, model_choice.text

    completed = client.post('/iphone/api/first-run/complete', json={
        'recovery_saved': True, 'privacy_mode': 'local_only',
        'autonomy_mode': 'ask', 'passkey_unavailable_confirmed': True,
    })
    assert completed.status_code == 200, completed.text
    assert setup.ready is True
    assert client.put('/iphone/api/first-run/avatar', json={
        'source': 'preset', 'preset_id': 'horizon',
    }).status_code == 409
    assert client.get('/iphone/api/access/profile/avatar').json()['source'] == 'upload'
    assert client.get('/iphone/api/status').status_code == 200
    duplicate = client.post('/iphone/api/first-run/create', json={
        'bootstrap_secret': bootstrap, 'first_name': 'Different',
        'password': 'another sufficiently long password',
    })
    assert duplicate.status_code == 409


def test_local_web_first_run_needs_no_setup_code_when_runtime_is_loopback_only(tmp_path):
    events = EventBus()
    registry = Registry()
    runtime = {
        'device_registry': registry,
        'executor': Executor(),
        'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
        'preferences': Preferences(tmp_path / 'preferences.json'),
        'models': SimpleNamespace(set_owner_privacy=lambda mode: None,
                                  set_default_provider=lambda provider: {'provider': provider},
                                  connect_owner_provider=lambda provider, key, model: {'provider': provider, 'model': model},
                                  status=lambda: {'state': 'unconfigured'}),
        'tools': SimpleNamespace(set_autonomy_mode=lambda mode: None),
    }
    setup = FirstRunCoordinator(tmp_path, runtime=runtime)
    setup.should_run()
    runtime['first_run_setup'] = setup
    runtime['pwa_sessions'] = PwaSessionStore(tmp_path / 'pwa-sessions.sqlite3', ttl_seconds=600)
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='', iphone_pwa_allow_insecure=True,
        # A developer may start the local launcher from a shell with a
        # bootstrap secret inherited from .env. Loopback setup must not ask
        # them to paste that hosted-runtime secret into a fresh local owner.
        control_server_host='127.0.0.1', owner_bootstrap_secret='B' * 40,
        data_dir=tmp_path,
        google_signin_client_id='', owner_google_email='',
    )
    runtime['settings'] = settings
    app = FastAPI()
    app.add_middleware(PwaSessionMiddleware, sessions=runtime['pwa_sessions'],
                       device_registry=registry, cookie_max_age=600,
                       first_run_setup=setup, cookie_secure=False)
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 12345))

    options = client.get('/iphone/api/access/options').json()
    assert options['creation_available'] is True
    assert options['local_setup_available'] is True
    created = client.post('/iphone/api/first-run/create', json={
        'first_name': 'Vaishnav', 'display_name': 'Vaishnav',
        'password': 'a sufficiently long local password',
    })
    assert created.status_code == 200, created.text
    assert runtime['owner_access'].identity() is not None
    original_device_id = created.json()['device']['id']
    client.cookies.delete('pa_device')
    client.cookies.delete('pa_token')
    reconnected = client.post('/iphone/api/first-run/resume', json={
        'password': 'a sufficiently long local password',
        'device_name': 'Replacement local browser',
    })
    assert reconnected.status_code == 200, reconnected.text
    replacement_device_id = reconnected.json()['device_id']
    assert replacement_device_id != original_device_id
    assert not runtime['device_registry'].is_active(original_device_id)
    assert runtime['device_registry'].is_active(replacement_device_id)
    resumed = client.post('/iphone/api/first-run/resume', json={})
    assert resumed.status_code == 200, resumed.text
    assert 'pa_setup_claim=' in resumed.headers.get('set-cookie', '')
    regenerated = client.post('/iphone/api/first-run/recovery-codes', json={})
    assert regenerated.status_code == 200, regenerated.text
    assert len(regenerated.json()['recovery_codes']) == 8
    saved_recovery = client.post('/iphone/api/first-run/recovery-saved', json={'saved': True})
    assert saved_recovery.status_code == 200, saved_recovery.text
    options = client.get('/iphone/api/access/options').json()
    assert options['setup_in_progress'] is True
    assert options['setup_resume_step'] == 4
    assert options['setup_recovery_saved'] is True
    regenerated_after_ack = client.post('/iphone/api/first-run/recovery-codes', json={})
    assert regenerated_after_ack.status_code == 200, regenerated_after_ack.text
    options = client.get('/iphone/api/access/options').json()
    assert options['setup_recovery_saved'] is False, 'new recovery codes must invalidate the previous save acknowledgement'
    saved_recovery = client.post('/iphone/api/first-run/recovery-saved', json={'saved': True})
    assert saved_recovery.status_code == 200, saved_recovery.text
    recovery_count = runtime['owner_access'].recovery_codes_remaining()
    duplicate = client.post('/iphone/api/first-run/create', json={
        'first_name': 'Vaishnav', 'display_name': 'Vaishnav',
        'password': 'a different sufficiently long password',
    })
    assert duplicate.status_code == 409
    assert 'Resume the pending setup' in duplicate.json()['detail']
    assert runtime['owner_access'].recovery_codes_remaining() == recovery_count
    saved_policy = client.put('/iphone/api/first-run/data-policy', json={
        'default_policy': 'device_only',
    })
    assert saved_policy.status_code == 200, saved_policy.text
    assert saved_policy.json()['settings']['default_policy'] == 'device_only'
    # The ordinary settings API remains unavailable until setup is complete;
    # only the setup-claim-bound endpoint may save the first-run choice.
    ordinary_policy = client.put('/iphone/api/data-plane/settings', json={
        'default_policy': 'sync_everywhere',
    })
    assert ordinary_policy.status_code == 423, ordinary_policy.text


def test_insecure_development_flag_does_not_allow_secretless_setup_on_public_bind(tmp_path):
    events = EventBus()
    runtime = {
        'device_registry': Registry(), 'executor': Executor(), 'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(), 'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
    }
    setup = FirstRunCoordinator(tmp_path, runtime=runtime)
    setup.should_run()
    runtime['first_run_setup'] = setup
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='', iphone_pwa_allow_insecure=True,
        control_server_host='0.0.0.0', owner_bootstrap_secret='',
        google_signin_client_id='', owner_google_email='',
    )
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 12345))
    options = client.get('/iphone/api/access/options').json()
    assert options['creation_available'] is False
    assert options['local_setup_available'] is False


def test_native_first_run_uses_canonical_identity_and_retries_without_duplicate_device(tmp_path):
    bootstrap = 'B' * 40
    events = EventBus()
    registry = Registry()
    runtime = {
        'device_registry': registry,
        'executor': Executor(),
        'events': events,
        'continuity': ContinuityService(tmp_path / 'continuity.sqlite3', events=events),
        'voice_qualification': Recorder(),
        'owner_access': OwnerAccessStore(tmp_path / 'owner-access.sqlite3'),
        'preferences': Preferences(tmp_path / 'preferences.json'),
        'models': SimpleNamespace(set_owner_privacy=lambda mode: None,
                                  set_default_provider=lambda provider: {'provider': provider},
                                  connect_owner_provider=lambda provider, key, model: {'provider': provider, 'model': model},
                                  status=lambda: {'state': 'unconfigured'}),
        'tools': SimpleNamespace(set_autonomy_mode=lambda mode: None),
    }
    setup = FirstRunCoordinator(tmp_path, runtime=runtime)
    setup.should_run()
    runtime['first_run_setup'] = setup
    settings = SimpleNamespace(
        base_dir=Path(__file__).resolve().parent.parent,
        iphone_owner_enrollment_code='', iphone_pwa_allow_insecure=False,
        owner_bootstrap_secret=bootstrap, google_signin_client_id='', owner_google_email='',
    )
    app = FastAPI()
    app.include_router(iphone_pwa_router(runtime, settings))
    client = TestClient(app, base_url='https://testserver')
    request = {
        'bootstrap_secret': bootstrap,
        'setup_claim': 'C' * 48,
        'first_name': 'Ada',
        'last_name': 'Lovelace',
        'display_name': 'Ada',
        'password': 'a sufficiently long password',
        'device_id': str(uuid.uuid4()),
        'device_token': 'D' * 48,
        'device_name': 'Ada Android',
        'platform': 'android',
    }
    denied = client.post('/iphone/api/first-run/native/create', json={
        **request, 'bootstrap_secret': 'wrong' * 8,
    })
    assert denied.status_code == 401
    assert runtime['owner_access'].identity() is None
    assert registry.active == set()
    created = client.post('/iphone/api/first-run/native/create', json=request)
    assert created.status_code == 200, created.text
    first = created.json()
    owner = runtime['owner_access'].identity()
    assert first['identity']['owner_id'] == owner['owner_id']
    assert first['device']['id'] == request['device_id']
    assert first['device']['platform'] == 'android'
    assert 'device_token' not in first
    assert len(first['recovery_codes']) >= 4
    assert runtime['owner_access'].recovery_codes_remaining() == len(first['recovery_codes'])

    # A retry after a lost response keeps the owner and Device 1 stable. The
    # previous unacknowledged code set is rotated and the replacement is shown.
    retried = client.post('/iphone/api/first-run/native/create', json=request)
    assert retried.status_code == 200, retried.text
    assert retried.json()['identity']['owner_id'] == owner['owner_id']
    assert retried.json()['device']['id'] == request['device_id']
    assert len(registry.active) == 1
    assert retried.json()['recovery_codes'] != first['recovery_codes']

    model_config = {
        'setup_claim': request['setup_claim'], 'device_id': request['device_id'],
        'device_token': request['device_token'], 'provider_id': 'deepseek',
        'model': 'deepseek-chat', 'api_key': 'secret-test-provider-key-1234567890',
    }
    model_audit = []
    events.subscribe('owner.first_run.model_configured', model_audit.append)
    denied_model = client.post('/iphone/api/first-run/native/model', json={
        **model_config, 'device_token': 'X' * 48,
    })
    assert denied_model.status_code == 401
    configured_model = client.post('/iphone/api/first-run/native/model', json=model_config)
    assert configured_model.status_code == 200, configured_model.text
    assert configured_model.json()['provider'] == 'deepseek'
    assert model_audit == [{
        'event': 'owner.first_run.model_configured',
        'device_id': request['device_id'], 'provider_id': 'deepseek',
    }]
    assert model_config['api_key'] not in repr(model_audit)

    stolen = client.post('/iphone/api/first-run/native/complete', json={
        'setup_claim': request['setup_claim'],
        'device_id': request['device_id'],
        'device_token': 'X' * 48,
        'recovery_saved': True,
        'privacy_mode': 'local_only',
        'model_choice': 'configured',
    })
    assert stolen.status_code == 401
    assert setup.ready is False
    completed = client.post('/iphone/api/first-run/native/complete', json={
        'setup_claim': request['setup_claim'],
        'device_id': request['device_id'],
        'device_token': request['device_token'],
        'recovery_saved': True,
        'privacy_mode': 'local_only',
        'model_choice': 'configured',
    })
    assert completed.status_code == 200, completed.text
    assert completed.json()['vishnu_id'] == owner['vishnu_id']
    assert setup.ready is True
    retried_completion = client.post('/iphone/api/first-run/native/complete', json={
        'setup_claim': request['setup_claim'], 'device_id': request['device_id'],
        'device_token': request['device_token'], 'recovery_saved': True,
        'privacy_mode': 'local_only', 'model_choice': 'configured',
    })
    assert retried_completion.status_code == 200
    duplicate = client.post('/iphone/api/first-run/native/create', json=request)
    assert duplicate.status_code == 200 and duplicate.json()['status'] == 'ready'
    recovery_device_id = str(uuid.uuid4())
    recovery_payload = {
        'recovery_code': retried.json()['recovery_codes'][0],
        'device_id': recovery_device_id,
        'device_token': 'R' * 48,
        'device_name': 'Replacement iPhone',
        'platform': 'ios',
    }
    restored = client.post('/iphone/api/access/native/recovery', json=recovery_payload)
    assert restored.status_code == 200, restored.text
    assert restored.json()['status'] == 'ready'
    assert restored.json()['identity']['vishnu_id'] == owner['vishnu_id']
    assert registry.authenticate(recovery_device_id, 'R' * 48)
    # Device 1 is historical metadata, not the identity root. Losing and
    # revoking it must leave the recovered device and owner identity usable.
    assert registry.revoke(request['device_id']) is True
    assert registry.authenticate(request['device_id'], request['device_token']) is False
    assert registry.authenticate(recovery_device_id, 'R' * 48) is True
    assert runtime['owner_access'].identity()['vishnu_id'] == owner['vishnu_id']
    replayed = client.post('/iphone/api/access/native/recovery', json={
        **recovery_payload, 'device_id': str(uuid.uuid4()), 'device_token': 'S' * 48,
    })
    assert replayed.status_code == 401



def test_stale_owner_reauthentication_fails_closed_for_conversation_delete(tmp_path):
    client, runtime = make_client(tmp_path, server_sessions=True)
    enrolled = client.post('/iphone/api/enroll', json={'code': 'this-is-a-long-owner-code'})
    assert enrolled.status_code == 200
    created = client.post('/iphone/api/conversations', json={'title': 'Keep this chat'})
    assert created.status_code == 200
    thread_id = created.json()['conversation']['id']
    session_id = next(iter(runtime['pwa_sessions'].active_for_device(enrolled.json()['device_id']))).id
    assert runtime['pwa_sessions'].mark_reauthenticated(session_id, at=time.time() - 1000)
    path = f'/iphone/api/conversations/{thread_id}'
    rejected = client.delete(path + '?confirm=true')
    assert rejected.status_code == 401
    assert rejected.json()['detail']['code'] == 'reauthentication_required'
    assert client.get(path).status_code == 200



def test_stage8_rotating_forwarded_addresses_cannot_bypass_global_access_limit(tmp_path):
    client, _ = make_client(tmp_path)
    for index in range(25):
        response = client.post(
            '/iphone/api/enroll',
            json={'code': 'wrong'},
            headers={'x-forwarded-for': f'198.51.100.{index + 1}'},
        )
        assert response.status_code == 401

    blocked = client.post(
        '/iphone/api/enroll',
        json={'code': 'wrong'},
        headers={'x-forwarded-for': '203.0.113.250'},
    )
    assert blocked.status_code == 429
