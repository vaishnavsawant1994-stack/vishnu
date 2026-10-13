from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from .manager import _json, _now


class OpaqueDataRelay:
    """Optional store-and-forward relay for already-encrypted data frames.

    The relay has no data-envelope keys and rejects plaintext-bearing fields. It
    is availability infrastructure only; DeviceRegistry remains trust authority.
    """

    MAX_FRAME_BYTES = 512 * 1024
    MAX_TTL_SECONDS = 15 * 60
    REQUIRED_FRAME_KEYS = {'protocol', 'session_id', 'sequence', 'nonce', 'ciphertext'}
    FORBIDDEN_KEYS = {'plaintext', 'bytes', 'bytes_b64', 'raw', 'raw_bytes', 'file_bytes', 'content'}

    def __init__(self, path: Path, *, device_registry=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.device_registry = device_registry
        with self._con() as con:
            con.executescript(
                '''
                CREATE TABLE IF NOT EXISTS data_relay_frames(
                    frame_id TEXT PRIMARY KEY,
                    sender_device_id TEXT NOT NULL,
                    recipient_device_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    frame_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    acknowledged_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_data_relay_recipient
                    ON data_relay_frames(recipient_device_id,acknowledged_at,expires_at);
                '''
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _active(self, device_id: str):
        if self.device_registry is None:
            return
        if not self.device_registry.is_active(device_id):
            raise PermissionError('trusted active device required')
        if hasattr(self.device_registry, 'authorize') and not self.device_registry.authorize(device_id, 'data:read'):
            raise PermissionError('device is not permitted for data:read')

    @classmethod
    def _validate_frame(cls, frame: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(frame)
        if not cls.REQUIRED_FRAME_KEYS.issubset(value):
            raise ValueError('encrypted relay frame is incomplete')
        if value.get('protocol') != 'vishnu-byte-transfer-v1':
            raise ValueError('unsupported encrypted relay protocol')
        lowered = {str(key).strip().lower().replace('-', '_') for key in value}
        if lowered & cls.FORBIDDEN_KEYS:
            raise PermissionError('relay refuses plaintext-bearing frame fields')
        encoded = _json(value).encode('utf-8')
        if len(encoded) > cls.MAX_FRAME_BYTES:
            raise ValueError('encrypted relay frame exceeds size limit')
        return value

    def put(self, sender_device_id: str, recipient_device_id: str, frame: Mapping[str, Any], *, ttl_seconds: int = 300):
        sender, recipient = str(sender_device_id), str(recipient_device_id)
        self._active(sender); self._active(recipient)
        value = self._validate_frame(frame)
        ttl = max(1, min(int(ttl_seconds), self.MAX_TTL_SECONDS))
        frame_id = secrets.token_urlsafe(24)
        with self._con() as con:
            con.execute('DELETE FROM data_relay_frames WHERE expires_at<=? OR acknowledged_at IS NOT NULL', (time.time(),))
            con.execute(
                '''INSERT INTO data_relay_frames(
                   frame_id,sender_device_id,recipient_device_id,session_id,sequence,frame_json,created_at,expires_at,acknowledged_at
                   ) VALUES(?,?,?,?,?,?,?,?,NULL)''',
                (frame_id, sender, recipient, str(value['session_id']), int(value['sequence']), _json(value), _now(), time.time() + ttl),
            )
        return {'frame_id': frame_id, 'recipient_device_id': recipient, 'expires_in': ttl, 'opaque_ciphertext_only': True}

    def pull(self, recipient_device_id: str, *, limit: int = 50):
        recipient = str(recipient_device_id); self._active(recipient)
        limit = max(1, min(int(limit), 100))
        with self._con() as con:
            con.execute('DELETE FROM data_relay_frames WHERE expires_at<=? OR acknowledged_at IS NOT NULL', (time.time(),))
            rows = con.execute(
                '''SELECT frame_id,sender_device_id,frame_json,created_at,expires_at
                   FROM data_relay_frames WHERE recipient_device_id=? AND acknowledged_at IS NULL
                   ORDER BY created_at,frame_id LIMIT ?''', (recipient, limit),
            ).fetchall()
        return [
            {'frame_id': row['frame_id'], 'sender_device_id': row['sender_device_id'], 'frame': json.loads(row['frame_json']), 'created_at': row['created_at'], 'expires_at': float(row['expires_at'])}
            for row in rows
        ]

    def acknowledge(self, recipient_device_id: str, frame_id: str) -> bool:
        recipient = str(recipient_device_id); self._active(recipient)
        with self._con() as con:
            cur = con.execute(
                '''UPDATE data_relay_frames SET acknowledged_at=?
                   WHERE frame_id=? AND recipient_device_id=? AND acknowledged_at IS NULL AND expires_at>?''',
                (_now(), str(frame_id), recipient, time.time()),
            )
        return cur.rowcount == 1

    def diagnostics(self):
        with self._con() as con:
            pending = int(con.execute('SELECT COUNT(*) FROM data_relay_frames WHERE acknowledged_at IS NULL AND expires_at>?', (time.time(),)).fetchone()[0])
        return {'pending_frames': pending, 'max_frame_bytes': self.MAX_FRAME_BYTES, 'max_ttl_seconds': self.MAX_TTL_SECONDS, 'stores_plaintext': False}
