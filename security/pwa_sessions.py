from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class PwaSession:
    id: str
    device_id: str
    created_at: float
    last_seen_at: float
    expires_at: float
    reauthenticated_at: float | None
    kind: str = "browser"
    scopes: tuple[str, ...] = ()


class PwaSessionStore:
    """Shared durable authority for browser sessions and scoped native sessions."""

    NATIVE_TTL_SECONDS = 8 * 60 * 60
    NATIVE_CODE_TTL_SECONDS = 90
    NATIVE_SCOPES = frozenset({"device:read", "device:admin"})

    def __init__(self, path: Path, *, ttl_seconds: int = 60 * 60 * 24 * 30,
                 native_client_redirects: dict[str, tuple[str, ...] | list[str]] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(300, min(int(ttl_seconds), 60 * 60 * 24 * 365))
        self.native_client_redirects = {
            str(client): frozenset(str(uri) for uri in uris)
            for client, uris in (native_client_redirects or {}).items()
        }
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS pwa_sessions (
                id TEXT PRIMARY KEY, device_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL, last_seen_at REAL NOT NULL, expires_at REAL NOT NULL,
                reauthenticated_at REAL, revoked_at REAL
            )""")
            self._ensure_column(con, "pwa_sessions", "session_kind", "TEXT NOT NULL DEFAULT 'browser'")
            self._ensure_column(con, "pwa_sessions", "scopes_json", "TEXT NOT NULL DEFAULT '[]'")
            con.execute("CREATE INDEX IF NOT EXISTS idx_pwa_sessions_device ON pwa_sessions(device_id,revoked_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_pwa_sessions_kind ON pwa_sessions(session_kind,expires_at)")
            con.execute("""CREATE TABLE IF NOT EXISTS native_authorization_codes (
                code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, redirect_uri TEXT NOT NULL,
                challenge TEXT NOT NULL, browser_session_id TEXT NOT NULL, device_id TEXT NOT NULL,
                scopes_json TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                consumed_at REAL
            )""")

    @staticmethod
    def _ensure_column(con, table: str, name: str, definition: str) -> None:
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(str(token).encode()).hexdigest()

    @staticmethod
    def _row(row) -> PwaSession:
        keys = set(row.keys())
        kind = row["session_kind"] if "session_kind" in keys else "browser"
        scopes = tuple(json.loads(row["scopes_json"] or "[]")) if "scopes_json" in keys else ()
        stamp = row["reauthenticated_at"]
        return PwaSession(row["id"], row["device_id"], float(row["created_at"]),
                          float(row["last_seen_at"]), float(row["expires_at"]),
                          float(stamp) if stamp is not None else None, kind, scopes)

    def _invalidate_connector_session(self, session_id):
        try:
            from integrations.state import invalidate_session_transactions
            invalidate_session_transactions(self.path.parent / "connectors.sqlite3", str(session_id))
        except Exception:
            pass

    def issue(self, device_id, *, reauthenticated=True):
        now = time.time()
        token = secrets.token_urlsafe(32)
        sid = str(uuid.uuid4())
        reauth = now if reauthenticated else None
        expires = now + self.ttl_seconds
        with self._con() as con:
            con.execute("""INSERT INTO pwa_sessions
                (id,device_id,token_hash,created_at,last_seen_at,expires_at,reauthenticated_at,revoked_at,session_kind,scopes_json)
                VALUES(?,?,?,?,?,?,?,NULL,'browser','[]')""",
                (sid, str(device_id), self._hash(token), now, now, expires, reauth))
        return token, PwaSession(sid, str(device_id), now, now, expires, reauth)

    def authenticate(self, token, device_id, *, touch=True):
        if not token or not device_id:
            return None
        return self._authenticate(token, device_id=str(device_id), kind="browser", touch=touch)

    def authenticate_native(self, token, *, touch=True):
        if not token:
            return None
        return self._authenticate(token, kind="native", touch=touch)

    def _authenticate(self, token, *, kind, device_id=None, touch=True):
        now = time.time()
        query = "SELECT * FROM pwa_sessions WHERE token_hash=? AND session_kind=? AND revoked_at IS NULL AND expires_at>=?"
        args: tuple = (self._hash(token), kind, now)
        if device_id is not None:
            query += " AND device_id=?"
            args += (device_id,)
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(query, args).fetchone()
            if row is None:
                con.commit()
                return None
            if touch:
                con.execute("UPDATE pwa_sessions SET last_seen_at=? WHERE id=? AND revoked_at IS NULL", (now, row["id"]))
                result = dict(row)
                result["last_seen_at"] = now
                con.commit()
                return self._row(result)
            con.commit()
            return self._row(row)

    def create_native_authorization_code(self, *, browser_session_id: str, device_id: str,
                                         client_id: str, redirect_uri: str, challenge: str,
                                         scopes: list[str], now: float | None = None) -> str:
        if client_id not in self.native_client_redirects or redirect_uri not in self.native_client_redirects[client_id]:
            raise ValueError("native client or redirect URI is not registered")
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("native redirect URI must be an allowlisted HTTPS link")
        if not isinstance(challenge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", challenge):
            raise ValueError("PKCE S256 challenge is invalid")
        granted = sorted(set(scopes)) if isinstance(scopes, list) else []
        if not granted or set(granted) - self.NATIVE_SCOPES:
            raise ValueError("requested native scopes are not allowed")
        stamp = time.time() if now is None else float(now)
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            browser = con.execute("""SELECT id FROM pwa_sessions WHERE id=? AND device_id=?
                AND session_kind='browser' AND revoked_at IS NULL AND expires_at>=?
                AND reauthenticated_at IS NOT NULL AND reauthenticated_at>=?""",
                (browser_session_id, device_id, stamp, stamp - 300)).fetchone()
            if browser is None:
                con.rollback()
                raise PermissionError("recent authenticated owner browser session required")
            code = secrets.token_urlsafe(32)
            con.execute("""INSERT INTO native_authorization_codes
                (code_hash,client_id,redirect_uri,challenge,browser_session_id,device_id,scopes_json,created_at,expires_at,consumed_at)
                VALUES(?,?,?,?,?,?,?,?,?,NULL)""",
                (self._hash(code), client_id, redirect_uri, challenge, browser_session_id,
                 device_id, json.dumps(granted), stamp, stamp + self.NATIVE_CODE_TTL_SECONDS))
            con.commit()
        return code

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        import base64
        return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    def exchange_native_authorization_code(self, *, code: str, verifier: str,
                                          client_id: str, redirect_uri: str,
                                          now: float | None = None) -> tuple[str, PwaSession]:
        if not isinstance(code, str) or not code or len(code) > 256:
            raise PermissionError("native authorization code is invalid")
        if not isinstance(verifier, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
            raise PermissionError("PKCE verifier is invalid")
        stamp = time.time() if now is None else float(now)
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            auth = con.execute("SELECT * FROM native_authorization_codes WHERE code_hash=?", (self._hash(code),)).fetchone()
            if auth is None or auth["consumed_at"] is not None or auth["expires_at"] < stamp:
                con.rollback()
                raise PermissionError("native authorization code is expired or already used")
            if auth["client_id"] != client_id or auth["redirect_uri"] != redirect_uri:
                con.rollback()
                raise PermissionError("native authorization code binding does not match")
            expected = self._pkce_challenge(verifier)
            if not hmac.compare_digest(auth["challenge"], expected):
                con.rollback()
                raise PermissionError("PKCE verification failed")
            browser = con.execute("""SELECT id FROM pwa_sessions WHERE id=? AND device_id=?
                AND session_kind='browser' AND revoked_at IS NULL AND expires_at>=?""",
                (auth["browser_session_id"], auth["device_id"], stamp)).fetchone()
            if browser is None:
                con.rollback()
                raise PermissionError("authorizing owner session is no longer active")
            consumed = con.execute("UPDATE native_authorization_codes SET consumed_at=? WHERE code_hash=? AND consumed_at IS NULL AND expires_at>=?",
                                   (stamp, auth["code_hash"], stamp))
            if consumed.rowcount != 1:
                con.rollback()
                raise PermissionError("native authorization code is expired or already used")
            token = secrets.token_urlsafe(48)
            session_id = str(uuid.uuid4())
            expires = stamp + self.NATIVE_TTL_SECONDS
            scopes = tuple(json.loads(auth["scopes_json"]))
            con.execute("""INSERT INTO pwa_sessions
                (id,device_id,token_hash,created_at,last_seen_at,expires_at,reauthenticated_at,revoked_at,session_kind,scopes_json)
                VALUES(?,?,?,?,?,?,?,NULL,'native',?)""",
                (session_id, auth["device_id"], self._hash(token), stamp, stamp, expires,
                 stamp, json.dumps(scopes)))
            con.commit()
        session = PwaSession(session_id, auth["device_id"], stamp, stamp, expires, stamp, "native", scopes)
        return token, session

    def get(self, session_id):
        with self._con() as con:
            row = con.execute("SELECT * FROM pwa_sessions WHERE id=? AND revoked_at IS NULL AND expires_at>=?", (str(session_id), time.time())).fetchone()
        return self._row(row) if row else None

    def mark_reauthenticated(self, session_id, *, at=None):
        stamp = time.time() if at is None else float(at)
        with self._con() as con:
            cur = con.execute("UPDATE pwa_sessions SET reauthenticated_at=? WHERE id=? AND revoked_at IS NULL AND expires_at>=?", (stamp, str(session_id), time.time()))
        return cur.rowcount == 1

    def rotate_native(self, session_id: str):
        stamp = time.time()
        token = secrets.token_urlsafe(48)
        new_id = str(uuid.uuid4())
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute("""SELECT * FROM pwa_sessions WHERE id=? AND session_kind='native'
                AND revoked_at IS NULL AND expires_at>=?""", (str(session_id), stamp)).fetchone()
            if old is None:
                con.rollback()
                raise PermissionError("native session is expired or revoked")
            revoked = con.execute("UPDATE pwa_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (stamp, str(session_id)))
            if revoked.rowcount != 1:
                con.rollback()
                raise PermissionError("native session is expired or revoked")
            expires = stamp + self.NATIVE_TTL_SECONDS
            con.execute("""INSERT INTO pwa_sessions
                (id,device_id,token_hash,created_at,last_seen_at,expires_at,reauthenticated_at,revoked_at,session_kind,scopes_json)
                VALUES(?,?,?,?,?,?,?,NULL,'native',?)""",
                (new_id, old["device_id"], self._hash(token), stamp, stamp, expires,
                 old["reauthenticated_at"], old["scopes_json"]))
            con.commit()
        return token, PwaSession(new_id, old["device_id"], stamp, stamp, expires,
                                  old["reauthenticated_at"], "native", tuple(json.loads(old["scopes_json"])))

    def revoke(self, session_id):
        with self._con() as con:
            cur = con.execute("UPDATE pwa_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (time.time(), str(session_id)))
        if cur.rowcount:
            self._invalidate_connector_session(session_id)
        return cur.rowcount == 1

    def revoke_token(self, token):
        if not token:
            return False
        with self._con() as con:
            row = con.execute("SELECT id FROM pwa_sessions WHERE token_hash=? AND revoked_at IS NULL", (self._hash(token),)).fetchone()
            cur = con.execute("UPDATE pwa_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (time.time(), self._hash(token)))
        if row:
            self._invalidate_connector_session(row["id"])
        return cur.rowcount == 1

    def revoke_device(self, device_id):
        with self._con() as con:
            rows = con.execute("SELECT id FROM pwa_sessions WHERE device_id=? AND revoked_at IS NULL", (str(device_id),)).fetchall()
            cur = con.execute("UPDATE pwa_sessions SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL", (time.time(), str(device_id)))
        for row in rows:
            self._invalidate_connector_session(row["id"])
        return int(cur.rowcount)

    def revoke_all(self):
        with self._con() as con:
            rows = con.execute("SELECT id FROM pwa_sessions WHERE revoked_at IS NULL").fetchall()
            cur = con.execute("UPDATE pwa_sessions SET revoked_at=? WHERE revoked_at IS NULL", (time.time(),))
        for row in rows:
            self._invalidate_connector_session(row["id"])
        return int(cur.rowcount)

    def active_for_device(self, device_id):
        with self._con() as con:
            rows = con.execute("SELECT * FROM pwa_sessions WHERE device_id=? AND revoked_at IS NULL AND expires_at>=? ORDER BY created_at", (str(device_id), time.time())).fetchall()
        return [self._row(row) for row in rows]

    def purge_expired(self):
        with self._con() as con:
            con.execute("DELETE FROM native_authorization_codes WHERE expires_at<? OR consumed_at IS NOT NULL", (time.time(),))
            cur = con.execute("DELETE FROM pwa_sessions WHERE expires_at<?", (time.time(),))
        return int(cur.rowcount)
