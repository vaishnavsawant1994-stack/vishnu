from __future__ import annotations

import hashlib
import threading
import urllib.parse
import urllib.request

from ui.native_auth import LoopbackCallback, make_pkce_pair


def test_desktop_pkce_pair_is_s256_and_state_is_independent():
    verifier, state, challenge = make_pkce_pair()
    expected = __import__("base64").urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    assert len(verifier) >= 43
    assert len(state) >= 32
    assert challenge == expected
    assert state != verifier


def test_desktop_callback_binds_one_local_code_and_state():
    server = LoopbackCallback(port=0)
    result = {}
    waiter = threading.Thread(target=lambda: result.setdefault("value", server.wait_for_code(timeout=3)), daemon=True)
    waiter.start()
    query = urllib.parse.urlencode({"code": "single-use-code", "state": "random-owner-state"})
    with urllib.request.urlopen("http://127.0.0.1:%d/native/callback?%s" % (server.server_address[1], query), timeout=2) as response:
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
    waiter.join(timeout=3)
    server.server_close()
    assert result["value"] == ("single-use-code", "random-owner-state")


def test_desktop_callback_wait_can_be_cancelled():
    server = LoopbackCallback(port=0)
    cancelled = threading.Event()
    outcome = {}
    def wait():
        try:
            server.wait_for_code(timeout=3, cancelled=cancelled)
        except InterruptedError:
            outcome["cancelled"] = True
    waiter = threading.Thread(target=wait, daemon=True)
    waiter.start()
    cancelled.set()
    waiter.join(timeout=2)
    server.server_close()
    assert outcome.get("cancelled") is True
