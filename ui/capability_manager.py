from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

import keyring
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox,
    QPushButton, QPlainTextEdit, QTextBrowser, QVBoxLayout,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl


CLIENT_ID = "ai.personal.companion.desktop"
REDIRECT_URI = "http://127.0.0.1:49173/native/callback"
KEYRING_SERVICE = "vishnu.native.capabilities"
MAX_RESPONSE_BYTES = 1_048_576


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def make_pkce_pair() -> tuple[str, str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    state = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, state, challenge


class _LoopbackCallback(HTTPServer):
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


class _AuthorizeWorker(QThread):
    open_browser = pyqtSignal(str)
    completed = pyqtSignal(str, int)
    failed = pyqtSignal(str)

    def __init__(self, cloud_base: str):
        super().__init__()
        self.cloud_base = cloud_base.rstrip("/")
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    def run(self):
        server = None
        try:
            verifier, state, challenge = make_pkce_pair()
            server = _LoopbackCallback()
            auth = self.cloud_base + "/iphone/native/authorize?" + urlencode({
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "code_challenge": challenge,
                "state": state,
            })
            self.open_browser.emit(auth)
            # Serve the registered callback on loopback until the owner returns.
            code, returned_state = server.wait_for_code(cancelled=self.cancelled)
            if not hmac.compare_digest(state, returned_state) or not code:
                raise PermissionError("Native sign-in state validation failed.")
            exchange = requests.Session()
            exchange.trust_env = False
            try:
                response = exchange.post(
                    self.cloud_base + "/iphone/api/native/sessions/exchange",
                    json={"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
                          "code": code, "code_verifier": verifier},
                    timeout=(4, 15), allow_redirects=False, stream=True,
                )
                payload = _bounded_json(response)
            finally:
                exchange.close()
            if response.status_code != 200:
                raise PermissionError("Vishnu did not authorize this desktop session.")
            token = payload.get("access_token")
            ttl = int(payload.get("expires_in", 0))
            if not isinstance(token, str) or not token or ttl <= 0:
                raise ValueError("Vishnu returned an invalid desktop session.")
            self.completed.emit(token, int(time.time()) + ttl)
        except Exception as exc:
            self.failed.emit(str(exc)[:240])
        finally:
            if server is not None:
                server.server_close()


def _bounded_json(response) -> dict:
    try:
        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ValueError("Vishnu response exceeded the 1 MiB limit.")
        value = json.loads(bytes(content))
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise ValueError("Vishnu returned an invalid response.") from exc
    finally:
        response.close()
    if not isinstance(value, dict):
        raise ValueError("Vishnu returned an invalid response.")
    return value


class NativeCapabilityManager(QDialog):
    """Desktop owner interface backed only by Vishnu's governed capability API."""

    def __init__(self, cloud_url: str, parent=None):
        super().__init__(parent)
        parsed = urlparse(cloud_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Capability management requires Vishnu HTTPS.")
        self.api_base = f"{parsed.scheme}://{parsed.netloc}/iphone/api"
        self.cloud_base = f"{parsed.scheme}://{parsed.netloc}"
        self._worker = None
        self._capabilities: list[dict] = []
        self.setWindowTitle("Vishnu · Universal Capabilities")
        self.resize(980, 680)
        self.setStyleSheet("QDialog,QWidget{background:#071019;color:#e8f0f4;font-family:Inter,Segoe UI,Arial} QPushButton{background:#173447;border:1px solid #35576a;border-radius:8px;padding:8px 12px} QPushButton:hover{background:#20506a} QListWidget,QTextBrowser,QPlainTextEdit{background:#0c1822;border:1px solid #263b49;border-radius:8px;padding:8px}")
        root = QVBoxLayout(self)
        title = QLabel("Universal Capabilities")
        title.setStyleSheet("font-size:22px;font-weight:700")
        self.status = QLabel("Sign in with the Vishnu owner account to manage capabilities.")
        self.status.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(self.status)
        toolbar = QHBoxLayout()
        for text, slot in (("Sign in / refresh", self.authorize), ("Search", self.search), ("Reload", self.reload),
                           ("Import OpenAPI", self.import_openapi), ("Add MCP server", self.add_mcp),
                           ("Rotate session", self.rotate_session), ("Sign out", self.logout)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        root.addLayout(toolbar)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_detail)
        self.detail = QTextBrowser()
        body.addWidget(self.list, 1)
        body.addWidget(self.detail, 2)
        root.addLayout(body, 1)
        actions = QHBoxLayout()
        for text, slot in (("Connect / approve", self.connect_selected), ("Test / execute", self.execute_selected),
                           ("History", lambda: self.read_selected("history")),
                           ("Audit", lambda: self.read_selected("audit")),
                           ("Rotate credential", self.rotate_selected), ("Disconnect", self.disconnect_selected)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            actions.addWidget(button)
        root.addLayout(actions)
        self._token = keyring.get_password(KEYRING_SERVICE, "access_token")
        self._expires = int(keyring.get_password(KEYRING_SERVICE, "expires_at") or 0)
        if self._token and self._expires > int(time.time()):
            self.reload()
        else:
            self._clear_session()

    def authorize(self):
        self.status.setText("Opening the system browser for owner authorization…")
        worker = _AuthorizeWorker(self.cloud_base)
        self._worker = worker
        worker.open_browser.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        worker.completed.connect(self._authorized)
        worker.failed.connect(lambda error: self.status.setText(error))
        worker.start()

    def _authorized(self, token: str, expires: int):
        try:
            keyring.set_password(KEYRING_SERVICE, "access_token", token)
            keyring.set_password(KEYRING_SERVICE, "expires_at", str(expires))
        except Exception:
            self.status.setText("The operating system secure credential store is unavailable; the session was not saved.")
            return
        self._token, self._expires = token, expires
        self.status.setText("Owner session connected. Vishnu rechecks device permissions for every action.")
        self.reload()

    def _clear_session(self):
        self._token, self._expires = None, 0
        for key in ("access_token", "expires_at"):
            try:
                keyring.delete_password(KEYRING_SERVICE, key)
            except Exception:
                pass

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self._token or self._expires <= int(time.time()):
            self._clear_session()
            raise PermissionError("Your native owner session expired. Sign in again.")
        response = requests.request(method, self.api_base + path, json=payload,
            headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
            timeout=(4, 15), allow_redirects=False, stream=True)
        result = _bounded_json(response)
        if response.status_code == 401:
            self._clear_session()
            raise PermissionError("Owner session expired or was revoked. Sign in again.")
        if response.status_code >= 400:
            raise RuntimeError("Vishnu denied this action (HTTP %s)." % response.status_code)
        return result

    def _sensitive(self, callback):
        password, ok = QInputDialog.getText(self, "Verify owner", "Re-enter the owner password:", QInputDialog.EchoMode.Password)
        if not ok or not password:
            return
        self._request("POST", "/native/sessions/reauth", {"password": password})
        return callback()

    def reload(self):
        try:
            result = self._request("GET", "/apps-tools/capabilities?query=" + quote(getattr(self, "_query", "")) + "&limit=100")
            self._capabilities = result.get("capabilities", [])
            self.list.clear()
            for item in self._capabilities:
                self.list.addItem("%s · %s · %s" % (item.get("name", "Capability"), item.get("method", item.get("type", "tool")), item.get("risk", "review")))
            self.status.setText("%s capabilities · owner permissions are enforced on every request" % len(self._capabilities))
        except Exception as exc:
            self.status.setText(str(exc))

    def search(self):
        query, ok = QInputDialog.getText(self, "Search capabilities", "Search catalog:", text=getattr(self, "_query", ""))
        if ok:
            self._query = query
            self.reload()

    def rotate_session(self):
        try:
            result = self._request("POST", "/native/sessions/rotate", {})
            token = result.get("access_token")
            ttl = int(result.get("expires_in", 0))
            if not isinstance(token, str) or not token or ttl <= 0:
                raise ValueError("Vishnu returned an invalid rotated session.")
            keyring.set_password(KEYRING_SERVICE, "access_token", token)
            self._token = token
            self._expires = int(time.time()) + ttl
            keyring.set_password(KEYRING_SERVICE, "expires_at", str(self._expires))
            self.status.setText("Native owner session rotated.")
        except Exception as exc:
            self.status.setText(str(exc))

    def _selected(self):
        index = self.list.currentRow()
        return self._capabilities[index] if 0 <= index < len(self._capabilities) else None

    def show_detail(self, index: int):
        if not 0 <= index < len(self._capabilities):
            return
        item = self._capabilities[index]
        try:
            detail = self._request("GET", "/apps-tools/capabilities/" + quote(item["id"], safe=""))
            self.detail.setPlainText(json.dumps(detail.get("capability", item), indent=2, ensure_ascii=False))
        except Exception as exc:
            self.detail.setPlainText(str(exc))

    def import_openapi(self):
        text, ok = QInputDialog.getMultiLineText(self, "Discover OpenAPI", "Paste the OpenAPI JSON document:")
        if not ok or not text:
            return
        try:
            doc = json.loads(text)
            self._sensitive(lambda: self._request("POST", "/apps-tools/capabilities/openapi", {"document": doc}))
            self.status.setText("OpenAPI operations discovered. They remain inactive until individually connected and approved.")
            self.reload()
        except Exception as exc:
            self.status.setText(str(exc))

    def add_mcp(self):
        text, ok = QInputDialog.getMultiLineText(self, "Discover MCP server", 'Enter JSON such as {"name":"Example","url":"https://host/mcp"}:')
        if not ok or not text:
            return
        try:
            item = json.loads(text)
            self._sensitive(lambda: self._request("POST", "/apps-tools/mcp/servers", item))
            self.status.setText("MCP server discovered. Connect it and review every tool's risk before use.")
            self.reload()
        except Exception as exc:
            self.status.setText(str(exc))

    def connect_selected(self):
        item = self._selected()
        if not item:
            return
        if item.get("type") == "mcp_tool":
            risk, ok = QInputDialog.getItem(self, "Review MCP tool risk", "Choose risk after reviewing the tool schema:", ["read", "write", "destructive"], 0, False)
            if not ok:
                return
            payload = {"risk": risk, "reviewed": True, "read_only_attested": risk == "read"}
            try:
                self._sensitive(lambda: self._request("POST", "/apps-tools/mcp/capabilities/%s/approve" % quote(item["id"], safe=""), payload))
                self.status.setText("MCP tool risk approved. Execution still passes through Vishnu permissions.")
                self.show_detail(self.list.currentRow())
            except Exception as exc:
                self.status.setText(str(exc))
            return
        auth_type, ok = QInputDialog.getItem(self, "Connection authentication", "Authentication:", ["none", "bearer_token", "api_key_header"], 0, False)
        if not ok:
            return
        secret = ""
        server_url = ""
        if item.get("type") != "mcp_server" and item.get("type") != "mcp_tool":
            server_url, ok = QInputDialog.getText(self, "API server", "Approved HTTPS server URL:", text=str(item.get("source_url") or ""))
            if not ok or not server_url:
                return
        if auth_type != "none":
            secret, ok = QInputDialog.getText(self, "Credential", "The secret is sent only to Vishnu's vault:", QInputDialog.EchoMode.Password)
            if not ok or not secret:
                return
        try:
            def connect():
                if item.get("type") == "mcp_server":
                    return self._request("POST", "/apps-tools/mcp/servers/%s/discover" % quote(item["id"], safe=""),
                        {"auth_type": auth_type, "api_key": secret})
                return self._request("POST", "/apps-tools/capabilities/%s/connect" % quote(item["id"], safe=""),
                    {"server_url": server_url, "auth_type": auth_type, "api_key": secret})
            self._sensitive(connect)
            self.status.setText("Connection stored in Vishnu's credential vault.")
            self.show_detail(self.list.currentRow())
        except Exception as exc:
            self.status.setText(str(exc))

    def execute_selected(self):
        item = self._selected()
        if not item:
            return
        raw, ok = QInputDialog.getMultiLineText(self, "Test capability", "Operation parameters as JSON:", "{}")
        if not ok:
            return
        try:
            params = json.loads(raw)
            if not isinstance(params, dict):
                raise ValueError("Parameters must be a JSON object.")
            is_mcp_write = item.get("type") == "mcp_tool" and item.get("approved_risk") in {"write", "destructive"}
            method = str(item.get("method", "GET")).upper()
            if method != "GET" or is_mcp_write:
                answer = QMessageBox.question(self, "Approve one write", "Create and consume a one-time approval for these exact parameters?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
                def perform():
                    path = "/apps-tools/capabilities/%s/execution-approvals" % quote(item["id"], safe="")
                    ticket = self._request("POST", path, {"parameters": params})
                    approval = ticket.get("approval_id")
                    approval_path = "/apps-tools/capabilities/%s/execution-approvals/%s/approve" % (quote(item["id"], safe=""), quote(approval or "", safe=""))
                    self._request("POST", approval_path, {"parameters": params})
                    return self._request("POST", "/apps-tools/capabilities/%s/execute" % quote(item["id"], safe=""), {"parameters": params, "approval_id": approval})
                result = self._sensitive(perform)
            else:
                result = self._request("POST", "/apps-tools/capabilities/%s/execute" % quote(item["id"], safe=""), {"parameters": params})
            if result is None:
                return
            self.status.setText("Provider response received; independently verified: %s" % (result.get("verified", False)))
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(str(exc))

    def read_selected(self, kind: str):
        item = self._selected()
        if not item:
            return
        try:
            result = self._request("GET", "/apps-tools/capabilities/%s/%s?limit=50" % (quote(item["id"], safe=""), kind))
            self.detail.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as exc:
            self.status.setText(str(exc))

    def rotate_selected(self):
        item = self._selected()
        if not item:
            return
        secret, ok = QInputDialog.getText(self, "Rotate credential", "Replacement secret:", QInputDialog.EchoMode.Password)
        if not ok or not secret:
            return
        try:
            self._sensitive(lambda: self._request("POST", "/apps-tools/capabilities/%s/credentials/rotate" % quote(item["id"], safe=""), {"auth_type": "bearer_token", "api_key": secret}))
            self.status.setText("Credential rotated in Vishnu's vault.")
        except Exception as exc:
            self.status.setText(str(exc))

    def disconnect_selected(self):
        item = self._selected()
        if not item:
            return
        if QMessageBox.question(self, "Disconnect", "Revoke this capability connection?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self._sensitive(lambda: self._request("POST", "/apps-tools/capabilities/%s/disconnect" % quote(item["id"], safe=""), {}))
            self.status.setText("Capability disconnected and revoked.")
            self.reload()
        except Exception as exc:
            self.status.setText(str(exc))

    def logout(self):
        try:
            if self._token and self._expires > int(time.time()):
                self._request("POST", "/native/sessions/logout", {})
        except Exception:
            pass
        self._clear_session()
        self.list.clear()
        self.detail.clear()
        self.status.setText("Desktop owner session revoked and removed from the OS credential store.")

    def closeEvent(self, event):
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(2000)
        super().closeEvent(event)
