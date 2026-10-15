from __future__ import annotations

import ipaddress
import json
import socket
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests

from core.sqlite import Migration, connect_sqlite, run_migrations


class ExternalCameraRegistry:
    """Owner-registered HTTPS snapshot cameras with pinned configuration.

    Requests can only target a URL already stored by the owner. The capture API
    never accepts arbitrary URLs or arbitrary headers, redirects are disabled,
    response size is bounded, and credentials live only in SecretVault.
    """

    COMPONENT = "sensorium_external_cameras"
    MAX_FRAME_BYTES = 2_000_000
    TIMEOUT_SECONDS = 8.0

    def __init__(self, path: Path, *, vault, events=None) -> None:
        if vault is None:
            raise RuntimeError("external camera credentials require SecretVault")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vault = vault
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "external-camera-registry", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS external_cameras(
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                snapshot_url TEXT NOT NULL,
                auth_kind TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )"""
        )

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    @staticmethod
    def _validate_url(value: str) -> str:
        url = str(value or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("external camera snapshot URL must be HTTPS without embedded credentials")
        if parsed.fragment:
            raise ValueError("external camera snapshot URL cannot contain a fragment")
        # Private/LAN cameras are permitted only because the owner explicitly
        # registers the exact endpoint. We still reject unspecified/multicast/
        # link-local targets and never accept a URL at capture time.
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("external camera hostname could not be resolved") from exc
        for item in addresses:
            host = item[4][0]
            try:
                ip = ipaddress.ip_address(host.split("%", 1)[0])
            except ValueError:
                continue
            if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
                raise ValueError("external camera endpoint resolves to a forbidden network address")
        return url

    @staticmethod
    def _auth_kind(value: str | None) -> str:
        kind = str(value or "none").strip().lower()
        if kind not in {"none", "bearer", "basic"}:
            raise ValueError("external camera auth must be none, bearer, or basic")
        return kind

    def register(
        self,
        *,
        label: str,
        snapshot_url: str,
        auth_kind: str = "none",
        credential: str | None = None,
    ) -> dict:
        name = str(label or "").strip()
        if not name or len(name) > 160:
            raise ValueError("external camera label is required")
        url = self._validate_url(snapshot_url)
        kind = self._auth_kind(auth_kind)
        secret = str(credential or "")
        if kind != "none" and not 1 <= len(secret) <= 4096:
            raise ValueError("external camera credential is required")
        camera_id = f"external:{uuid.uuid4()}"
        if kind != "none":
            self.vault.set(f"sensorium.camera:{camera_id}:credential", secret)
        stamp = time.time()
        try:
            with self._con() as con:
                con.execute(
                    "INSERT INTO external_cameras(id,label,snapshot_url,auth_kind,created_at,updated_at,revoked) VALUES(?,?,?,?,?,?,0)",
                    (camera_id, name, url, kind, stamp, stamp),
                )
        except Exception:
            if kind != "none":
                self.vault.delete(f"sensorium.camera:{camera_id}:credential")
            raise
        self._emit("sensorium.camera.external_registered", camera_id=camera_id, auth_kind=kind)
        return self.get(camera_id)

    def get(self, camera_id: str) -> dict:
        key = str(camera_id or "").strip()
        with self._con() as con:
            row = con.execute(
                "SELECT id,label,snapshot_url,auth_kind,created_at,updated_at,revoked FROM external_cameras WHERE id=?",
                (key,),
            ).fetchone()
        if row is None or row["revoked"]:
            raise KeyError("external camera not found")
        return {
            "camera_id": row["id"],
            "label": row["label"],
            "snapshot_url": row["snapshot_url"],
            "auth_kind": row["auth_kind"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "external": True,
            "native": False,
        }

    def list(self) -> list[dict]:
        with self._con() as con:
            rows = con.execute(
                "SELECT id,label,snapshot_url,auth_kind,created_at,updated_at FROM external_cameras WHERE revoked=0 ORDER BY created_at"
            ).fetchall()
        return [
            {
                "camera_id": row["id"],
                "label": row["label"],
                "snapshot_url": row["snapshot_url"],
                "auth_kind": row["auth_kind"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "external": True,
                "native": False,
            }
            for row in rows
        ]

    def revoke(self, camera_id: str) -> bool:
        key = str(camera_id or "").strip()
        with self._con() as con:
            changed = con.execute(
                "UPDATE external_cameras SET revoked=1,updated_at=? WHERE id=? AND revoked=0",
                (time.time(), key),
            ).rowcount == 1
        if changed:
            self.vault.delete(f"sensorium.camera:{key}:credential")
            self._emit("sensorium.camera.external_revoked", camera_id=key)
        return changed

    def capture(self, camera_id: str) -> dict:
        camera = self.get(camera_id)
        headers = {"Accept": "image/jpeg,image/png,image/webp"}
        credential = self.vault.get(f"sensorium.camera:{camera['camera_id']}:credential")
        auth = None
        if camera["auth_kind"] == "bearer":
            if not credential:
                raise RuntimeError("external camera bearer credential is unavailable")
            headers["Authorization"] = f"Bearer {credential}"
        elif camera["auth_kind"] == "basic":
            if not credential or ":" not in str(credential):
                raise RuntimeError("external camera basic credential is invalid")
            username, password = str(credential).split(":", 1)
            auth = (username, password)
        try:
            response = requests.get(
                camera["snapshot_url"],
                headers=headers,
                auth=auth,
                timeout=self.TIMEOUT_SECONDS,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout as exc:
            raise TimeoutError("external camera snapshot timed out") from exc
        except requests.RequestException as exc:
            raise RuntimeError("external camera snapshot failed") from exc
        try:
            if response.is_redirect or response.is_permanent_redirect:
                raise RuntimeError("external camera redirects are forbidden")
            if response.status_code != 200:
                raise RuntimeError("external camera returned a non-success response")
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise RuntimeError("external camera returned an unsupported frame type")
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > self.MAX_FRAME_BYTES:
                        raise RuntimeError("external camera frame exceeds the size limit")
                except ValueError:
                    pass
            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.MAX_FRAME_BYTES:
                    raise RuntimeError("external camera frame exceeds the size limit")
                chunks.append(chunk)
            raw = b"".join(chunks)
            if not raw:
                raise RuntimeError("external camera returned an empty frame")
        finally:
            response.close()
        self._emit(
            "sensorium.camera.external_captured",
            camera_id=camera["camera_id"],
            frame_bytes=len(raw),
            mime_type=content_type,
        )
        return {
            "camera_id": camera["camera_id"],
            "label": camera["label"],
            "mime_type": content_type,
            "bytes": raw,
            "external": True,
        }
