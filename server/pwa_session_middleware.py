from __future__ import annotations

from http.cookies import SimpleCookie

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from security.request_context import (
    TrustedRequestContext,
    reset_trusted_request,
    set_trusted_request,
)


PUBLIC_PATHS = {
    '/iphone',
    '/iphone/',
    '/iphone/campaign-demo',
    '/iphone/native/authorize',
    '/iphone/manifest.webmanifest',
    '/iphone/sw.js',
    '/iphone/reference-home.css',
    '/iphone/reference-home.js',
    '/iphone/global-search.js',
    '/iphone/global-search.css',
    # Static UI code and illustrative fixture content are public, non-secret
    # resources. The demo itself only activates behind the explicit local
    # `?campaignDemo=1` flag and performs no owner-data writes.
    '/iphone/campaign-demo.js',
    '/iphone/campaign-demo.css',
    '/iphone/campaign-demo-data.js',
    '/iphone/genesis.css',
    '/iphone/first-run.js',
    '/iphone/first-run-actions.js',
    '/iphone/api/access/options',
    '/iphone/api/first-run/create',
    '/iphone/api/first-run/complete',
    '/iphone/api/first-run/model',
    '/iphone/api/first-run/data-policy',
    '/iphone/api/first-run/recovery-codes',
    '/iphone/api/first-run/recovery-saved',
    '/iphone/api/first-run/resume',
    '/iphone/api/first-run/resume',
    '/iphone/api/first-run/native/create',
    '/iphone/api/first-run/native/complete',
    '/iphone/api/access/native/recovery',
    '/iphone/api/access/google/login',
    '/iphone/api/access/password/login',
    '/iphone/api/access/recovery/login',
    '/iphone/api/access/passkey/login/options',
    '/iphone/api/access/passkey/login/complete',
    '/iphone/api/access/join/status',
    '/iphone/api/enroll',
    '/iphone/api/first-run/create',
    '/iphone/api/native/sessions/exchange',
    # External OAuth providers cannot carry Vishnu browser/native sessions back
    # to this callback. Forge validates its own one-time durable state + PKCE +
    # security epoch before exchanging the code, so the middleware must not
    # pre-empt that callback with a session challenge.
    '/iphone/capability-oauth/callback',
}

LOGIN_PATHS = {
    '/iphone/api/first-run/create',
    '/iphone/api/first-run/resume',
    '/iphone/api/access/google/login',
    '/iphone/api/access/password/login',
    '/iphone/api/access/recovery/login',
    '/iphone/api/access/passkey/login/complete',
    '/iphone/api/access/join/status',
    '/iphone/api/enroll',
}


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith('/iphone/assets/genesis/')


def _cookie_from_response(response, name: str) -> str | None:
    for raw_name, raw_value in response.raw_headers:
        if raw_name.lower() != b'set-cookie':
            continue
        jar = SimpleCookie()
        try:
            jar.load(raw_value.decode('latin1'))
        except Exception:
            continue
        morsel = jar.get(name)
        if morsel and morsel.value:
            return morsel.value
    return None


class PwaSessionMiddleware(BaseHTTPMiddleware):
    """Require a revocable server-side session in addition to the device bearer."""

    def __init__(self, app, *, sessions, device_registry, cookie_max_age: int,
                 first_run_setup=None, cookie_secure: bool = True):
        super().__init__(app)
        self.sessions = sessions
        self.device_registry = device_registry
        self.cookie_max_age = max(300, int(cookie_max_age))
        self.first_run_setup = first_run_setup
        self.cookie_secure = bool(cookie_secure)

    def _set_session_cookie(self, response, token: str):
        response.set_cookie(
            'pa_session',
            token,
            httponly=True,
            secure=self.cookie_secure,
            samesite='strict',
            path='/iphone',
            max_age=self.cookie_max_age,
        )

    @staticmethod
    def _clear_session_cookie(response):
        response.delete_cookie('pa_session', path='/iphone')

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith('/iphone'):
            return await call_next(request)

        context_token = None
        session = None
        session_token = request.cookies.get('pa_session')
        device_id = request.cookies.get('pa_device')
        authorization = request.headers.get('authorization', '')
        bearer = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
        native_route = (
            path.startswith('/iphone/api/apps-tools')
            or path.startswith('/iphone/api/native/sessions/')
            or path.startswith('/iphone/api/owner/forge/v3')
        )

        if not _is_public(path):
            session = None
            if bearer and native_route:
                session = self.sessions.authenticate_native(bearer)
            if session is None:
                session = self.sessions.authenticate(session_token, device_id)
            if session is None:
                response = JSONResponse(
                    status_code=401,
                    content={
                        'detail': {
                            'code': 'session_expired',
                            'message': 'This browser session is missing, expired, or revoked. Sign in again.',
                        }
                    },
                )
                self._clear_session_cookie(response)
                return response
            if not self.device_registry.is_active(session.device_id):
                self.sessions.revoke(session.id)
                response = JSONResponse(
                    status_code=401,
                    content={
                        'detail': {
                            'code': 'device_revoked',
                            'message': 'This trusted device has been revoked.',
                        }
                    },
                )
                self._clear_session_cookie(response)
                return response
            context_token = set_trusted_request(
                TrustedRequestContext(
                    device_id=session.device_id,
                    session_id=session.id,
                    reauthenticated_at=session.reauthenticated_at,
                    scopes=frozenset(session.scopes) if session.kind == 'native' else None,
                    auth_type=session.kind,
                )
            )

        if self.first_run_setup is not None and not self.first_run_setup.ready:
            allowed_during_setup = {
                '/iphone/api/access/options',
                '/iphone/api/access/reauth/password',
                '/iphone/api/passkey/register/options',
                '/iphone/api/passkey/register/complete',
                '/iphone/api/access/passkey/register/options',
                '/iphone/api/access/passkey/register/complete',
                '/iphone/api/access/security',
                '/iphone/api/first-run/complete',
                '/iphone/api/first-run/model',
                '/iphone/api/first-run/recovery-codes',
                '/iphone/api/first-run/recovery-saved',
                '/iphone/api/first-run/resume',
                # First-run policy writes are separately authorized by the
                # setup claim and first-device credential in iphone_pwa.py.
                '/iphone/api/first-run/data-policy',
                # Photos are not public during setup: these paths still need
                # an active session, trusted device, owner identity, and (for
                # updates) the canonical first-device setup claim.
                '/iphone/api/first-run/avatar',
                '/iphone/api/access/profile/avatar',
                '/iphone/api/access/profile/avatar/image',
            }
            if path.startswith('/iphone/api/') and path not in allowed_during_setup and path not in PUBLIC_PATHS:
                response = JSONResponse(
                    status_code=423,
                    content={
                        'detail': {
                            'code': 'first_run_incomplete',
                            'message': 'Finish Vishnu setup on this device before using its data.',
                        }
                    },
                )
                if context_token is not None:
                    reset_trusted_request(context_token)
                return response

        try:
            response = await call_next(request)
        finally:
            if context_token is not None:
                reset_trusted_request(context_token)

        if path in LOGIN_PATHS and response.status_code < 400:
            new_device_id = _cookie_from_response(response, 'pa_device')
            if new_device_id and self.device_registry.is_active(new_device_id):
                new_token, _ = self.sessions.issue(new_device_id, reauthenticated=True)
                self._set_session_cookie(response, new_token)

        if path == '/iphone/api/logout':
            if session is not None:
                self.sessions.revoke(session.id)
            elif session_token:
                self.sessions.revoke_token(session_token)
            self._clear_session_cookie(response)

        return response
