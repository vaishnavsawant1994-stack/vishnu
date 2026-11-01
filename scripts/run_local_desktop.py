"""Run the canonical web UI in a native Windows desktop window."""

from __future__ import annotations

import socket
import json
import sys
import threading
import time
from urllib.request import urlopen

import uvicorn
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.config import settings


def _web_url() -> str:
    host = settings.control_server_host
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The embedded desktop UI requires a loopback-only local web server")
    # /web/ is the public canonical URL; middleware maps it onto the PWA router
    # that serves the shared Phase 2 screen modules.
    return f"http://127.0.0.1:{settings.control_server_port}/web/"


def _server_is_running(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _verify_existing_local_setup(host: str, port: int) -> None:
    """Do not silently reuse a stale, non-development server for first run."""
    try:
        with urlopen(f"http://{host}:{port}/web/api/access/options", timeout=3) as response:
            options = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "A server is already using Vishnu's desktop port, but its first-run settings could not be verified. "
            "Stop that server and restart it with scripts/start_web_dev.ps1 or scripts/start_windows_dev.ps1."
        ) from exc
    if ((options.get("restore_available") or options.get("setup_in_progress"))
            and not options.get("creation_available")
            and not options.get("local_setup_available")):
        raise RuntimeError(
            "The existing local server has first-run setup disabled. Stop it and restart with "
            "scripts/start_web_dev.ps1 or scripts/start_windows_dev.ps1; no Vishnu data was changed."
        )


def _serve_local_ui() -> tuple[uvicorn.Server | None, threading.Thread | None]:
    if _server_is_running("127.0.0.1", settings.control_server_port):
        _verify_existing_local_setup("127.0.0.1", settings.control_server_port)
        return None, None

    from server import cloud_app

    config = uvicorn.Config(
        cloud_app.app,
        host="127.0.0.1",
        port=settings.control_server_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="vishnu-local-web", daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.started:
            return server, thread
        if not thread.is_alive():
            raise RuntimeError("Vishnu's local web runtime stopped during startup")
        time.sleep(0.1)
    server.should_exit = True
    raise TimeoutError("Vishnu's local web runtime did not become ready within 30 seconds")


def main() -> int:
    server, server_thread = _serve_local_ui()
    app = QApplication(sys.argv)
    app.setApplicationName("Vishnu")

    window = QMainWindow()
    window.setWindowTitle("Vishnu")
    profile_dir = settings.data_dir / "browser-profile"
    cache_dir = profile_dir / "cache"
    profile_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    profile = QWebEngineProfile("vishnu-desktop", app)
    profile.setPersistentStoragePath(str(profile_dir))
    profile.setCachePath(str(cache_dir))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    web_view = QWebEngineView(window)
    web_view.setPage(QWebEnginePage(profile, web_view))
    web_view.setUrl(QUrl(_web_url()))
    window.setCentralWidget(web_view)
    # Start maximized so the shared PWA shell is not clipped on displays whose
    # work area is smaller than the former fixed 1440x960 initial size.
    # Give the window a real fallback geometry before maximize; some Windows
    # window managers otherwise keep the QMainWindow at Qt's tiny default size.
    window.setMinimumSize(640, 480)
    window.resize(1440, 900)
    window.show()
    window.showMaximized()

    try:
        return app.exec()
    finally:
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
