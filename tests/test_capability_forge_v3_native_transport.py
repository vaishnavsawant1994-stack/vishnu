from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.capability_forge_v3_api import capability_forge_oauth_callback_router, capability_forge_v3_router
from server.pwa_session_middleware import PwaSessionMiddleware


class Sessions:
    native_client_redirects = {"native": ["https://vishnu.example/iphone/native/callback"]}

    def authenticate_native(self, token):
        if token != "native-token":
            return None
        return SimpleNamespace(
            device_id="device-1",
            id="native-session-1",
            reauthenticated_at=time.time(),
            scopes=("device:read", "device:admin"),
            kind="native",
        )

    def authenticate(self, token, device_id):
        return None

    def revoke(self, session_id):
        return None

    def issue(self, device_id, reauthenticated=False):
        return "browser-token", SimpleNamespace()

    def revoke_token(self, token):
        return None


class Devices:
    def is_active(self, device_id):
        return device_id == "device-1"

    def authorize(self, device_id, scope):
        return device_id == "device-1" and scope in {"device:read", "device:admin"}


class Readiness:
    def evaluate(self, **kwargs):
        return SimpleNamespace(to_dict=lambda: {"ready": False, "checks": {}, "blockers": ["deployment config absent"]})


class Catalog:
    def all(self):
        return []


class OAuthCallback:
    def complete_state(self, *, state, code):
        assert state == "s" * 16
        assert code == "provider-code"
        return SimpleNamespace(capability_id="generated.test")

    def discard(self, state):
        return None


def _app(runtime):
    app = FastAPI()
    app.include_router(capability_forge_v3_router(runtime))
    app.include_router(capability_forge_oauth_callback_router(runtime))
    app.add_middleware(
        PwaSessionMiddleware,
        sessions=runtime["pwa_sessions"],
        device_registry=runtime["device_registry"],
        cookie_max_age=3600,
    )
    return app


def test_v3_owner_api_accepts_scoped_native_bearer_session(monkeypatch):
    sessions = Sessions()
    runtime = {
        "pwa_sessions": sessions,
        "device_registry": Devices(),
        "capability_forge_production_readiness": Readiness(),
        "capability_catalog": Catalog(),
        "android_asset_links": [],
        "apple_app_site_association": {},
        "capability_forge_provenance": object(),
        "capability_forge_provider_verifier": object(),
        "capability_forge_rollout": object(),
        "capability_forge_oauth": object(),
    }
    client = TestClient(_app(runtime))
    response = client.get(
        "/iphone/api/owner/forge/v3/readiness",
        headers={"Authorization": "Bearer native-token"},
    )
    assert response.status_code == 200
    assert response.json()["production_activation_authority"] is False


def test_external_capability_oauth_callback_is_not_blocked_by_session_middleware():
    sessions = Sessions()
    runtime = {
        "pwa_sessions": sessions,
        "device_registry": Devices(),
        "capability_forge_oauth": OAuthCallback(),
    }
    client = TestClient(_app(runtime))
    response = client.get(
        "/iphone/capability-oauth/callback",
        params={"state": "s" * 16, "code": "provider-code"},
    )
    assert response.status_code == 200
    assert "generated.test" in response.text
