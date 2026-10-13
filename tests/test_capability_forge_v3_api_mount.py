from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from server.capability_forge_v3_api import capability_forge_oauth_callback_router, capability_forge_v3_router
from server.capability_forge_v3_ui import capability_forge_v3_ui_router


ROOT = Path(__file__).resolve().parents[1]


def _paths(router) -> list[str]:
    return [path for route in router.routes if (path := getattr(route, "path", None))]


def test_capability_forge_v3_routes_are_defined_once_and_cloud_app_mounts_each_router_once():
    runtime = {
        "pwa_sessions": SimpleNamespace(native_client_redirects={}),
        "device_registry": SimpleNamespace(),
    }
    paths = (
        _paths(capability_forge_v3_router(runtime))
        + _paths(capability_forge_oauth_callback_router(runtime))
        + _paths(capability_forge_v3_ui_router())
    )
    assert paths.count("/iphone/api/owner/forge/v3/readiness") == 1
    assert paths.count("/iphone/api/owner/forge/v3/oauth/providers") == 1
    assert paths.count("/iphone/api/owner/forge/v3/providers/verify") == 1
    assert paths.count("/iphone/capability-oauth/callback") == 1
    assert paths.count("/capabilities/forge/production-readiness") == 1

    cloud = (ROOT / "server/cloud_app.py").read_text(encoding="utf-8")
    assert cloud.count("app.include_router(capability_forge_v3_router(runtime))") == 1
    assert cloud.count("app.include_router(capability_forge_oauth_callback_router(runtime))") == 1
    assert cloud.count("app.include_router(capability_forge_v3_ui_router())") == 1
