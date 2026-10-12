"""Standard-library native authorization helpers for the desktop client."""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def make_pkce_pair() -> tuple[str, str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    state = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, state, challenge


class LoopbackCallback(HTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, port: int = 49173):
        self.result: tuple[str, str] | None = None
        self.received = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query, keep_blank_values=True)
                code = (query.get("code") or [""])[0]
                state = (query.get("state") or [""])[0]
                if parsed.path != "/native/callback" or len(code) > 256 or len(state) > 200:
                    self.send_error(400)
                    return
                owner.result = (code, state)
                owner.received.set()
                body = b"Vishnu sign-in returned to the desktop app. You may close this tab."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        super().__init__(("127.0.0.1", port), Handler)
        self.timeout = 0.5

    def wait_for_code(self, timeout: float = 240, cancelled: threading.Event | None = None) -> tuple[str, str]:
        deadline = time.monotonic() + timeout
        while not self.received.is_set() and time.monotonic() < deadline and not (cancelled and cancelled.is_set()):
            self.handle_request()
        if self.result is None:
            if cancelled and cancelled.is_set():
                raise InterruptedError("Desktop sign-in was cancelled.")
            raise TimeoutError("Owner authorization did not return to Vishnu desktop.")
        return self.result
