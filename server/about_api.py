from __future__ import annotations

import os
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter, HTTPException

from security.request_context import current_trusted_request


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


def about_router(runtime):
    """Expose safe release identity; updates remain platform/install managed."""
    router = APIRouter(prefix='/iphone/api/about', tags=['about'])
    registry = runtime['device_registry']

    @router.get('')
    def about():
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not registry.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if context.auth_type == 'native' and (context.scopes is None or 'device:read' not in context.scopes):
            raise HTTPException(403, 'This native session is not scoped for device:read')
        if not registry.authorize(context.device_id, 'device:read'):
            raise HTTPException(403, 'This device is not permitted to inspect release identity')
        build_version, version_source = _release_identity()
        return {
            'product': 'Vishnu',
            'version': build_version,
            'version_source': version_source,
            'build_sha': str(os.getenv('VISHNU_BUILD_SHA') or os.getenv('VISHNU_RELEASE_REVISION') or '').strip() or None,
            'release_channel': str(os.getenv('VISHNU_RELEASE_CHANNEL', 'unknown')).strip() or 'unknown',
            'updates': {
                'available': False,
                'status': 'managed_by_installation',
                'message': 'This installation does not expose an in-app update flow. Updates are managed by the platform or installation owner.',
            },
        }

    return router
