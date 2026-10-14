from __future__ import annotations

import base64
import html
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, SecretStr
from webauthn import generate_registration_options, options_to_json, verify_registration_response
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


_ANDROID_PASSKEY_RELATION = 'delegate_permission/common.get_login_creds'
_ANDROID_PACKAGE = 'ai.personal.companion'
_IOS_BUNDLE_SUFFIX = '.ai.personal.companion'


class NativePasskeyOptionsBody(BaseModel):
    device_id: str = Field(min_length=16, max_length=80)
    device_token: SecretStr = Field(min_length=32, max_length=256)
    platform: Literal['android', 'ios']


class NativePasskeyCompleteBody(NativePasskeyOptionsBody):
    challenge_id: str = Field(min_length=10, max_length=80)
    credential: dict
    name: str = Field(default='Owner mobile passkey', min_length=1, max_length=120)


def _android_passkey_origins(asset_links) -> set[str]:
    """Return native WebAuthn origins derived only from configured DAL fingerprints."""
    origins: set[str] = set()
    if not isinstance(asset_links, list):
        return origins
    for statement in asset_links:
        if not isinstance(statement, dict):
            continue
        relation = statement.get('relation', [])
        if isinstance(relation, str):
            relation = [relation]
        if _ANDROID_PASSKEY_RELATION not in relation:
            continue
        target = statement.get('target', {})
        if not isinstance(target, dict) or target.get('namespace') != 'android_app':
            continue
        if target.get('package_name') != _ANDROID_PACKAGE:
            continue
        fingerprints = target.get('sha256_cert_fingerprints', [])
        if not isinstance(fingerprints, list):
            continue
        for fingerprint in fingerprints:
            try:
                digest = bytes.fromhex(str(fingerprint).replace(':', '').strip())
            except ValueError:
                continue
            if len(digest) != 32:
                continue
            encoded = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
            origins.add(f'android:apk-key-hash:{encoded}')
    return origins


def _ios_passkey_enabled(association) -> bool:
    """Require an explicit AASA webcredentials association for this app family."""
    if not isinstance(association, dict):
        return False
    service = association.get('webcredentials', {})
    if not isinstance(service, dict):
        return False
    apps = service.get('apps', [])
    if not isinstance(apps, list):
        return False
    return any(str(app).endswith(_IOS_BUNDLE_SUFFIX) for app in apps)


def _credential_origin(credential: dict) -> str:
    encoded = credential.get('response', {}).get('clientDataJSON') if isinstance(credential, dict) else None
    if not encoded:
        raise ValueError('Passkey response is missing client data')
    try:
        client_data = json.loads(base64url_to_bytes(str(encoded)).decode('utf-8'))
    except Exception as exc:
        raise ValueError('Passkey client data is invalid') from exc
    origin = str(client_data.get('origin') or '').strip()
    if not origin:
        raise ValueError('Passkey client data is missing its origin')
    return origin


def native_capability_auth_router(runtime):
    router = APIRouter(tags=["native-capability-auth"])
    sessions = runtime["pwa_sessions"]
    owner_access = runtime['owner_access']
    registry = runtime['device_registry']
    events = runtime.get('events')

    def emit(name: str, **payload):
        if events is not None:
            events.emit(name, **payload)

    def request_identity(request: Request) -> tuple[str, str]:
        forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
        host = forwarded_host or request.headers.get('host', '').strip()
        forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip().lower()
        proto = forwarded_proto or request.url.scheme.lower()
        if proto != 'https' or not host:
            raise HTTPException(400, 'Native passkey enrollment requires HTTPS')
        if host.startswith('['):
            rp_id = host.split(']', 1)[0].strip('[]')
        else:
            rp_id = host.rsplit(':', 1)[0] if host.count(':') == 1 else host
        if not rp_id:
            raise HTTPException(400, 'Native passkey relying-party domain is invalid')
        return rp_id, f'https://{rp_id}'

    def require_native_owner_device(body: NativePasskeyOptionsBody) -> str:
        token = body.device_token.get_secret_value()
        if not registry.authenticate(body.device_id, token):
            raise HTTPException(401, 'This trusted device credential is invalid or revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(body.device_id, 'device:admin'):
            raise HTTPException(403, 'This device is not permitted to manage owner security')
        record = next((item for item in registry.list() if item.get('id') == body.device_id), None)
        if record is None or str(record.get('platform') or '') != body.platform:
            raise HTTPException(403, 'The trusted device platform does not match this passkey request')
        return body.device_id

    def require_platform_association(platform: str) -> set[str] | None:
        if platform == 'android':
            origins = _android_passkey_origins(runtime.get('android_asset_links', []))
            if not origins:
                raise HTTPException(
                    409,
                    'Android passkey registration is disabled until this runtime publishes a Digital Asset Link for the signed Vishnu app.',
                )
            return origins
        if not _ios_passkey_enabled(runtime.get('apple_app_site_association', {})):
            raise HTTPException(
                409,
                'iOS passkey registration is disabled until this runtime and signed app share an Apple webcredentials association.',
            )
        return None

    @router.get("/iphone/native/authorize", response_class=HTMLResponse)
    def authorize_page(client_id: str = Query(..., min_length=1, max_length=160),
                       redirect_uri: str = Query(..., min_length=1, max_length=1000),
                       code_challenge: str = Query(..., min_length=43, max_length=128),
                       state: str = Query(..., min_length=16, max_length=200)):
        if client_id not in sessions.native_client_redirects or redirect_uri not in sessions.native_client_redirects[client_id]:
            raise HTTPException(400, "Native application redirect is not registered")
        # The query values are escaped into attributes, and capability permissions
        # are chosen with an explicit owner gesture before any code is issued.
        cid, redirect, challenge, nonce = map(html.escape, (client_id, redirect_uri, code_challenge, state))
        page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize Vishnu</title><body style="font:16px system-ui;max-width:36rem;margin:12vh auto;padding:1.5rem;background:#09111b;color:#edf2f7">
<main><h1>Connect this Vishnu app?</h1><p>Confirm the capabilities this app may manage. Access remains limited by this trusted device's permissions.</p>
<form id="grant" data-client="{cid}" data-redirect="{redirect}" data-challenge="{challenge}" data-state="{nonce}">
<label><input type="checkbox" name="scope" value="device:read" checked> View and test approved capabilities</label><br>
<label><input type="checkbox" name="scope" value="device:admin"> Manage connections, credentials, approvals, and permissions</label><br>
<button type="submit" style="margin-top:1rem;padding:.8rem 1.2rem">Authorize this app</button>
</form><p id="status" role="status" aria-live="polite">This grant uses a short-lived one-time code. Your session token is never placed in the redirect URL.</p>
<p><a href="/iphone/" style="color:#85c8ff">Open Vishnu sign-in</a></p></main>
<script>
const form=document.getElementById('grant'),status=document.getElementById('status');
form.addEventListener('submit',async event=>{{event.preventDefault();const scopes=[...form.querySelectorAll('input[name=scope]:checked')].map(x=>x.value);if(!scopes.length){{status.textContent='Select at least one permission.';return}}status.textContent='Checking owner session…';try{{const response=await fetch('/iphone/api/native/sessions/authorize',{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{client_id:form.dataset.client,redirect_uri:form.dataset.redirect,code_challenge:form.dataset.challenge,scopes}})}});if(!response.ok){{if(response.status===401)throw new Error('Sign in to Vishnu in this browser, then return to this authorization page.')}}const result=await response.json();const target=new URL(result.redirect_uri);target.searchParams.set('code',result.code);target.searchParams.set('state',form.dataset.state);location.assign(target.toString())}}catch(error){{status.textContent=error.message||'Authorization could not be completed.'}}}});
</script></body></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Pragma": "no-cache",
                                           "Referrer-Policy": "no-referrer",
                                           "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

    @router.get("/.well-known/assetlinks.json")
    def android_association():
        links = runtime.get("android_asset_links", [])
        return JSONResponse(links, headers={"Cache-Control": "public, max-age=300"})

    @router.get("/.well-known/apple-app-site-association")
    def ios_association():
        association = runtime.get("apple_app_site_association", {})
        return JSONResponse(association, headers={"Cache-Control": "public, max-age=300"})

    @router.post('/iphone/api/native/passkeys/register/options')
    def native_passkey_register_options(body: NativePasskeyOptionsBody, request: Request):
        device_id = require_native_owner_device(body)
        require_platform_association(body.platform)
        rp_id, _ = request_identity(request)
        identity = owner_access.identity()
        if identity is None:
            raise HTTPException(409, 'Vishnu owner identity is not initialized')
        exclude = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item['credential_id']))
            for item in owner_access.passkeys()
        ]
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name='Vishnu',
            user_name=identity['owner_id'],
            user_id=identity['owner_id'].encode('utf-8'),
            user_display_name=identity['display_name'],
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                require_resident_key=False,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=exclude,
        )
        challenge_id = owner_access.create_challenge(
            'native_registration', options.challenge, rp_id, f'native:{body.platform}',
            device_id=device_id,
        )
        emit('owner.passkey.native_requested', device_id=device_id, platform=body.platform)
        return {
            'challenge_id': challenge_id,
            'rp_id': rp_id,
            'user_id': base64.urlsafe_b64encode(identity['owner_id'].encode('utf-8')).decode('ascii').rstrip('='),
            'user_name': identity['display_name'],
            'public_key': json.loads(options_to_json(options)),
        }

    @router.post('/iphone/api/native/passkeys/register/complete')
    def native_passkey_register_complete(body: NativePasskeyCompleteBody, request: Request):
        device_id = require_native_owner_device(body)
        allowed_android_origins = require_platform_association(body.platform)
        rp_id, ios_origin = request_identity(request)
        challenge = owner_access.consume_challenge(
            body.challenge_id, 'native_registration', device_id=device_id,
        )
        if not challenge:
            raise HTTPException(409, 'Native passkey setup expired. Start again.')
        if challenge['rp_id'] != rp_id or challenge['origin'] != f'native:{body.platform}':
            raise HTTPException(400, 'Native passkey relying party changed during setup')
        try:
            client_origin = _credential_origin(body.credential)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if body.platform == 'android':
            if client_origin not in (allowed_android_origins or set()):
                raise HTTPException(401, 'Android passkey origin is not authorized by this runtime')
        elif client_origin != ios_origin:
            raise HTTPException(401, 'iOS passkey origin is not authorized by this runtime')
        try:
            verified = verify_registration_response(
                credential=body.credential,
                expected_challenge=bytes(challenge['challenge']),
                expected_rp_id=rp_id,
                expected_origin=client_origin,
                require_user_verification=True,
            )
        except Exception as exc:
            raise HTTPException(401, 'Native passkey could not be verified') from exc
        transports = body.credential.get('response', {}).get('transports', [])
        owner_access.save_passkey(
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            body.name,
            json.dumps(transports),
        )
        emit('owner.passkey.registered', device_id=device_id, platform=body.platform, native=True)
        return {'ok': True, 'name': body.name, 'platform': body.platform}

    return router
