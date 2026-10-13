from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from devices.gateway import DeviceCommand
from .envelopes import EnvelopeKeyManager, _b64, _unb64
from .manager import _json, _now


class LeaseBoundByteTransport:
    """Bounded raw-byte transport that cannot bypass the canonical data lease."""

    MAX_CHUNK_SIZE = 256 * 1024
    DEFAULT_CHUNK_SIZE = 64 * 1024
    MAX_TRANSFER_BYTES = 8 * 1024 * 1024 * 1024

    def __init__(self, data_plane, envelopes: EnvelopeKeyManager, gateway=None, events=None):
        self.data_plane = data_plane
        self.envelopes = envelopes
        self.gateway = gateway or getattr(data_plane, "device_gateway", None)
        self.events = events or getattr(data_plane, "events", None)
        self._init_schema()

    def _init_schema(self):
        with self.data_plane._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_plane_transfer_sessions(
                    session_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    global_id TEXT NOT NULL,
                    requester_device_id TEXT NOT NULL,
                    source_device_id TEXT NOT NULL,
                    object_version INTEGER NOT NULL,
                    key_epoch INTEGER NOT NULL,
                    wrapped_key TEXT NOT NULL,
                    wrap_nonce TEXT NOT NULL,
                    chunk_size INTEGER NOT NULL,
                    next_sequence INTEGER NOT NULL DEFAULT 0,
                    bytes_transferred INTEGER NOT NULL DEFAULT 0,
                    expected_size INTEGER,
                    expected_digest TEXT,
                    expires_at REAL NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_data_plane_transfer_item
                    ON data_plane_transfer_sessions(global_id,state);
                """
            )

    def _emit(self, topic: str, **payload):
        if self.events is not None:
            try:
                self.events.emit(topic, **payload)
            except Exception:
                pass

    def open_transfer(
        self,
        global_id: str,
        *,
        requester_device_id: str,
        object_version: int | None = None,
        expected_size: int | None = None,
        expected_digest: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        ttl_seconds: int = 120,
    ) -> dict[str, Any]:
        item = self.data_plane.item(str(global_id))
        if item["tombstone"]:
            raise KeyError("data item is deleted")
        version = int(object_version or item["version"])
        if version < 1:
            raise ValueError("object_version must be positive")
        chunk_size = int(chunk_size)
        if chunk_size < 1024 or chunk_size > self.MAX_CHUNK_SIZE:
            raise ValueError("chunk_size is outside the bounded transfer range")
        if expected_size is not None:
            expected_size = int(expected_size)
            if expected_size < 0 or expected_size > self.MAX_TRANSFER_BYTES:
                raise ValueError("expected_size is outside the bounded transfer range")
        if expected_digest is not None:
            expected_digest = str(expected_digest).lower()
            if len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
                raise ValueError("expected_digest must be a sha256 hex digest")

        lease = self.data_plane.grant_remote_access(
            str(global_id), requester_device_id=str(requester_device_id), purpose="raw_view",
            allow_persist=False, ttl_seconds=max(1, min(int(ttl_seconds), 300)),
        )
        if lease.get("persist_allowed"):
            raise PermissionError("remote-view transfer unexpectedly allows persistence")

        session_id = secrets.token_urlsafe(24)
        transfer_key = secrets.token_bytes(32)
        wrapped = self.envelopes.wrap_key(f"transfer:{session_id}", version, transfer_key)
        with self.data_plane._con() as con:
            con.execute(
                """INSERT INTO data_plane_transfer_sessions(
                   session_id,lease_id,global_id,requester_device_id,source_device_id,object_version,
                   key_epoch,wrapped_key,wrap_nonce,chunk_size,next_sequence,bytes_transferred,
                   expected_size,expected_digest,expires_at,state,created_at,completed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?,?,NULL)""",
                (
                    session_id, lease["lease_id"], str(global_id), str(requester_device_id),
                    str(lease["source_device_id"]), version, int(wrapped["key_epoch"]),
                    wrapped["wrapped_key"], wrapped["wrap_nonce"], chunk_size, expected_size,
                    expected_digest, float(lease["expires_at"]), "open", _now(),
                ),
            )
        self._emit("data_plane.transfer_opened", session_id=session_id, global_id=str(global_id),
                   source_device_id=str(lease["source_device_id"]), requester_device_id=str(requester_device_id))
        return {
            "session_id": session_id, "lease_id": lease["lease_id"], "global_id": str(global_id),
            "object_version": version, "source_device_id": str(lease["source_device_id"]),
            "requester_device_id": str(requester_device_id), "chunk_size": chunk_size,
            "expires_at": float(lease["expires_at"]), "cache_policy": "no_store",
            "index_allowed": False, "backup_allowed": False, "persist_allowed": False,
            "algorithm": "AES-256-GCM",
        }

    def _row(self, session_id: str):
        with self.data_plane._con() as con:
            row = con.execute("SELECT * FROM data_plane_transfer_sessions WHERE session_id=?", (str(session_id),)).fetchone()
        if row is None:
            raise KeyError("byte-transfer session not found")
        if row["state"] != "open":
            raise RuntimeError(f"byte-transfer session is {row['state']}")
        if float(row["expires_at"]) <= time.time():
            self.abort(session_id, reason="expired")
            raise PermissionError("byte-transfer session expired")
        lease = self.data_plane.validate_remote_lease(str(row["lease_id"]), require_persist=False)
        if lease["global_id"] != row["global_id"]:
            raise PermissionError("transfer lease no longer matches data item")
        if lease["requester_device_id"] != row["requester_device_id"]:
            raise PermissionError("transfer requester no longer matches lease")
        return row

    @staticmethod
    def _chunk_aad(row, sequence: int, eof: bool) -> bytes:
        return _json({
            "protocol": "vishnu-byte-transfer-v1", "session_id": row["session_id"],
            "global_id": row["global_id"], "object_version": int(row["object_version"]),
            "sequence": int(sequence), "offset": int(row["bytes_transferred"]), "eof": bool(eof),
        }).encode("utf-8")

    def _session_key(self, row) -> bytes:
        return self.envelopes.unwrap_key(
            f"transfer:{row['session_id']}", int(row["object_version"]),
            {"key_epoch": int(row["key_epoch"]), "wrapped_key": row["wrapped_key"], "wrap_nonce": row["wrap_nonce"]},
        )

    def encrypt_chunk(self, session_id: str, sequence: int, plaintext: bytes, *, eof: bool = False) -> dict[str, Any]:
        row = self._row(session_id)
        sequence = int(sequence)
        if sequence != int(row["next_sequence"]):
            raise ValueError("unexpected transfer sequence")
        data = bytes(plaintext)
        if len(data) > int(row["chunk_size"]):
            raise ValueError("chunk exceeds negotiated transfer size")
        projected = int(row["bytes_transferred"]) + len(data)
        if projected > self.MAX_TRANSFER_BYTES:
            raise ValueError("transfer exceeds global byte limit")
        if row["expected_size"] is not None and projected > int(row["expected_size"]):
            raise ValueError("transfer exceeds expected object size")
        if eof and row["expected_size"] is not None and projected != int(row["expected_size"]):
            raise ValueError("final transfer size does not match expected object size")

        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._session_key(row)).encrypt(nonce, data, self._chunk_aad(row, sequence, bool(eof)))
        digest = hashlib.sha256(data).hexdigest()
        state = "complete" if eof else "open"
        with self.data_plane._con() as con:
            updated = con.execute(
                """UPDATE data_plane_transfer_sessions SET next_sequence=?,bytes_transferred=?,state=?,completed_at=?
                   WHERE session_id=? AND state='open' AND next_sequence=?""",
                (sequence + 1, projected, state, _now() if eof else None, str(session_id), sequence),
            )
            if updated.rowcount != 1:
                raise RuntimeError("transfer sequence changed concurrently")
        frame = {
            "protocol": "vishnu-byte-transfer-v1", "session_id": str(session_id),
            "global_id": row["global_id"], "object_version": int(row["object_version"]),
            "sequence": sequence, "offset": int(row["bytes_transferred"]), "plaintext_size": len(data),
            "chunk_digest": digest, "nonce": _b64(nonce), "ciphertext": _b64(ciphertext),
            "eof": bool(eof), "cache_policy": "no_store",
        }
        self._emit("data_plane.transfer_chunk", session_id=str(session_id), global_id=row["global_id"],
                   sequence=sequence, plaintext_size=len(data), eof=bool(eof))
        return frame

    def decrypt_chunk(self, frame: Mapping[str, Any]) -> bytes:
        session_id = str(frame.get("session_id") or "")
        with self.data_plane._con() as con:
            row = con.execute("SELECT * FROM data_plane_transfer_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError("byte-transfer session not found")
        aad = _json({
            "protocol": "vishnu-byte-transfer-v1", "session_id": session_id,
            "global_id": row["global_id"], "object_version": int(row["object_version"]),
            "sequence": int(frame["sequence"]), "offset": int(frame["offset"]), "eof": bool(frame.get("eof")),
        }).encode("utf-8")
        try:
            plaintext = AESGCM(self._session_key(row)).decrypt(_unb64(frame["nonce"]), _unb64(frame["ciphertext"]), aad)
        except InvalidTag as exc:
            raise ValueError("transfer chunk authentication failed") from exc
        if len(plaintext) != int(frame["plaintext_size"]):
            raise ValueError("transfer chunk size verification failed")
        if not secrets.compare_digest(hashlib.sha256(plaintext).hexdigest(), str(frame["chunk_digest"])):
            raise ValueError("transfer chunk digest verification failed")
        return plaintext

    async def request_remote_chunk(self, session_id: str) -> dict[str, Any]:
        row = self._row(session_id)
        if self.gateway is None:
            raise RuntimeError("canonical DeviceGateway is required for remote byte access")
        command = DeviceCommand(
            "data_plane_byte_read",
            {"session_id": str(session_id), "lease_id": row["lease_id"], "global_id": row["global_id"],
             "object_version": int(row["object_version"]), "offset": int(row["bytes_transferred"]),
             "length": int(row["chunk_size"])}, str(uuid.uuid4()),
        )
        response = await self.gateway.request(str(row["source_device_id"]), command, timeout=20)
        if not bool(response.get("ok")):
            raise RuntimeError(str(response.get("error") or "source device rejected byte read"))
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("source device returned malformed byte result")
        try:
            raw = base64.b64decode(str(result.get("bytes_b64") or ""), validate=True)
        except Exception as exc:
            raise RuntimeError("source device returned invalid byte encoding") from exc
        if len(raw) > int(row["chunk_size"]):
            raise RuntimeError("source device exceeded negotiated chunk size")
        return self.encrypt_chunk(str(session_id), int(row["next_sequence"]), raw, eof=bool(result.get("eof")))

    def abort(self, session_id: str, *, reason: str = "aborted") -> bool:
        with self.data_plane._con() as con:
            row = con.execute("SELECT lease_id FROM data_plane_transfer_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if row is None:
                return False
            con.execute("UPDATE data_plane_transfer_sessions SET state='aborted',completed_at=? WHERE session_id=? AND state='open'", (_now(), str(session_id)))
            con.execute("UPDATE data_plane_remote_leases SET revoked_at=? WHERE lease_id=? AND revoked_at IS NULL", (time.time(), row["lease_id"]))
        self._emit("data_plane.transfer_aborted", session_id=str(session_id), reason=str(reason)[:120])
        return True

    def status(self, session_id: str) -> dict[str, Any]:
        with self.data_plane._con() as con:
            row = con.execute("SELECT * FROM data_plane_transfer_sessions WHERE session_id=?", (str(session_id),)).fetchone()
        if row is None:
            raise KeyError("byte-transfer session not found")
        return {
            "session_id": row["session_id"], "lease_id": row["lease_id"], "global_id": row["global_id"],
            "requester_device_id": row["requester_device_id"], "source_device_id": row["source_device_id"],
            "object_version": int(row["object_version"]), "chunk_size": int(row["chunk_size"]),
            "next_sequence": int(row["next_sequence"]), "bytes_transferred": int(row["bytes_transferred"]),
            "expected_size": row["expected_size"], "expires_at": float(row["expires_at"]), "state": row["state"],
            "cache_policy": "no_store", "index_allowed": False, "backup_allowed": False,
            "raw_session_key_exposed": False,
        }
