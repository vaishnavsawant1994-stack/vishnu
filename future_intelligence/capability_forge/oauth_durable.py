from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from .oauth_lifecycle import CapabilityOAuthLifecycle


class DurableCapabilityOAuthLifecycle(CapabilityOAuthLifecycle):
    """Adds durable state->capability routing for the single V3 OAuth callback."""

    def __init__(self, *args, path: str | Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS forge_oauth_pending(
                    state TEXT PRIMARY KEY,
                    capability_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    device_id TEXT,
                    session_id TEXT,
                    security_epoch INTEGER,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def begin(self, capability_id: str, provider_id: str, **kwargs):
        configured = str(os.getenv("VISHNU_CAPABILITY_OAUTH_REDIRECT_URI") or "").strip()
        requested = str(kwargs.get("redirect_uri") or "").strip()
        if not configured:
            raise PermissionError("Capability OAuth callback URI is not configured")
        if requested and requested != configured:
            raise PermissionError("Capability OAuth redirect must match the configured V3 callback")
        kwargs["redirect_uri"] = configured
        result = super().begin(capability_id, provider_id, **kwargs)
        now = time.time()
        expires = now + max(60, min(int(result.get("expires_in") or 600), 1800))
        with self._con() as con:
            con.execute("DELETE FROM forge_oauth_pending WHERE expires_at<=?", (now,))
            con.execute(
                """INSERT OR REPLACE INTO forge_oauth_pending(
                    state,capability_id,provider_id,owner_id,device_id,session_id,security_epoch,expires_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(result["state"]), str(capability_id), str(provider_id),
                    str(kwargs.get("owner_id") or "owner"), kwargs.get("device_id"), kwargs.get("session_id"),
                    kwargs.get("security_epoch"), expires, now,
                ),
            )
        return result

    def pending(self, state: str):
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_oauth_pending WHERE state=?", (str(state),)).fetchone()
        if row is None:
            return None
        item = dict(row)
        if float(item["expires_at"]) <= time.time():
            self.discard(state)
            return None
        return item

    def discard(self, state: str) -> None:
        with self._con() as con:
            con.execute("DELETE FROM forge_oauth_pending WHERE state=?", (str(state),))

    def complete_state(self, *, state: str, code: str):
        binding = self.pending(state)
        if binding is None:
            raise PermissionError("capability OAuth callback state is unavailable or expired")
        try:
            result = super().complete(
                binding["capability_id"],
                binding["provider_id"],
                state=str(state),
                code=str(code),
                owner_id=binding["owner_id"],
                device_id=binding.get("device_id"),
                session_id=binding.get("session_id"),
                security_epoch=binding.get("security_epoch"),
            )
        except Exception:
            # OAuthAccountManager owns replay/expiry semantics. Keep the routing
            # row only if its state still exists there; a later cleanup removes it.
            raise
        self.discard(state)
        return result
