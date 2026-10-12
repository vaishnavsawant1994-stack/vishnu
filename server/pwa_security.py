from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from security.request_context import current_trusted_request


class PasswordReauthBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class NativeAuthorizationBody(BaseModel):
    client_id: str = Field(min_length=1, max_length=160)
    redirect_uri: str = Field(min_length=1, max_length=1000)
    code_challenge: str = Field(min_length=43, max_length=128)
    scopes: list[str] = Field(min_length=1, max_length=2)


class NativeExchangeBody(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    code_verifier: str = Field(min_length=43, max_length=128)
    client_id: str = Field(min_length=1, max_length=160)
    redirect_uri: str = Field(min_length=1, max_length=1000)


def pwa_security_router(runtime):
    router = APIRouter(prefix='/iphone/api', tags=['iphone-pwa-security'])
    sessions = runtime['pwa_sessions']
    owner_access = runtime['owner_access']
    # Older isolated router consumers (for example, browser session tests) may
    # construct this router without a device registry. Native authorization is
    # fail-closed in that case while the existing browser session endpoints
    # remain usable.
    devices = runtime.get('device_registry')

    def context():
        current = current_trusted_request()
        if current is None:
            raise HTTPException(401, {
                'code': 'session_expired',
                'message': 'This browser session is missing, expired, or revoked.',
            })
        return current

    def audit(event, current, **payload):
        state = getattr(runtime.get('integrations'), 'state_store', None)
        if state is not None:
            state.audit(event, device_id=current.device_id, session_id=current.session_id,
                        payload=payload)

    @router.post('/access/reauth/password')
    def reauth_password(body: PasswordReauthBody):
        current = context()
        if not owner_access.password_configured():
            raise HTTPException(409, {
                'code': 'password_not_configured',
                'message': 'Owner password re-authentication is not configured.',
            })
        if not owner_access.verify_password(body.password):
            raise HTTPException(401, {
                'code': 'reauthentication_failed',
                'message': 'Owner verification failed.',
            })
        if not sessions.mark_reauthenticated(current.session_id):
            raise HTTPException(401, {
                'code': 'session_expired',
                'message': 'This browser session is no longer active.',
            })
        return {'ok': True, 'session_id': current.session_id}

    @router.post('/native/sessions/authorize')
    def authorize_native(body: NativeAuthorizationBody):
        current = context()
        if current.auth_type != 'browser':
            raise HTTPException(403, 'Only a signed-in owner browser can authorize a native session')
        if devices is None:
            raise HTTPException(503, 'Native authorization is unavailable')
        if not devices.is_active(current.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if set(body.scopes) - sessions.NATIVE_SCOPES:
            raise HTTPException(403, 'Requested native permissions are not supported')
        for scope in body.scopes:
            if not devices.authorize(current.device_id, scope):
                raise HTTPException(403, f'This device is not permitted to grant {scope}')
        try:
            code = sessions.create_native_authorization_code(
                browser_session_id=current.session_id, device_id=current.device_id,
                client_id=body.client_id, redirect_uri=body.redirect_uri,
                challenge=body.code_challenge, scopes=body.scopes,
            )
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('native_session.authorization_issued', current,
              client_id=body.client_id, scopes=sorted(set(body.scopes)))
        return {'code': code, 'expires_in': sessions.NATIVE_CODE_TTL_SECONDS,
                'redirect_uri': body.redirect_uri}

    @router.post('/native/sessions/exchange')
    def exchange_native(body: NativeExchangeBody):
        try:
            token, session = sessions.exchange_native_authorization_code(
                code=body.code, verifier=body.code_verifier,
                client_id=body.client_id, redirect_uri=body.redirect_uri,
            )
        except PermissionError as exc:
            raise HTTPException(400, {'code': 'native_authorization_failed',
                                      'message': 'Native authorization could not be completed.'}) from exc
        if not devices.is_active(session.device_id):
            sessions.revoke(session.id)
            raise HTTPException(401, 'The authorizing device is no longer active')
        audit('native_session.created', type('Context', (), {
            'device_id': session.device_id, 'session_id': session.id
        })(), client_id=body.client_id, scopes=list(session.scopes))
        return {'access_token': token, 'token_type': 'Bearer', 'expires_in': int(session.expires_at - session.created_at),
                'session_id': session.id, 'scopes': list(session.scopes)}

    @router.post('/native/sessions/reauth')
    def reauth_native(body: PasswordReauthBody):
        current = context()
        if current.auth_type != 'native':
            raise HTTPException(400, 'A native session is required')
        if not owner_access.password_configured() or not owner_access.verify_password(body.password):
            raise HTTPException(401, 'Owner verification failed')
        if not sessions.mark_reauthenticated(current.session_id):
            raise HTTPException(401, 'Native session is no longer active')
        audit('native_session.reauthenticated', current)
        return {'ok': True, 'session_id': current.session_id}

    @router.post('/native/sessions/logout')
    def logout_native():
        current = context()
        if current.auth_type != 'native':
            raise HTTPException(400, 'A native session is required')
        sessions.revoke(current.session_id)
        audit('native_session.revoked', current, reason='logout')
        return {'ok': True}

    @router.post('/native/sessions/rotate')
    def rotate_native():
        current = context()
        if current.auth_type != 'native':
            raise HTTPException(400, 'A native session is required')
        try:
            token, session = sessions.rotate_native(current.session_id)
        except PermissionError as exc:
            raise HTTPException(401, 'Native session is expired or revoked') from exc
        audit('native_session.rotated', current)
        return {'access_token': token, 'token_type': 'Bearer',
                'expires_in': int(session.expires_at - session.created_at),
                'session_id': session.id, 'scopes': list(session.scopes)}

    @router.get('/sessions')
    def list_sessions():
        current = context()
        rows = sessions.active_for_device(current.device_id)
        return {
            'current_session_id': current.session_id,
            'sessions': [
                {
                    'id': row.id,
                    'device_id': row.device_id,
                    'created_at': row.created_at,
                    'last_seen_at': row.last_seen_at,
                    'expires_at': row.expires_at,
                    'reauthenticated_at': row.reauthenticated_at,
                    'current': row.id == current.session_id,
                }
                for row in rows
            ],
        }

    @router.post('/sessions/{session_id}/revoke')
    def revoke_session(session_id: str):
        current = context()
        target = sessions.get(session_id)
        if target is None or target.device_id != current.device_id:
            raise HTTPException(404, {
                'code': 'session_not_found',
                'message': 'That browser session was not found for this trusted device.',
            })
        sessions.revoke(session_id)
        executor = runtime.get('executor')
        cancel_session_turns = getattr(executor, 'cancel_session_turns', None)
        cancelled_turns = int(cancel_session_turns(session_id, reason='session_revoked')) if callable(cancel_session_turns) else 0
        automations = runtime.get('automations')
        cancel_session_runs = getattr(automations, 'cancel_session_runs', None)
        cancelled_workflows = int(cancel_session_runs(session_id, reason='session_revoked')) if callable(cancel_session_runs) else 0
        return {'ok': True, 'revoked': session_id, 'current': session_id == current.session_id, 'cancelled_turns': cancelled_turns, 'cancelled_workflows': cancelled_workflows}

    @router.post('/sessions/revoke-others')
    def revoke_other_sessions():
        current = context()
        count = 0
        for row in sessions.active_for_device(current.device_id):
            if row.id != current.session_id and sessions.revoke(row.id):
                count += 1
                executor = runtime.get('executor')
                cancel_session_turns = getattr(executor, 'cancel_session_turns', None)
                if callable(cancel_session_turns):
                    cancel_session_turns(row.id, reason='session_revoked')
                automations = runtime.get('automations')
                cancel_session_runs = getattr(automations, 'cancel_session_runs', None)
                if callable(cancel_session_runs):
                    cancel_session_runs(row.id, reason='session_revoked')
        return {'ok': True, 'revoked': count, 'current_session_id': current.session_id}

    return router
