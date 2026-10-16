from __future__ import annotations

import html
import json
import os
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from data_plane.runtime import get_data_plane
from security.request_context import current_trusted_request
from sensorium import NativeDeviceLab
from server.data_plane_owner_api import _safe_provider


def _release_identity() -> tuple[str, str]:
    build_version = str(os.getenv('VISHNU_BUILD_VERSION', '')).strip()
    source = 'build configuration'
    if not build_version:
        try:
            build_version = version('personal-ai')
            source = 'installed package metadata'
        except PackageNotFoundError:
            try:
                project = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())
                build_version = str(project['project']['version'])
                source = 'repository project metadata'
            except (OSError, KeyError, tomllib.TOMLDecodeError):
                build_version = 'development build'
                source = 'fallback'
    return build_version, source


def _page(title: str, subtitle: str, body: str) -> HTMLResponse:
    return HTMLResponse(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Vishnu</title><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,sans-serif;background:#030405;color:#edf3f6}}
body{{margin:0;background:#030405;color:#edf3f6}}main{{max-width:880px;margin:0 auto;padding:32px 20px 64px}}
a{{color:#67b7ff}}.back{{display:inline-block;margin-bottom:24px}}h1{{font-size:28px;margin:0 0 8px}}p{{color:#9badb7;line-height:1.55}}
.card{{background:#0b1115;border:1px solid #2b4350;border-radius:14px;padding:18px;margin:16px 0}}.row{{display:flex;gap:16px;justify-content:space-between;border-top:1px solid #1c303b;padding:12px 0}}.row:first-child{{border-top:0}}.key{{color:#9badb7}}.value{{text-align:right;overflow-wrap:anywhere}}.ok{{color:#71e6a2}}.warn{{color:#ffd166}}code{{background:#101b21;padding:2px 6px;border-radius:6px}}@media(max-width:600px){{.row{{display:block}}.value{{text-align:left;margin-top:5px}}}}
</style></head><body><main><a class="back" href="/iphone/">← Back to Vishnu</a><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>{body}</main></body></html>''')


def _row(key: str, value: object, *, css: str = '') -> str:
    rendered = '—' if value in (None, '') else str(value)
    return f'<div class="row"><div class="key">{html.escape(key)}</div><div class="value {css}">{html.escape(rendered)}</div></div>'


def about_router(runtime):
    """Safe product identity plus owner-read detail pages for canonical UI gaps."""
    router = APIRouter(prefix='/iphone/api/about', tags=['about'])
    registry = runtime['device_registry']

    def require_owner(scope: str = 'device:read'):
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not registry.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if context.auth_type == 'native' and (context.scopes is None or scope not in context.scopes):
            raise HTTPException(403, f'This native session is not scoped for {scope}')
        if not registry.authorize(context.device_id, scope):
            raise HTTPException(403, f'This device is not permitted to use {scope}')
        return context

    def identity_payload() -> dict:
        build_version, version_source = _release_identity()
        return {
            'product': 'Vishnu',
            'version': build_version,
            'version_source': version_source,
            'build_sha': str(os.getenv('VISHNU_BUILD_SHA') or os.getenv('VISHNU_RELEASE_REVISION') or '').strip() or None,
            'release_channel': str(os.getenv('VISHNU_RELEASE_CHANNEL', 'unknown')).strip() or 'unknown',
            'license': 'Proprietary — All Rights Reserved',
            'updates': {
                'available': False,
                'status': 'managed_by_installation',
                'message': 'This installation does not expose an in-app signed updater. Installation updates are managed by the platform or installation owner.',
            },
        }

    def native_lab() -> NativeDeviceLab:
        lab = runtime.get('sensorium_native_lab')
        if lab is not None:
            return lab
        runtime_settings = runtime.get('settings')
        data_dir = getattr(runtime_settings, 'data_dir', None)
        if data_dir is None:
            from core.config import settings as application_settings
            data_dir = application_settings.data_dir
        lab = NativeDeviceLab(Path(data_dir) / 'sensorium-native.sqlite3', event_bus=runtime.get('events'))
        runtime['sensorium_native_lab'] = lab
        return lab

    @router.get('')
    def about():
        require_owner()
        return identity_payload()

    @router.get('/storage-provider/{provider_id}', response_class=HTMLResponse)
    def storage_provider_page(provider_id: str):
        require_owner()
        data = get_data_plane(runtime)
        try:
            provider = _safe_provider(data.provider_status(provider_id))
        except KeyError as exc:
            raise HTTPException(404, 'Storage provider not found') from exc
        destinations = provider.get('destination') or {}
        destination_text = ', '.join(f'{key}: {value}' for key, value in destinations.items()) or 'No destination metadata exposed'
        capabilities = ', '.join(provider.get('capabilities') or []) or 'No provider capabilities currently reported'
        body = '<section class="card">' + ''.join((
            _row('Provider', provider.get('label')),
            _row('State', 'Available' if provider.get('available') else 'Not available', css='ok' if provider.get('available') else 'warn'),
            _row('Connected / consent', provider.get('consent_state')),
            _row('Capabilities', capabilities),
            _row('Destination', destination_text),
            _row('Verified', provider.get('verified_at')),
            _row('Last sync', provider.get('last_sync_at') or 'No sync timestamp reported'),
            _row('Last error', provider.get('last_error') or 'No provider error reported'),
        )) + '</section><section class="card"><strong>Protection</strong><p>' + html.escape(provider['encryption_statement']) + '</p><p>Credential values and credential references are deliberately not shown on this page.</p></section>'
        return _page('Connected Storage Provider', 'Read-only provider status from the canonical Data Plane. Data movement remains a separate governed action.', body)

    @router.get('/sensorium/status')
    def sensorium_status():
        require_owner()
        lab = native_lab()
        evidence = lab.list(limit=100)
        latest: dict[str, dict] = {}
        for item in evidence:
            latest.setdefault(str(item.get('provider') or ''), item)
        return {
            'providers': lab.profiles(),
            'latest_evidence': latest,
            'evidence_count': len(evidence),
            'live_availability_verified': False,
            'physical_device': False,
            'execution_authority': False,
            'message': 'This page reports saved qualification evidence. It does not probe a live device or grant adb, simctl, shell, keyboard, mouse, app-launch, or other device-control authority.',
        }

    @router.get('/sensorium', response_class=HTMLResponse)
    def sensorium_page():
        status = sensorium_status()
        cards = []
        for profile in status['providers']:
            provider = str(profile.get('provider') or '')
            evidence = status['latest_evidence'].get(provider) or {}
            cards.append('<section class="card">' + ''.join((
                _row('Provider', provider),
                _row('Platforms', ', '.join(profile.get('platforms') or [])),
                _row('Environment', profile.get('environment_kind')),
                _row('Saved evidence status', evidence.get('status') or 'No saved evidence'),
                _row('Last evidence', evidence.get('observed_at') or 'Not recorded'),
                _row('Target', evidence.get('target_id') or 'Not recorded'),
                _row('Physical device', 'No'),
                _row('Execution authority', 'No'),
            )) + '</section>')
        cards.append('<section class="card"><strong>Important boundary</strong><p>' + html.escape(status['message']) + '</p></section>')
        return _page('Sensorium Status & Providers', 'Advanced read-only evidence for emulator, simulator, and hosted-VM qualification.', ''.join(cards))

    @router.get('/updates', response_class=HTMLResponse)
    def updates_page():
        require_owner()
        identity = identity_payload()
        release = runtime.get('release_control')
        release_summary = None
        if release is not None:
            try:
                release_summary = release.summary()
            except Exception:
                release_summary = None
        body = '<section class="card">' + ''.join((
            _row('Installed version', identity['version']),
            _row('Build SHA', identity.get('build_sha') or 'Not embedded in this build'),
            _row('Release channel', identity['release_channel']),
            _row('Installed-app updater', 'Managed by platform / installation', css='warn'),
            _row('Signed in-app updater', 'Not connected'),
        )) + '</section>'
        body += '<section class="card"><strong>Release authority</strong>'
        if release_summary is None:
            body += '<p>The governed release authority is unavailable on this host. No update or release action is being claimed.</p>'
        else:
            body += '<p>The governed release authority is available for Vishnu engineering/release candidates. This is separate from an installed-app updater.</p>'
            body += '<div class="row"><div class="key">Summary</div><div class="value"><code>' + html.escape(json.dumps(release_summary, sort_keys=True, default=str)[:2000]) + '</code></div></div>'
            body += '<p><a href="/owner/releases">Open governed Release Control</a></p>'
        body += '</section><section class="card"><strong>Update safety</strong><p>' + html.escape(identity['updates']['message']) + '</p><p>Vishnu will not show a fake “Install update” action until a signed updater authority is actually connected and qualified.</p></section>'
        return _page('Updates & Release', 'Installed build identity and governed release status, with updater limitations stated explicitly.', body)

    @router.get('/notices', response_class=HTMLResponse)
    def notices_page():
        require_owner()
        identity = identity_payload()
        body = '<section class="card">' + ''.join((
            _row('Product', identity['product']),
            _row('Version', identity['version']),
            _row('Build', identity.get('build_sha') or 'Not embedded'),
            _row('License', identity['license']),
        )) + '</section><section class="card"><strong>Third-party notices</strong><p>Third-party license and dependency evidence remains part of Vishnu package/SBOM evidence. This page does not reinterpret third-party licenses.</p></section><section class="card"><a href="/iphone/#settings">Privacy & Settings</a><br><a href="/owner/security">Security controls</a><br><a href="/iphone/api/about/updates">Updates & Release</a></section>'
        return _page('About / Version / Notices', 'Stable product, build, license, privacy, security, and update identity.', body)

    return router
