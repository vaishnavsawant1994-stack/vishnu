from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import time
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, SecretStr
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from agent.executor import ConfirmationRequired, ExecutionCancelled
from models.router import ModelError
from security.owner_access import OwnerAccessStore
from security.owner_access import FirstRunClaimBusy
from security.request_context import current_trusted_request


class OwnerEnrollBody(BaseModel):
    code: str
    name: str = 'Owner iPhone'


class OwnerPasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    name: str = Field(default='Owner browser', max_length=120)


class OwnerPasswordSetupBody(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class OwnerRecoveryBody(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    name: str = Field(default='Recovered owner browser', max_length=120)


class GoogleLoginBody(BaseModel):
    credential: str = Field(min_length=100, max_length=8192)
    name: str = Field(default='Google owner browser', max_length=120)


class PasskeyCompleteBody(BaseModel):
    challenge_id: str = Field(min_length=10, max_length=80)
    credential: dict
    name: str = Field(default='Owner Face ID', max_length=120)


class FirstRunCreateBody(BaseModel):
    bootstrap_secret: SecretStr = Field(min_length=32, max_length=256)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default='', max_length=80)
    display_name: str = Field(default='', max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)
    device_name: str = Field(default='First trusted browser', max_length=120)


class FirstRunCompleteBody(BaseModel):
    recovery_saved: bool
    privacy_mode: Literal['local_only', 'local_preferred', 'external_allowed'] = 'local_only'
    autonomy_mode: Literal['observe', 'suggest', 'ask', 'act'] = 'ask'
    passkey_unavailable_confirmed: bool = False


class FirstRunModelBody(BaseModel):
    provider_id: Literal[
        'skip', 'local', 'openai', 'gemini', 'openrouter', 'deepseek',
        'xai', 'groq', 'cerebras', 'mistral', 'custom',
    ]
    model: str = Field(default='', max_length=200)
    api_key: SecretStr = Field(default=SecretStr(''), max_length=2048)


class NativeFirstRunCreateBody(BaseModel):
    bootstrap_secret: SecretStr = Field(min_length=32, max_length=256)
    setup_claim: SecretStr = Field(min_length=32, max_length=256)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default='', max_length=80)
    display_name: str = Field(default='', max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)
    device_id: str = Field(min_length=36, max_length=36)
    device_token: SecretStr = Field(min_length=32, max_length=256)
    device_name: str = Field(min_length=1, max_length=120)
    platform: Literal['android', 'ios']


class NativeFirstRunCompleteBody(BaseModel):
    setup_claim: SecretStr = Field(min_length=32, max_length=256)
    device_id: str = Field(min_length=36, max_length=36)
    device_token: SecretStr = Field(min_length=32, max_length=256)
    recovery_saved: Literal[True]
    privacy_mode: Literal['local_only', 'local_preferred', 'external_allowed'] = 'local_only'
    model_choice: Literal['configure_later', 'configured']


class NativeFirstRunModelBody(BaseModel):
    setup_claim: SecretStr = Field(min_length=32, max_length=256)
    device_id: str = Field(min_length=36, max_length=36)
    device_token: SecretStr = Field(min_length=32, max_length=256)
    provider_id: Literal[
        'skip', 'local', 'openai', 'gemini', 'openrouter', 'deepseek',
        'xai', 'groq', 'cerebras', 'mistral', 'custom',
    ]
    model: str = Field(default='', max_length=200)
    api_key: SecretStr = Field(default=SecretStr(''), max_length=2048)


class NativeRecoveryBody(BaseModel):
    recovery_code: SecretStr = Field(min_length=8, max_length=64)
    device_id: str = Field(min_length=36, max_length=36)
    device_token: SecretStr = Field(min_length=32, max_length=256)
    device_name: str = Field(min_length=1, max_length=120)
    platform: Literal['android', 'ios']


class VoiceTurnBody(BaseModel):
    transcript: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=80)


class BargeBody(BaseModel):
    speaking: bool = True


class VoiceClientEventBody(BaseModel):
    event: Literal['tts_started', 'tts_completed', 'tts_error']
    detail: str = Field(default='', max_length=160)


class QualificationStartBody(BaseModel):
    environment: dict = Field(default_factory=dict)
    notes: str = 'iPhone Safari physical voice qualification'


class QualificationTakeoverBody(QualificationStartBody):
    confirm: Literal[True]


class ConversationCreateBody(BaseModel):
    title: str = Field(default='New conversation', max_length=120)


class ConversationRenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class IphonePwaState:
    def __init__(self):
        self._lock = threading.RLock()
        self._cancel: dict[str, threading.Event] = {}

    def begin_turn(self, device_id: str) -> threading.Event:
        with self._lock:
            previous = self._cancel.get(device_id)
            if previous:
                previous.set()
            current = threading.Event()
            self._cancel[device_id] = current
            return current

    def cancel(self, device_id: str) -> bool:
        with self._lock:
            current = self._cancel.get(device_id)
            if not current:
                return False
            current.set()
            return True

    def finish(self, device_id: str, event: threading.Event):
        with self._lock:
            if self._cancel.get(device_id) is event:
                self._cancel.pop(device_id, None)


def iphone_pwa_router(runtime, settings, *, include_legacy_runtime_routes: bool = True):
    router = APIRouter(prefix='/iphone', tags=['iphone-pwa'])
    state = IphonePwaState()
    web_dir = Path(settings.base_dir) / 'pwa'
    registry = runtime['device_registry']
    executor = runtime['executor']
    events = runtime.get('events')
    continuity = runtime.get('continuity')
    recorder = runtime.get('voice_qualification')
    owner_access: OwnerAccessStore = runtime['owner_access']
    first_run_setup = runtime.get('first_run_setup')
    pending_approvals: dict[str, dict] = {}
    pending_approvals_lock = threading.RLock()
    failed_access_attempts: dict[str, list[float]] = {}
    access_attempts_lock = threading.RLock()
    access_failure_window_seconds = 300
    per_client_failure_limit = 5
    global_method_failure_limit = 25

    def device_cookie_kwargs():
        cookie_days = max(1, min(int(getattr(settings, 'iphone_device_cookie_days', 365)), 3650))
        return dict(
            httponly=True,
            secure=not getattr(settings, 'iphone_pwa_allow_insecure', False),
            samesite='strict',
            path='/iphone',
            max_age=60 * 60 * 24 * cookie_days,
        )

    def require_https(request: Request):
        forwarded = request.headers.get('x-forwarded-proto', '').split(',')[0].strip().lower()
        scheme = forwarded or request.url.scheme.lower()
        if scheme != 'https' and not getattr(settings, 'iphone_pwa_allow_insecure', False):
            raise HTTPException(400, 'iPhone owner enrollment requires HTTPS')

    def request_identity(request: Request):
        forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
        host = forwarded_host or request.headers.get('host', '').strip()
        forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip().lower()
        proto = forwarded_proto or request.url.scheme.lower()
        if not host or proto != 'https':
            raise HTTPException(400, 'Secure HTTPS origin required')
        rp_id = host.rsplit(':', 1)[0] if host.count(':') == 1 else host.strip('[]')
        return rp_id, f'{proto}://{host}'

    def access_attempt_keys(request: Request, method: str):
        forwarded = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        try:
            address = str(ipaddress.ip_address(forwarded)) if forwarded else ''
        except ValueError:
            address = ''
        if not address:
            peer = request.client.host if request.client else 'unknown'
            try:
                address = str(ipaddress.ip_address(peer))
            except ValueError:
                address = str(peer or 'unknown')[:80]
        method = str(method)[:40]
        return (f'client:{method}:{address}', f'global:{method}')

    def allow_access_attempt(request: Request, method: str):
        keys = access_attempt_keys(request, method)
        cutoff = time.monotonic() - access_failure_window_seconds
        with access_attempts_lock:
            for stored_key in list(failed_access_attempts):
                attempts = [stamp for stamp in failed_access_attempts[stored_key] if stamp >= cutoff]
                if attempts:
                    failed_access_attempts[stored_key] = attempts
                else:
                    failed_access_attempts.pop(stored_key, None)
            client_attempts = failed_access_attempts.get(keys[0], [])
            global_attempts = failed_access_attempts.get(keys[1], [])
        if len(client_attempts) >= per_client_failure_limit or len(global_attempts) >= global_method_failure_limit:
            raise HTTPException(429, 'Too many unsuccessful attempts. Wait five minutes and try again.')
        return keys

    def failed_access_attempt(keys):
        stamp = time.monotonic()
        with access_attempts_lock:
            for key in keys:
                failed_access_attempts.setdefault(key, []).append(stamp)

    def clear_access_attempts(keys):
        with access_attempts_lock:
            for key in keys:
                failed_access_attempts.pop(key, None)

    def trust_browser(response: Response, name: str, platform: str = 'web-pwa'):
        device, token = registry.enroll(str(name or 'Owner browser').strip()[:120], platform)
        if hasattr(registry, 'set_permissions') and hasattr(registry, 'OWNER_SCOPES'):
            registry.set_permissions(device['id'], registry.OWNER_SCOPES)
        if continuity:
            continuity.resume(device['id'])
        cookie_kwargs = device_cookie_kwargs()
        response.set_cookie('pa_device', device['id'], **cookie_kwargs)
        response.set_cookie('pa_token', token, **cookie_kwargs)
        emit('owner.access.trusted', device_id=device['id'], platform=platform)
        return device

    def auth_device(device_id: str | None, device_token: str | None):
        if not device_id or not device_token or not registry.authenticate(device_id, device_token):
            raise HTTPException(401, 'iPhone session is not enrolled or has been revoked')
        if not registry.is_active(device_id):
            raise HTTPException(401, 'iPhone device is revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, 'ai:chat'):
            raise HTTPException(403, 'This device is not permitted to use conversation or voice')
        return device_id

    def require_fresh_owner_verification(device_id: str):
        # The production cloud app installs PwaSessionMiddleware and provides
        # pwa_sessions. Isolated compatibility routers may intentionally omit it.
        if runtime.get('pwa_sessions') is None:
            return
        context = current_trusted_request()
        ttl = int(getattr(runtime.get('agent_executor'), 'reauth_ttl_seconds', 300) or 300)
        ttl = max(30, min(ttl, 900))
        stamp = getattr(context, 'reauthenticated_at', None) if context is not None else None
        try:
            age = time.time() - float(stamp)
        except (TypeError, ValueError):
            age = ttl + 1
        if context is None or context.device_id != device_id or age < 0 or age > ttl:
            raise HTTPException(401, {
                'code': 'reauthentication_required',
                'message': 'Fresh owner verification is required for this security-sensitive action.',
            })

    def emit(name: str, **payload):
        if events:
            events.emit(name, **payload)

    def resolve_conversation(device_id: str, conversation_id: str | None = None):
        if continuity is None:
            return None
        if conversation_id:
            thread = continuity.thread(conversation_id)
            if not thread or thread.get('closed_at'):
                raise HTTPException(404, 'Conversation not found')
            continuity.set_active(device_id, thread['id'])
            return thread
        bundle = continuity.resume(device_id, event_limit=100)
        return bundle.get('thread')

    def append_conversation(thread, device_id: str, kind: str, text: str, **payload):
        if not thread or continuity is None:
            return
        continuity.append(
            thread['id'],
            device_id=device_id,
            kind=kind,
            payload={'text': text, **payload},
        )

    def model_history(thread):
        if not thread or continuity is None:
            return None
        roles = {'user_message': 'user', 'assistant_message': 'assistant'}
        history = []
        for event in continuity.events_for_thread(thread['id'], limit=1000):
            role = roles.get(event.get('kind'))
            text = str(event.get('payload', {}).get('text') or '').strip()
            if role and text:
                history.append({'role': role, 'content': text})
        return history[-16:]

    @router.get('', response_class=HTMLResponse, include_in_schema=False)
    @router.get('/', response_class=HTMLResponse, include_in_schema=False)
    def iphone_home():
        page = (web_dir / 'index.html').read_text(encoding='utf-8')
        page = page.replace(
            '</body>',
            '<script src="/iphone/first-run.js" defer></script>'
            '<script src="/iphone/first-run-actions.js" defer></script></body>',
        )
        return HTMLResponse(page, headers={'Cache-Control': 'no-store'})

    @router.get('/first-run.js', include_in_schema=False)
    def first_run_script():
        return Response((web_dir / 'first-run.js').read_text(encoding='utf-8'),
                        media_type='application/javascript',
                        headers={'Cache-Control': 'no-cache'})

    @router.get('/first-run-actions.js', include_in_schema=False)
    def first_run_actions_script():
        return Response((web_dir / 'first-run-actions.js').read_text(encoding='utf-8'),
                        media_type='application/javascript',
                        headers={'Cache-Control': 'no-cache'})

    @router.get('/manifest.webmanifest', include_in_schema=False)
    def manifest():
        return Response((web_dir / 'manifest.webmanifest').read_text(encoding='utf-8'), media_type='application/manifest+json')

    @router.get('/sw.js', include_in_schema=False)
    def service_worker():
        return Response((web_dir / 'sw.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/projects-workspace.js', include_in_schema=False)
    def projects_workspace_script():
        return Response((web_dir / 'projects-workspace.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/home-chat-redesign.js', include_in_schema=False)
    def home_chat_redesign_script():
        return Response((web_dir / 'home-chat-redesign.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/reference-home.js', include_in_schema=False)
    def reference_home_script():
        return Response((web_dir / 'reference-home.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/reference-home.css', include_in_schema=False)
    def reference_home_styles():
        return Response((web_dir / 'reference-home.css').read_text(encoding='utf-8'), media_type='text/css', headers={'Cache-Control': 'no-cache'})

    @router.get('/reference-pages.js', include_in_schema=False)
    def reference_pages_script():
        return Response((web_dir / 'reference-pages.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/reference-pages.css', include_in_schema=False)
    def reference_pages_styles():
        return Response((web_dir / 'reference-pages.css').read_text(encoding='utf-8'), media_type='text/css', headers={'Cache-Control': 'no-cache'})

    @router.get('/owner-controls.js', include_in_schema=False)
    def owner_controls_script():
        return Response((web_dir / 'owner-controls.js').read_text(encoding='utf-8'), media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @router.get('/owner-controls.css', include_in_schema=False)
    def owner_controls_styles():
        return Response((web_dir / 'owner-controls.css').read_text(encoding='utf-8'), media_type='text/css', headers={'Cache-Control': 'no-cache'})

    @router.get('/projects-workspace.css', include_in_schema=False)
    def projects_workspace_styles():
        return Response((web_dir / 'projects-workspace.css').read_text(encoding='utf-8'), media_type='text/css', headers={'Cache-Control': 'no-cache'})

    @router.get('/api/status')
    def status(
        response: Response,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        # Successful use renews this browser's durable trust without changing
        # its scoped credential or weakening revocation checks.
        response.set_cookie('pa_device', device_id, **device_cookie_kwargs())
        response.set_cookie('pa_token', pa_token, **device_cookie_kwargs())
        active_qualification = None
        if recorder is not None:
            active = recorder.active_session()
            if active and active.get('environment', {}).get('device_id') == device_id:
                active_qualification = {
                    'session_id': active['id'],
                    'evidence_class': active['evidence_class'],
                    'started_at': active.get('started_at'),
                }
        conversation = None
        conversations = []
        if continuity is not None:
            bundle = continuity.resume(device_id, event_limit=100)
            conversation = bundle
            conversations = continuity.list_threads(limit=50)
        memory_count = 0
        second_brain = runtime.get('second_brain')
        if second_brain is not None:
            try:
                memory_count = len(second_brain.graph().get('nodes', []))
            except Exception:
                memory_count = 0
        preferences = runtime.get('preferences')
        owner_display_name = ''
        if preferences is not None:
            try:
                owner_display_name = str(preferences.get('preferred_name', '') or '').strip()[:80]
            except Exception:
                owner_display_name = ''
        return {
            'ok': True,
            'device_id': device_id,
            'owner_display_name': owner_display_name,
            'voice_qualification_available': recorder is not None,
            'active_qualification': active_qualification,
            'continuity_available': continuity is not None,
            'conversation': conversation,
            'conversations': conversations,
            'memory_count': memory_count,
            'model': runtime['models'].status() if runtime.get('models') else {'state': 'unavailable'},
        }

    @router.get('/api/access/options')
    def access_options():
        google_client_id = getattr(settings, 'google_signin_client_id', '').strip()
        owner_google_email = getattr(settings, 'owner_google_email', '').strip().casefold()
        setup_state = first_run_setup.snapshot() if first_run_setup is not None else {}
        bootstrap_secret = str(getattr(settings, 'owner_bootstrap_secret', '') or '').strip()
        creation_available = bool(
            first_run_setup is not None
            and not first_run_setup.ready
            and len(bootstrap_secret) >= 32
            and setup_state.get('status') in {'uninitialized', 'setup_in_progress'}
            and setup_state.get('mode') in {None, 'create'}
        )
        return {
            'creation_available': creation_available,
            'setup_in_progress': setup_state.get('status') == 'setup_in_progress',
            'model_setup_complete': bool({'model', 'model_skipped'} & set(setup_state.get('completed_steps', []))),
            'passkey_available': bool(owner_access.passkeys()),
            'password_available': owner_access.password_configured(),
            'recovery_available': owner_access.recovery_codes_remaining() > 0,
            'enrollment_available': len(getattr(settings, 'iphone_owner_enrollment_code', '').strip()) >= 12,
            'google_available': bool(google_client_id and owner_google_email),
            'google_client_id': google_client_id if google_client_id and owner_google_email else '',
        }

    @router.post('/api/first-run/create')
    def first_run_create(body: FirstRunCreateBody, request: Request, response: Response,
                         pa_setup_claim: str | None = Cookie(default=None),
                         pa_device: str | None = Cookie(default=None),
                         pa_token: str | None = Cookie(default=None)):
        if first_run_setup is None:
            raise HTTPException(503, 'First-device creation is unavailable on this Vishnu runtime')
        require_https(request)
        key = allow_access_attempt(request, 'first-run-bootstrap')
        expected = str(getattr(settings, 'owner_bootstrap_secret', '') or '').strip()
        if len(expected) < 32:
            raise HTTPException(503, 'Secure first-device bootstrap is not configured')
        if not hmac.compare_digest(body.bootstrap_secret.get_secret_value(), expected):
            failed_access_attempt(key)
            raise HTTPException(401, 'The Vishnu setup code is invalid')
        clear_access_attempts(key)
        if not first_run_setup.should_run():
            raise HTTPException(409, 'Vishnu is already initialized. Connect this device instead.')
        state = first_run_setup.snapshot()
        if state.get('status') not in {'uninitialized', 'setup_in_progress'} or state.get('mode') not in {None, 'create'}:
            raise HTTPException(409, 'This Vishnu setup cannot start a new creation ceremony')
        try:
            claim, created_claim = owner_access.acquire_first_run_claim(
                pa_setup_claim, ttl=900,
                allow_pending_identity=state.get('status') == 'setup_in_progress',
            )
        except FirstRunClaimBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        try:
            if state.get('status') == 'uninitialized':
                first_run_setup.begin('create')
            first_run_setup.configure_owner(
                first_name=body.first_name,
                last_name=body.last_name,
                display_name=body.display_name,
            )
            codes = first_run_setup.configure_security(body.password.get_secret_value())
            identity = first_run_setup.initialize_pending_identity()
        except Exception:
            if created_claim:
                owner_access.release_first_run_claim(claim)
            raise

        device = None
        if pa_device and pa_token and registry.authenticate(pa_device, pa_token):
            device = next((item for item in registry.list() if item['id'] == pa_device), None)
        if device is None:
            device = trust_browser(response, body.device_name, 'web-first-device')
        try:
            first_run_setup.record_first_device(device['id'])
        except RuntimeError as exc:
            if created_claim:
                owner_access.release_first_run_claim(claim)
            raise HTTPException(409, str(exc)) from exc
        response.set_cookie(
            'pa_setup_claim', claim,
            httponly=True, secure=not getattr(settings, 'iphone_pwa_allow_insecure', False),
            samesite='strict', path='/iphone', max_age=900,
        )
        emit('owner.security.configured', device_id=device['id'], method='password')
        return {
            'ok': True,
            'identity': identity,
            'device': {key: device[key] for key in ('id', 'name', 'platform') if key in device},
            'recovery_codes': codes,
            'recovery_codes_shown_once': True,
            'next': 'save_recovery_and_create_passkey',
        }

    @router.post('/api/first-run/native/create')
    def native_first_run_create(body: NativeFirstRunCreateBody, request: Request):
        """Create the canonical first owner from a native secure-storage client.

        The native client generates and persists its device ID, bearer secret,
        and setup claim before this request. Only hashes are stored centrally,
        so a retry after a lost response can safely return the same enrollment.
        """
        if first_run_setup is None:
            raise HTTPException(503, 'First-device creation is unavailable on this Vishnu runtime')
        require_https(request)
        try:
            device_id = str(uuid.UUID(body.device_id))
        except ValueError as exc:
            raise HTTPException(422, 'The native device ID is invalid') from exc
        if device_id != body.device_id.lower():
            raise HTTPException(422, 'The native device ID must be a canonical UUID')
        if first_run_setup.ready:
            state = first_run_setup.snapshot()
            if state.get('first_device_id') == device_id and registry.authenticate(
                    device_id, body.device_token.get_secret_value()):
                identity = owner_access.identity()
                device = next((item for item in registry.list() if item['id'] == device_id), None)
                return {'ok': True, 'status': 'ready', 'identity': identity, 'device': device}
            raise HTTPException(409, 'Vishnu is already initialized. Connect this device instead.')
        keys = allow_access_attempt(request, 'native-first-run-bootstrap')
        expected = str(getattr(settings, 'owner_bootstrap_secret', '') or '').strip()
        if len(expected) < 32:
            raise HTTPException(503, 'Secure first-device bootstrap is not configured')
        if not hmac.compare_digest(body.bootstrap_secret.get_secret_value(), expected):
            failed_access_attempt(keys)
            raise HTTPException(401, 'The Vishnu setup code is invalid')
        clear_access_attempts(keys)
        if not first_run_setup.should_run():
            raise HTTPException(409, 'Vishnu is already initialized. Connect this device instead.')
        state = first_run_setup.snapshot()
        if state.get('status') not in {'uninitialized', 'setup_in_progress'} or state.get('mode') not in {None, 'create'}:
            raise HTTPException(409, 'This Vishnu setup cannot start a new creation ceremony')
        claim = body.setup_claim.get_secret_value()
        owner_was_initialized = owner_access.identity() is not None
        security_was_configured = owner_access.password_configured()
        device_was_registered = registry.is_active(device_id)
        try:
            claim, _ = owner_access.acquire_first_run_claim(
                claim, ttl=900,
                allow_pending_identity=state.get('status') == 'setup_in_progress',
                allow_proposed=True,
            )
            if state.get('status') == 'uninitialized':
                first_run_setup.begin('create')
            first_run_setup.configure_owner(
                first_name=body.first_name,
                last_name=body.last_name,
                display_name=body.display_name,
            )
            codes = first_run_setup.configure_security(body.password.get_secret_value())
            identity = first_run_setup.initialize_pending_identity()
            device, _ = registry.enroll_with_credential(
                device_id, body.device_token.get_secret_value(),
                body.device_name, body.platform,
            )
            if continuity:
                continuity.resume(device['id'])
            first_run_setup.record_first_device(device['id'])
        except FirstRunClaimBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not security_was_configured:
            emit('owner.security.configured', device_id=device['id'], method='password')
        if not owner_was_initialized:
            emit('owner.first_device.registered', device_id=device['id'], platform=body.platform)
        if not device_was_registered:
            emit('device.registered', device_id=device['id'], platform=body.platform,
                 first_device=True, authorization='first_run')
        return {
            'ok': True,
            'identity': identity,
            'device': {key: device[key] for key in ('id', 'name', 'platform')},
            'recovery_codes': codes,
            'recovery_codes_shown_once': True,
            'next': 'save_recovery_and_finish_native_setup',
        }

    @router.post('/api/first-run/native/complete')
    def native_first_run_complete(body: NativeFirstRunCompleteBody, request: Request):
        if first_run_setup is None:
            raise HTTPException(503, 'First-device creation is unavailable on this Vishnu runtime')
        require_https(request)
        if first_run_setup.ready:
            state = first_run_setup.snapshot()
            if (state.get('first_device_id') == body.device_id
                    and registry.authenticate(body.device_id, body.device_token.get_secret_value())):
                return {'ok': True, 'status': 'ready',
                        'vishnu_id': owner_access.identity()['vishnu_id']}
            raise HTTPException(409, 'Vishnu is already initialized. Connect this device instead.')
        try:
            claim, claim_created = owner_access.acquire_first_run_claim(
                body.setup_claim.get_secret_value(), ttl=900,
                allow_pending_identity=True,
            )
        except (FirstRunClaimBusy, RuntimeError) as exc:
            raise HTTPException(401, 'The first-device setup session expired. Re-enter the runtime setup code to resume.') from exc
        if claim_created:
            owner_access.release_first_run_claim(claim)
            raise HTTPException(401, 'The first-device setup session expired. Re-enter the runtime setup code to resume.')
        device_id = body.device_id
        if not registry.authenticate(device_id, body.device_token.get_secret_value()):
            raise HTTPException(401, 'This trusted device credential is invalid or revoked')
        state = first_run_setup.snapshot()
        if state.get('first_device_id') != device_id:
            raise HTTPException(403, 'This device is not the first trusted device for the pending setup')
        try:
            first_run_setup.confirm_recovery_codes_saved()
            first_run_setup.configure_preferences(
                privacy_mode=body.privacy_mode,
                autonomy_mode='ask',
                memory_enabled=True,
            )
            if body.model_choice == 'configure_later':
                first_run_setup.skip_model_configuration()
            elif 'model' not in state.get('completed_steps', []):
                raise RuntimeError('Configure an AI provider or choose Configure later before finishing')
            result = first_run_setup.complete()
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        owner_access.release_first_run_claim(body.setup_claim.get_secret_value())
        emit('owner.first_run.completed', device_id=device_id,
             owner_id=result.get('identity', {}).get('owner_id'))
        return {'ok': True, 'status': 'ready', 'vishnu_id': owner_access.identity()['vishnu_id']}

    @router.post('/api/first-run/native/model')
    def native_first_run_model(body: NativeFirstRunModelBody, request: Request):
        """Configure the shared model router during native first-device setup.

        Provider credentials flow directly into the existing encrypted model
        credential store and are never persisted by the native onboarding UI.
        """
        if first_run_setup is None or first_run_setup.ready:
            raise HTTPException(409, 'Native first-device setup is not pending')
        require_https(request)
        try:
            claim, created = owner_access.acquire_first_run_claim(
                body.setup_claim.get_secret_value(), ttl=900,
                allow_pending_identity=True,
            )
        except (FirstRunClaimBusy, RuntimeError) as exc:
            raise HTTPException(401, 'The first-device setup session expired') from exc
        if created:
            owner_access.release_first_run_claim(claim)
            raise HTTPException(401, 'The first-device setup session expired')
        if not registry.authenticate(body.device_id, body.device_token.get_secret_value()):
            raise HTTPException(401, 'This trusted device credential is invalid or revoked')
        state = first_run_setup.snapshot()
        if (state.get('status') != 'setup_in_progress'
                or state.get('mode') != 'create'
                or state.get('first_device_id') != body.device_id):
            raise HTTPException(403, 'This device cannot configure the pending first-device setup')
        try:
            if body.provider_id == 'skip':
                result = first_run_setup.skip_model_configuration()
            else:
                result = first_run_setup.configure_model(
                    provider_id=body.provider_id,
                    model=body.model,
                    api_key=body.api_key.get_secret_value(),
                )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit('owner.first_run.model_configured', device_id=body.device_id,
             provider_id='skipped' if body.provider_id == 'skip' else body.provider_id)
        return {'ok': True, 'provider': body.provider_id,
                'configured': body.provider_id not in {'skip'}}

    @router.post('/api/access/native/recovery')
    def native_recovery(body: NativeRecoveryBody, request: Request):
        require_https(request)
        if first_run_setup is not None and not first_run_setup.ready:
            raise HTTPException(409, 'Finish the pending first-device setup before restoring another device')
        identity = owner_access.identity()
        if identity is None:
            raise HTTPException(409, 'This runtime has no initialized Vishnu identity')
        try:
            device_id = str(uuid.UUID(body.device_id))
        except ValueError as exc:
            raise HTTPException(422, 'The native device ID is invalid') from exc
        if device_id != body.device_id.lower():
            raise HTTPException(422, 'The native device ID must be a canonical UUID')
        keys = allow_access_attempt(request, 'native-recovery')
        # A retry after a lost HTTP response is safe because the client already
        # generated and persisted its device credential before sending it.
        if registry.authenticate(device_id, body.device_token.get_secret_value()):
            clear_access_attempts(keys)
            device = next((item for item in registry.list() if item['id'] == device_id), None)
            return {'ok': True, 'status': 'ready', 'identity': identity, 'device': device}
        if not owner_access.consume_recovery_code(body.recovery_code.get_secret_value()):
            failed_access_attempt(keys)
            raise HTTPException(401, 'Invalid or already used recovery code')
        clear_access_attempts(keys)
        try:
            device, _ = registry.enroll_with_credential(
                device_id, body.device_token.get_secret_value(),
                body.device_name, body.platform,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, 'This device could not be enrolled. Use another recovery code to retry.') from exc
        if continuity:
            continuity.resume(device['id'])
        emit('device.registered', device_id=device['id'], platform=body.platform,
             authorization='recovery_code')
        emit('owner.recovery.used', device_id=device['id'])
        emit('owner.device.recovered', device_id=device['id'], platform=body.platform)
        return {'ok': True, 'status': 'ready', 'identity': identity,
                'device': {key: device[key] for key in ('id', 'name', 'platform')}}

    @router.post('/api/first-run/complete')
    def first_run_complete(body: FirstRunCompleteBody, response: Response,
                           pa_setup_claim: str | None = Cookie(default=None),
                           pa_device: str | None = Cookie(default=None),
                           pa_token: str | None = Cookie(default=None)):
        if first_run_setup is None:
            raise HTTPException(503, 'First-device creation is unavailable on this Vishnu runtime')
        if not pa_setup_claim:
            raise HTTPException(401, 'The first-device setup session expired. Restart setup with your bootstrap code.')
        try:
            owner_access.acquire_first_run_claim(pa_setup_claim, ttl=900)
        except (FirstRunClaimBusy, RuntimeError) as exc:
            raise HTTPException(401, 'The first-device setup session expired. Restart setup with your bootstrap code.') from exc
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        if body.recovery_saved is not True:
            raise HTTPException(422, 'Confirm that you saved the one-time recovery codes before continuing')
        if not owner_access.passkeys() and not body.passkey_unavailable_confirmed:
            raise HTTPException(409, 'Create a passkey before finishing, or confirm that this browser cannot create one')
        try:
            first_run_setup.confirm_recovery_codes_saved()
            first_run_setup.configure_preferences(
                privacy_mode=body.privacy_mode,
                autonomy_mode=body.autonomy_mode,
                memory_enabled=True,
            )
            result = first_run_setup.complete()
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        owner_access.release_first_run_claim(pa_setup_claim)
        response.delete_cookie('pa_setup_claim', path='/iphone')
        emit('owner.first_run.completed', device_id=device_id,
             owner_id=result.get('identity', {}).get('owner_id'))
        return {'ok': True, 'status': 'ready', 'vishnu_id': owner_access.identity()['vishnu_id']}

    @router.post('/api/first-run/model')
    def first_run_model(body: FirstRunModelBody, request: Request,
                        pa_setup_claim: str | None = Cookie(default=None),
                        pa_device: str | None = Cookie(default=None),
                        pa_token: str | None = Cookie(default=None)):
        if first_run_setup is None or not pa_setup_claim:
            raise HTTPException(401, 'The first-device setup session expired')
        try:
            owner_access.acquire_first_run_claim(pa_setup_claim, ttl=900)
        except (FirstRunClaimBusy, RuntimeError) as exc:
            raise HTTPException(401, 'The first-device setup session expired') from exc
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        require_https(request)
        try:
            if body.provider_id == 'skip':
                result = first_run_setup.skip_model_configuration()
            else:
                result = first_run_setup.configure_model(
                    provider_id=body.provider_id, model=body.model,
                    api_key=body.api_key.get_secret_value(),
                )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit('owner.first_run.model_configured', device_id=device_id,
             provider_id='skipped' if body.provider_id == 'skip' else body.provider_id)
        return {'ok': True, 'provider': body.provider_id, 'configured': body.provider_id != 'skip'}

    @router.get('/api/access/security')
    def access_security(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        auth_device(pa_device, pa_token)
        return {
            'password_configured': owner_access.password_configured(),
            'recovery_codes_remaining': owner_access.recovery_codes_remaining(),
            'passkeys': owner_access.passkeys(),
            'google_configured': bool(
                getattr(settings, 'google_signin_client_id', '').strip()
                and getattr(settings, 'owner_google_email', '').strip()
            ),
        }

    @router.post('/api/access/google/login')
    def google_login(body: GoogleLoginBody, request: Request, response: Response):
        require_https(request)
        key = allow_access_attempt(request, 'google')
        client_id = getattr(settings, 'google_signin_client_id', '').strip()
        owner_email = getattr(settings, 'owner_google_email', '').strip().casefold()
        if not client_id or not owner_email:
            raise HTTPException(503, 'Google owner sign-in is not configured')
        try:
            claims = google_id_token.verify_oauth2_token(
                body.credential,
                GoogleAuthRequest(),
                client_id,
            )
            email = str(claims.get('email') or '').strip().casefold()
            verified = claims.get('email_verified') is True or str(claims.get('email_verified')).lower() == 'true'
            subject = str(claims.get('sub') or '').strip()
            if not verified or not subject or not hmac.compare_digest(email, owner_email):
                raise ValueError('Google account is not the configured owner')
        except Exception:
            failed_access_attempt(key)
            raise HTTPException(401, 'This Google account is not authorized for Vishnu')
        clear_access_attempts(key)
        device = trust_browser(response, body.name, 'web-pwa-google')
        emit('owner.google.login', device_id=device['id'], provider='google')
        return {'ok': True, 'device_id': device['id']}

    @router.post('/api/access/password/setup')
    def password_setup(
        body: OwnerPasswordSetupBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            owner_access.set_password(body.password)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        emit('owner.password.updated', device_id=device_id)
        return {'ok': True}

    @router.post('/api/access/password/login')
    def password_login(body: OwnerPasswordBody, request: Request, response: Response):
        require_https(request)
        key = allow_access_attempt(request, 'password')
        if not owner_access.password_configured():
            raise HTTPException(409, 'Owner password has not been set up yet')
        if not owner_access.verify_password(body.password):
            failed_access_attempt(key)
            raise HTTPException(401, 'Incorrect owner password')
        clear_access_attempts(key)
        device = trust_browser(response, body.name, 'web-pwa-password')
        emit('owner.password.login', device_id=device['id'])
        return {'ok': True, 'device_id': device['id']}

    @router.post('/api/access/recovery/regenerate')
    def recovery_regenerate(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        codes = owner_access.regenerate_recovery_codes()
        emit('owner.recovery.regenerated', device_id=device_id, count=len(codes))
        return {'codes': codes, 'message': 'Save these codes now. Each code works only once.'}

    @router.post('/api/access/recovery/login')
    def recovery_login(body: OwnerRecoveryBody, request: Request, response: Response):
        require_https(request)
        key = allow_access_attempt(request, 'recovery')
        if not owner_access.consume_recovery_code(body.code):
            failed_access_attempt(key)
            raise HTTPException(401, 'Invalid or already used recovery code')
        clear_access_attempts(key)
        device = trust_browser(response, body.name, 'web-pwa-recovery')
        emit('owner.recovery.used', device_id=device['id'])
        return {'ok': True, 'device_id': device['id']}

    @router.post('/api/access/passkey/register/options')
    def passkey_register_options(
        request: Request,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        require_https(request)
        rp_id, origin = request_identity(request)
        exclude = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item['credential_id']))
            for item in owner_access.passkeys()
        ]
        identity = owner_access.identity()
        webauthn_owner_id = (identity or {}).get('owner_id', 'personal-ai-owner')
        owner_display_name = (identity or {}).get('display_name', 'Vishnu Owner')
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name='Vishnu',
            user_name=webauthn_owner_id,
            user_id=webauthn_owner_id.encode('utf-8'),
            user_display_name=owner_display_name,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                require_resident_key=False,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=exclude,
        )
        challenge_id = owner_access.create_challenge(
            'registration', options.challenge, rp_id, origin, device_id=device_id,
        )
        return {'challenge_id': challenge_id, 'public_key': json.loads(options_to_json(options))}

    @router.post('/api/access/passkey/register/complete')
    def passkey_register_complete(
        body: PasskeyCompleteBody,
        request: Request,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        require_https(request)
        challenge = owner_access.consume_challenge(body.challenge_id, 'registration', device_id=device_id)
        if not challenge:
            raise HTTPException(409, 'Face ID setup expired. Start again.')
        rp_id, origin = request_identity(request)
        if rp_id != challenge['rp_id'] or origin != challenge['origin']:
            raise HTTPException(400, 'Passkey origin changed during setup')
        try:
            verified = verify_registration_response(
                credential=body.credential,
                expected_challenge=bytes(challenge['challenge']),
                expected_rp_id=rp_id,
                expected_origin=origin,
                require_user_verification=True,
            )
        except Exception:
            raise HTTPException(401, 'Face ID passkey could not be verified')
        transports = body.credential.get('response', {}).get('transports', [])
        owner_access.save_passkey(
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            body.name,
            json.dumps(transports),
        )
        emit('owner.passkey.registered', device_id=device_id)
        return {'ok': True, 'name': body.name}

    @router.post('/api/access/passkey/login/options')
    def passkey_login_options(request: Request):
        require_https(request)
        rp_id, origin = request_identity(request)
        passkeys = owner_access.passkeys()
        if not passkeys:
            raise HTTPException(409, 'Face ID has not been set up yet')
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item['credential_id']))
                for item in passkeys
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        challenge_id = owner_access.create_challenge('authentication', options.challenge, rp_id, origin)
        return {'challenge_id': challenge_id, 'public_key': json.loads(options_to_json(options))}

    @router.post('/api/access/passkey/login/complete')
    def passkey_login_complete(body: PasskeyCompleteBody, request: Request, response: Response):
        require_https(request)
        key = allow_access_attempt(request, 'passkey')
        challenge = owner_access.consume_challenge(body.challenge_id, 'authentication')
        if not challenge:
            failed_access_attempt(key)
            raise HTTPException(409, 'Face ID request expired. Try again.')
        rp_id, origin = request_identity(request)
        if rp_id != challenge['rp_id'] or origin != challenge['origin']:
            failed_access_attempt(key)
            raise HTTPException(400, 'Passkey origin changed during login')
        try:
            credential_id = base64url_to_bytes(str(body.credential.get('id') or ''))
            stored = owner_access.passkey(credential_id)
            if not stored:
                raise ValueError('unknown credential')
            verified = verify_authentication_response(
                credential=body.credential,
                expected_challenge=bytes(challenge['challenge']),
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=bytes(stored['public_key']),
                credential_current_sign_count=int(stored['sign_count']),
                require_user_verification=True,
            )
        except Exception:
            failed_access_attempt(key)
            raise HTTPException(401, 'Face ID passkey could not be verified')
        clear_access_attempts(key)
        owner_access.use_passkey(credential_id, verified.new_sign_count)
        device = trust_browser(response, body.name, 'web-pwa-passkey')
        emit('owner.passkey.login', device_id=device['id'])
        return {'ok': True, 'device_id': device['id']}

    @router.post('/api/enroll')
    def enroll(body: OwnerEnrollBody, request: Request, response: Response):
        require_https(request)
        key = allow_access_attempt(request, 'enrollment')
        expected = getattr(settings, 'iphone_owner_enrollment_code', '').strip()
        if len(expected) < 12:
            raise HTTPException(503, 'iPhone owner enrollment is not configured')
        if not hmac.compare_digest(body.code.strip(), expected):
            failed_access_attempt(key)
            raise HTTPException(401, 'Invalid owner enrollment code')
        clear_access_attempts(key)
        device = trust_browser(response, body.name, 'ios-pwa')
        emit('iphone.enrolled', device_id=device['id'], platform='ios-pwa')
        return {'ok': True, 'device_id': device['id']}

    @router.post('/api/logout')
    def logout(response: Response):
        response.delete_cookie('pa_device', path='/iphone')
        response.delete_cookie('pa_token', path='/iphone')
        return {'ok': True}

    @router.post('/api/voice/turn')
    async def voice_turn(
        body: VoiceTurnBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        transcript = body.transcript.strip()
        conversation = resolve_conversation(device_id, body.conversation_id)
        conversation_history = model_history(conversation)
        append_conversation(conversation, device_id, 'user_message', transcript)
        if conversation and conversation['title'] in {'New conversation', 'Current context', 'Primary Vishnu Context'}:
            continuity.rename_thread(conversation['id'], transcript[:72])
            conversation = continuity.thread(conversation['id'])
        cancel_event = state.begin_turn(device_id)
        emit('state', state='understanding', device_id=device_id, source='iphone-pwa')
        emit('voice.transcript', text=transcript, device_id=device_id, source='iphone-pwa')
        try:
            reply = await asyncio.to_thread(
                executor.chat,
                transcript,
                cancel_event=cancel_event,
                device_id=device_id,
                conversation_id=conversation['id'] if conversation else None,
                conversation_history=conversation_history,
            )
            if cancel_event.is_set():
                emit('voice.turn.cancelled', device_id=device_id, source='iphone-pwa')
                emit('state', state='listening', device_id=device_id, source='iphone-pwa')
                raise HTTPException(409, 'turn_cancelled')
            emit('voice.reply', text=reply, device_id=device_id, source='iphone-pwa')
            append_conversation(conversation, device_id, 'assistant_message', reply)
            emit('state', state='speaking', device_id=device_id, source='iphone-pwa')
            return {
                'reply': reply,
                'device_id': device_id,
                'conversation_id': conversation['id'] if conversation else None,
                'conversation_title': conversation['title'] if conversation else None,
            }
        except ExecutionCancelled:
            emit('voice.turn.cancelled', device_id=device_id, source='iphone-pwa')
            emit('state', state='listening', device_id=device_id, source='iphone-pwa')
            raise HTTPException(409, 'turn_cancelled')
        except ConfirmationRequired as exc:
            with pending_approvals_lock:
                pending_approvals[exc.approval_id] = {
                    'device_id': device_id,
                    'tool': exc.tool_name,
                    'conversation_id': conversation['id'] if conversation else None,
                }
            emit(
                'state',
                state='approval',
                approval_id=exc.approval_id,
                tool=exc.tool_name,
                device_id=device_id,
                source='iphone-pwa',
            )
            return JSONResponse(status_code=202, content={
                'status': 'approval_required',
                'reply': f'This action needs your approval before I can use {exc.tool_name}.',
                'approval': {
                    'id': exc.approval_id,
                    'tool': exc.tool_name,
                    'description': exc.description or f'Use {exc.tool_name}',
                    'expires_at': exc.expires_at,
                },
                'device_id': device_id,
                'conversation_id': conversation['id'] if conversation else None,
            })
        except ModelError as exc:
            emit('voice.error', error=exc.code, device_id=device_id, source='iphone-pwa')
            emit('state', state='error', error=exc.code, device_id=device_id, source='iphone-pwa')
            raise HTTPException(exc.status_code, {'code': exc.code, 'message': exc.user_message})
        except HTTPException:
            raise
        except Exception:
            emit('voice.error', error='tool_error', device_id=device_id, source='iphone-pwa')
            emit('state', state='error', error='tool_error', device_id=device_id, source='iphone-pwa')
            raise HTTPException(502, {
                'code': 'tool_error',
                'message': 'That tool is unavailable on this Vishnu surface. No action was completed.',
            })
        finally:
            state.finish(device_id, cancel_event)

    def claim_pending_approval(approval_id: str, device_id: str):
        # The in-memory map is presentation/correlation state only. Canonical
        # approval existence and binding live in the durable Stage-2 authority,
        # so a router reload or lost response must not make a valid ticket vanish.
        with pending_approvals_lock:
            pending = pending_approvals.get(approval_id)
        canonical = None
        lookup = getattr(executor, 'approval_context', None)
        if callable(lookup):
            try:
                canonical = lookup(approval_id)
            except Exception:
                canonical = None
        if canonical is not None:
            if canonical.get('device_id') not in (None, device_id):
                raise HTTPException(404, {
                    'code': 'approval_not_found',
                    'message': 'This approval is missing, expired, or belongs to another device.',
                })
            if pending is None:
                pending = {
                    'device_id': device_id,
                    'tool': canonical.get('tool'),
                    'conversation_id': canonical.get('conversation_id'),
                }
        if not pending or pending['device_id'] != device_id:
            raise HTTPException(404, {
                'code': 'approval_not_found',
                'message': 'This approval is missing, expired, or belongs to another device.',
            })
        return pending

    @router.post('/api/approval/{approval_id}/approve')
    async def approval_approve(
        approval_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        pending = claim_pending_approval(approval_id, device_id)
        emit('state', state='acting', device_id=device_id, source='iphone-pwa')
        try:
            reply = await asyncio.to_thread(executor.approve, approval_id)
        except PermissionError:
            raise HTTPException(409, {
                'code': 'approval_expired',
                'message': 'This approval has expired or was already used.',
            })
        except ModelError as exc:
            raise HTTPException(exc.status_code, {'code': exc.code, 'message': exc.user_message})
        except Exception:
            emit('voice.error', error='tool_error', device_id=device_id, source='iphone-pwa')
            raise HTTPException(502, {
                'code': 'tool_error',
                'message': 'The approved action could not be completed safely.',
            })
        finally:
            with pending_approvals_lock:
                pending_approvals.pop(approval_id, None)
        emit('voice.reply', text=reply, device_id=device_id, source='iphone-pwa')
        conversation_id = pending.get('conversation_id')
        if conversation_id and continuity is not None:
            append_conversation(continuity.thread(conversation_id), device_id, 'assistant_message', reply)
        emit('state', state='speaking', device_id=device_id, source='iphone-pwa')
        return {'status': 'approved', 'reply': reply, 'device_id': device_id}

    @router.post('/api/approval/{approval_id}/reject')
    def approval_reject(
        approval_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        pending = claim_pending_approval(approval_id, device_id)
        try:
            reply = executor.reject(approval_id)
        finally:
            with pending_approvals_lock:
                pending_approvals.pop(approval_id, None)
        emit('state', state='listening', device_id=device_id, source='iphone-pwa')
        conversation_id = pending.get('conversation_id')
        if conversation_id and continuity is not None:
            continuity.append(
                conversation_id,
                device_id=device_id,
                kind='approval_rejected',
                payload={'text': reply, 'approval_id': approval_id},
            )
        return {'status': 'rejected', 'reply': reply, 'device_id': device_id}

    @router.get('/api/conversations')
    def conversation_list(
        q: str = '',
        limit: int = 50,
        include_closed: bool = False,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        active = continuity.active_for_device(device_id)
        return {
            'active_conversation_id': active['id'] if active else None,
            'conversations': continuity.list_threads(
                q, limit=max(1, min(limit, 100)), include_closed=include_closed,
            ),
        }

    @router.post('/api/conversations')
    def conversation_create(
        body: ConversationCreateBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        thread_id = continuity.create_thread(body.title.strip() or 'New conversation', device_id=device_id)
        return {'conversation': continuity.thread(thread_id), 'events': []}

    @router.get('/api/conversations/{conversation_id}')
    def conversation_get(
        conversation_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        thread = resolve_conversation(device_id, conversation_id)
        return {
            'conversation': thread,
            'events': continuity.events_for_thread(thread['id'], limit=500),
        }

    @router.post('/api/conversations/{conversation_id}/activate')
    def conversation_activate(
        conversation_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        thread = resolve_conversation(device_id, conversation_id)
        return {
            'conversation': thread,
            'events': continuity.events_for_thread(thread['id'], limit=500),
        }

    @router.patch('/api/conversations/{conversation_id}')
    def conversation_rename(
        conversation_id: str,
        body: ConversationRenameBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        resolve_conversation(device_id, conversation_id)
        return {'conversation': continuity.rename_thread(conversation_id, body.title)}

    @router.get('/api/conversations/{conversation_id}/export')
    def conversation_export(
        conversation_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        thread = continuity.thread(conversation_id)
        if not thread or thread.get('closed_at'):
            raise HTTPException(404, 'Conversation not found')
        return continuity.export_thread(thread['id'])

    @router.delete('/api/conversations/{conversation_id}')
    def conversation_delete(
        conversation_id: str,
        confirm: bool = Query(default=False),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if not confirm:
            raise HTTPException(422, 'Explicit conversation deletion confirmation is required')
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        thread = continuity.thread(conversation_id)
        if not thread or thread.get('closed_at'):
            raise HTTPException(404, 'Conversation not found')
        # Destruction is owner-authorized, explicitly confirmed and
        # requires recent verification when production sessions exist.
        require_fresh_owner_verification(device_id)
        if not continuity.delete_thread(thread['id']):
            raise HTTPException(404, 'Conversation not found')
        return {'deleted': True, 'conversation_id': thread['id']}

    @router.post('/api/voice/barge')
    def voice_barge(
        body: BargeBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        cancelled = state.cancel(device_id)
        if body.speaking or cancelled:
            emit('voice.barge_in', device_id=device_id, source='iphone-pwa')
            emit('voice.turn.cancelled', device_id=device_id, source='iphone-pwa')
            emit('state', state='listening', device_id=device_id, source='iphone-pwa')
        return {'ok': True, 'cancelled_server_turn': cancelled}

    @router.post('/api/voice/client-event')
    def voice_client_event(
        body: VoiceClientEventBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        emit(f'voice.client.{body.event}', device_id=device_id, source='iphone-pwa', detail=body.detail)
        if body.event == 'tts_error':
            emit('voice.error', error='tts_error', detail=body.detail, device_id=device_id, source='iphone-pwa')
        return {'ok': True}

    @router.post('/api/qualification/start')
    def qualification_start(
        body: QualificationStartBody,
        request: Request,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if recorder is None:
            raise HTTPException(503, 'Voice qualification recorder unavailable')
        environment = {
            **body.environment,
            'device_id': device_id,
            'platform': 'ios-pwa',
            'user_agent': request.headers.get('user-agent', ''),
            'transport': 'https-pwa',
        }

        def resume_active_session():
            active = recorder.active_session()
            if not active:
                return None
            if active.get('environment', {}).get('device_id') != device_id:
                raise HTTPException(409, {
                    'code': 'qualification_session_active',
                    'message': 'Another trusted device already has an active qualification session',
                })
            emit('state', state='listening', device_id=device_id, source='iphone-pwa')
            return {
                'session_id': active['id'],
                'evidence_class': active['evidence_class'],
                'status': 'already_active',
                'message': 'Existing session resumed',
            }

        resumed = resume_active_session()
        if resumed:
            return resumed
        try:
            session_id = recorder.start_session(evidence_class='real_device', environment=environment, notes=body.notes)
        except RuntimeError as exc:
            if str(exc) != 'voice qualification session already active':
                raise
            resumed = resume_active_session()
            if resumed:
                return resumed
            raise HTTPException(409, {
                'code': 'qualification_session_active',
                'message': 'A qualification session is already active',
            })
        emit('state', state='listening', device_id=device_id, source='iphone-pwa')
        return {'session_id': session_id, 'evidence_class': 'real_device', 'status': 'started'}

    @router.post('/api/qualification/stop')
    def qualification_stop(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if recorder is None:
            raise HTTPException(503, 'Voice qualification recorder unavailable')
        active = recorder.active_session()
        if active and active.get('environment', {}).get('device_id') != device_id:
            raise HTTPException(409, {
                'code': 'qualification_session_owned_by_other_device',
                'message': 'This evidence session belongs to another trusted browser and was left running.',
            })
        try:
            return recorder.stop_session()
        except RuntimeError as exc:
            if str(exc) != 'no active voice qualification session':
                raise
            return {'ok': True, 'status': 'already_stopped', 'message': 'Session already stopped'}

    @router.post('/api/qualification/takeover')
    def qualification_takeover(
        body: QualificationTakeoverBody,
        request: Request,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = auth_device(pa_device, pa_token)
        if recorder is None:
            raise HTTPException(503, 'Voice qualification recorder unavailable')
        close_sessions = getattr(recorder, 'close_active_sessions', None)
        if not callable(close_sessions):
            raise HTTPException(503, 'Qualification session recovery is unavailable')
        closed_session_ids = close_sessions(
            reason=f'Owner-confirmed takeover by trusted device {device_id}'
        )
        environment = {
            **body.environment,
            'device_id': device_id,
            'platform': 'ios-pwa',
            'user_agent': request.headers.get('user-agent', ''),
            'transport': 'https-pwa',
        }
        session_id = recorder.start_session(
            evidence_class='real_device',
            environment=environment,
            notes=body.notes,
        )
        emit(
            'qualification.session_takeover',
            device_id=device_id,
            closed_session_ids=closed_session_ids,
            session_id=session_id,
            source='iphone-pwa',
        )
        emit('state', state='listening', device_id=device_id, source='iphone-pwa')
        return {
            'status': 'started',
            'session_id': session_id,
            'evidence_class': 'real_device',
            'closed_session_ids': closed_session_ids,
        }

    @router.get('/api/qualification/sessions')
    def qualification_sessions(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        auth_device(pa_device, pa_token)
        if recorder is None:
            raise HTTPException(503, 'Voice qualification recorder unavailable')
        return {'sessions': recorder.sessions()}

    if not include_legacy_runtime_routes:
        # Stage 3/Stage 2 canonical routers own these production paths. Keep the
        # historical handlers available only for isolated compatibility/P3 tests,
        # never as order-dependent competing cloud authorities.
        canonical_runtime_routes = {
            ('POST', '/iphone/api/voice/turn'),
            ('POST', '/iphone/api/approval/{approval_id}/approve'),
            ('POST', '/iphone/api/approval/{approval_id}/reject'),
            ('GET', '/iphone/api/conversations'),
            ('GET', '/iphone/api/conversations/{conversation_id}'),
            ('POST', '/iphone/api/voice/barge'),
            ('POST', '/iphone/api/voice/client-event'),
        }
        router.routes[:] = [
            route for route in router.routes
            if not any(
                (method, getattr(route, 'path', '')) in canonical_runtime_routes
                for method in (getattr(route, 'methods', None) or ())
            )
        ]

    return router
