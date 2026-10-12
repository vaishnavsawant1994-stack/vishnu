from __future__ import annotations

import base64
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from security.pwa_sessions import PwaSessionStore
from security.request_context import current_trusted_request
from server.pwa_security import pwa_security_router
from server.pwa_session_middleware import PwaSessionMiddleware


CLIENT = "ai.personal.companion.android"
REDIRECT = "https://vishnu.example/native/callback/android"
SCOPES = ["device:read"]


def challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class Devices:
    def is_active(self, device_id):
        return device_id in {"device-a", "device-b"}

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in {"device:read", "device:admin"}


class OwnerAccess:
    def password_configured(self):
        return True

    def verify_password(self, password):
        return password == "owner-password"


def test_native_session_exchange_is_pkce_bound_durable_scoped_and_revocable(tmp_path):
    path = tmp_path / "sessions.sqlite3"
    store = PwaSessionStore(path, native_client_redirects={CLIENT: [REDIRECT]})
    browser_token, browser = store.issue("device-a")
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    code = store.create_native_authorization_code(
        browser_session_id=browser.id, device_id="device-a", client_id=CLIENT,
        redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES,
    )
    assert code not in path.read_bytes().decode("latin1", errors="ignore")

    restarted = PwaSessionStore(path, native_client_redirects={CLIENT: [REDIRECT]})
    token, session = restarted.exchange_native_authorization_code(
        code=code, verifier=verifier, client_id=CLIENT, redirect_uri=REDIRECT,
    )
    assert token not in path.read_bytes().decode("latin1", errors="ignore")
    assert session.kind == "native"
    assert session.scopes == tuple(SCOPES)
    assert restarted.authenticate(token, "device-a") is None
    assert restarted.authenticate_native(token).id == session.id
    assert restarted.authenticate_native(token + "x") is None
    rotated, replacement = restarted.rotate_native(session.id)
    assert restarted.authenticate_native(token) is None
    assert restarted.authenticate_native(rotated).id == replacement.id
    assert replacement.scopes == tuple(SCOPES)
    assert restarted.revoke_device("device-a") == 2
    assert restarted.authenticate_native(token) is None
    assert restarted.authenticate_native(rotated) is None
    assert restarted.authenticate(browser_token, "device-a") is None


def test_native_codes_reject_bad_pkce_redirect_client_cross_device_and_expiry(tmp_path):
    store = PwaSessionStore(tmp_path / "sessions.sqlite3", native_client_redirects={CLIENT: [REDIRECT]})
    _, browser = store.issue("device-a")
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    code = store.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
        client_id=CLIENT, redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES, now=1000)
    with pytest.raises(PermissionError, match="PKCE"):
        store.exchange_native_authorization_code(code=code, verifier=verifier + "wrong", client_id=CLIENT,
                                                 redirect_uri=REDIRECT, now=1001)
    with pytest.raises(PermissionError, match="binding"):
        store.exchange_native_authorization_code(code=code, verifier=verifier, client_id=CLIENT,
                                                 redirect_uri="https://attacker.example/callback", now=1001)
    with pytest.raises(PermissionError, match="binding"):
        store.exchange_native_authorization_code(code=code, verifier=verifier, client_id="another.app",
                                                 redirect_uri=REDIRECT, now=1001)
    with pytest.raises(PermissionError, match="expired"):
        store.exchange_native_authorization_code(code=code, verifier=verifier, client_id=CLIENT,
                                                 redirect_uri=REDIRECT, now=1091)
    with pytest.raises(ValueError, match="registered"):
        store.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
            client_id=CLIENT, redirect_uri="https://attacker.example/callback", challenge=challenge(verifier), scopes=SCOPES)
    _, other_device_session = store.issue("device-b")
    cross_device_code = store.create_native_authorization_code(
        browser_session_id=other_device_session.id, device_id="device-b", client_id=CLIENT,
        redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES,
    )
    store.revoke(other_device_session.id)
    with pytest.raises(PermissionError, match="authorizing owner session"):
        store.exchange_native_authorization_code(code=cross_device_code, verifier=verifier,
            client_id=CLIENT, redirect_uri=REDIRECT)


def test_native_authorization_requires_recent_browser_reauth_and_known_scopes(tmp_path):
    store = PwaSessionStore(tmp_path / "sessions.sqlite3", native_client_redirects={CLIENT: [REDIRECT]})
    _, browser = store.issue("device-a")
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    store.mark_reauthenticated(browser.id, at=1)
    with pytest.raises(PermissionError, match="recent authenticated owner"):
        store.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
            client_id=CLIENT, redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES)
    store.mark_reauthenticated(browser.id)
    with pytest.raises(ValueError, match="scopes"):
        store.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
            client_id=CLIENT, redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=["owner:root"])


def test_native_code_has_atomic_single_redemption(tmp_path):
    store = PwaSessionStore(tmp_path / "sessions.sqlite3", native_client_redirects={CLIENT: [REDIRECT]})
    _, browser = store.issue("device-a")
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    code = store.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
        client_id=CLIENT, redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES)
    barrier = threading.Barrier(2)

    def redeem(_):
        barrier.wait()
        try:
            return store.exchange_native_authorization_code(code=code, verifier=verifier,
                client_id=CLIENT, redirect_uri=REDIRECT)[0]
        except PermissionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, range(2)))
    assert sum(token is not None for token in results) == 1


def test_native_api_bearer_is_restricted_to_capability_routes_and_device_scope(tmp_path):
    redirects = {CLIENT: [REDIRECT]}
    sessions = PwaSessionStore(tmp_path / "sessions.sqlite3", native_client_redirects=redirects)
    device_token, browser = sessions.issue("device-a")
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    code = sessions.create_native_authorization_code(browser_session_id=browser.id, device_id="device-a",
        client_id=CLIENT, redirect_uri=REDIRECT, challenge=challenge(verifier), scopes=SCOPES)
    native_token, native = sessions.exchange_native_authorization_code(code=code, verifier=verifier,
        client_id=CLIENT, redirect_uri=REDIRECT)
    app = FastAPI()
    devices = Devices()
    app.add_middleware(PwaSessionMiddleware, sessions=sessions, device_registry=devices, cookie_max_age=600)

    @app.get("/iphone/api/apps-tools/test")
    def capability():
        current = current_trusted_request()
        return {"session_id": current.session_id, "device_id": current.device_id,
                "auth_type": current.auth_type, "scopes": sorted(current.scopes or ())}

    @app.get("/iphone/api/protected")
    def browser_only():
        return {"ok": True}

    client = TestClient(app, base_url="https://testserver")
    native_response = client.get("/iphone/api/apps-tools/test", headers={"Authorization": "Bearer " + native_token})
    assert native_response.status_code == 200
    assert native_response.json() == {"session_id": native.id, "device_id": "device-a",
                                      "auth_type": "native", "scopes": SCOPES}
    assert client.get("/iphone/api/protected", headers={"Authorization": "Bearer " + native_token}).status_code == 401
    assert client.get("/iphone/api/apps-tools/test", headers={"Authorization": "Bearer " + device_token}).status_code == 401
    devices.active.remove("device-a")
    assert client.get("/iphone/api/apps-tools/test", headers={"Authorization": "Bearer " + native_token}).status_code == 401
    assert sessions.authenticate_native(native_token) is None


def test_native_session_routes_require_owner_browser_and_support_exchange_reauth_logout(tmp_path):
    sessions = PwaSessionStore(tmp_path / "sessions.sqlite3", native_client_redirects={CLIENT: [REDIRECT]})
    runtime = {"pwa_sessions": sessions, "owner_access": OwnerAccess(), "device_registry": Devices(),
               "integrations": None}
    app = FastAPI()
    app.add_middleware(PwaSessionMiddleware, sessions=sessions, device_registry=runtime["device_registry"], cookie_max_age=600)

    @app.post("/iphone/api/access/password/login")
    def login(response: Response):
        response.set_cookie("pa_device", "device-a", httponly=True, secure=True, path="/iphone")
        return {"ok": True}

    app.include_router(pwa_security_router(runtime))
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/iphone/api/access/password/login").status_code == 200
    verifier = "verifier-value-with-sufficient-entropy-0123456789abcdef"
    code = client.post("/iphone/api/native/sessions/authorize", json={
        "client_id": CLIENT, "redirect_uri": REDIRECT,
        "code_challenge": challenge(verifier), "scopes": ["device:read"],
    })
    assert code.status_code == 200, code.text
    exchange = client.post("/iphone/api/native/sessions/exchange", json={
        "client_id": CLIENT, "redirect_uri": REDIRECT,
        "code": code.json()["code"], "code_verifier": verifier,
    })
    assert exchange.status_code == 200, exchange.text
    result = exchange.json()
    assert "access_token" in result and result["scopes"] == ["device:read"]
    token = result["access_token"]
    assert sessions.authenticate_native(token).id == result["session_id"]
    assert client.post("/iphone/api/native/sessions/reauth", json={"password": "owner-password"},
                       headers={"Authorization": "Bearer " + token}).status_code == 200
    assert client.post("/iphone/api/native/sessions/logout", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert sessions.authenticate_native(token) is None

