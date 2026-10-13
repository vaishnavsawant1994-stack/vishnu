from __future__ import annotations

from types import SimpleNamespace

from server.native_capability_auth import native_capability_auth_router


def test_capability_forge_v3_routes_are_exposed_through_native_capability_boundary():
    runtime = {
        "pwa_sessions": SimpleNamespace(native_client_redirects={}),
        "device_registry": SimpleNamespace(),
    }
    router = native_capability_auth_router(runtime)
    paths = {route.path for route in router.routes}
    assert "/iphone/api/owner/forge/v3/readiness" in paths
    assert "/iphone/api/owner/forge/v3/oauth/providers" in paths
    assert "/iphone/api/owner/forge/v3/providers/verify" in paths
    assert "/iphone/capability-oauth/callback" in paths
