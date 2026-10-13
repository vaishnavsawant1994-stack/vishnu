from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI

from server.capability_forge_v3_api import capability_forge_oauth_callback_router, capability_forge_v3_router
from server.capability_forge_v3_ui import capability_forge_v3_ui_router
from server.native_capability_auth import native_capability_auth_router


def test_capability_forge_v3_routes_are_mounted_once_beside_native_capability_boundary():
    runtime = {
        "pwa_sessions": SimpleNamespace(native_client_redirects={}),
        "device_registry": SimpleNamespace(),
    }
    app = FastAPI()
    app.include_router(native_capability_auth_router(runtime))
    app.include_router(capability_forge_v3_router(runtime))
    app.include_router(capability_forge_oauth_callback_router(runtime))
    app.include_router(capability_forge_v3_ui_router())
    paths = [route.path for route in app.routes]
    assert paths.count("/iphone/api/owner/forge/v3/readiness") == 1
    assert paths.count("/iphone/api/owner/forge/v3/oauth/providers") == 1
    assert paths.count("/iphone/api/owner/forge/v3/providers/verify") == 1
    assert paths.count("/iphone/capability-oauth/callback") == 1
    assert paths.count("/capabilities/forge/production-readiness") == 1
