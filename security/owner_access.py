from __future__ import annotations

import base64
import secrets
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.security import hash_secret, verify_secret


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


class FirstRunClaimBusy(RuntimeError):
    """Another device currently owns the short-lived setup ceremony."""


class OwnerAccessStore:
    """Durable owner login methods without storing reusable plaintext secrets."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS owner_password(
                id INTEGER PRIMARY KEY CHECK(id=1),salt TEXT NOT NULL,password_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL)''')
            con.execute('''CREATE TABLE IF NOT EXISTS recovery_codes(
                id TEXT PRIMARY KEY,salt TEXT NOT NULL,code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,used_at TEXT)''')
            con.execute('''CREATE TABLE IF NOT EXISTS passkeys(
                credential_id BLOB PRIMARY KEY,public_key BLOB NOT NULL,sign_count INTEGER NOT NULL,
                name TEXT NOT NULL,transports TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
                last_used_at TEXT)''')
            con.execute('''CREATE TABLE IF NOT EXISTS auth_challenges(
                id TEXT PRIMARY KEY,kind TEXT NOT NULL,challenge BLOB NOT NULL,device_id TEXT,
                rp_id TEXT NOT NULL,origin TEXT NOT NULL,expires_at INTEGER NOT NULL)''')
            # Owner identity is installation independent metadata owned by the
            # same canonical security store as passkeys, passwords and recovery.
            # It intentionally contains no device credentials or provider IDs.
            con.execute('''CREATE TABLE IF NOT EXISTS owner_identity(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                owner_id TEXT NOT NULL UNIQUE,
                vishnu_id TEXT NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                identity_version INTEGER NOT NULL DEFAULT 1)''')
            con.execute('''CREATE TABLE IF NOT EXISTS first_run_claim(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                salt TEXT NOT NULL,
                claim_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL)''')

    def _con(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def identity(self) -> dict | None:
        """Return the stable owner/Vishnu identity, without device secrets."""
        with self._con() as con:
            row = con.execute(
                '''SELECT owner_id,vishnu_id,first_name,last_name,display_name,
                          created_at,identity_version
                   FROM owner_identity WHERE singleton=1'''
            ).fetchone()
        return dict(row) if row else None

    def restore_identity_metadata(self, identity: dict) -> dict:
        """Restore stable identity labels without restoring any security authority.

        Backups may carry these non-secret identifiers so a data restore can
        continue the same Vishnu. Passwords, recovery hashes, passkeys, claims,
        sessions, and device credentials remain local and are never imported.
        """
        required = ('owner_id', 'vishnu_id', 'first_name', 'last_name', 'display_name',
                    'created_at', 'identity_version')
        if not isinstance(identity, dict) or any(key not in identity for key in required):
            raise ValueError('Backup identity metadata is incomplete')
        owner_id = str(identity['owner_id'])
        vishnu_id = str(identity['vishnu_id'])
        if (not re.fullmatch(r'OWNER-[0-9A-F]{32}', owner_id)
                or not re.fullmatch(r'VISHNU-[0-9A-F]{32}', vishnu_id)):
            raise ValueError('Backup identity metadata is invalid')
        values = (owner_id, vishnu_id, str(identity['first_name'])[:80],
                  str(identity['last_name'])[:80], str(identity['display_name'])[:120],
                  str(identity['created_at'])[:80], int(identity['identity_version']))
        if not values[2] or not values[4] or values[6] < 1:
            raise ValueError('Backup identity metadata is invalid')
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT owner_id,vishnu_id FROM owner_identity WHERE singleton=1').fetchone()
            if row:
                if row['owner_id'] != owner_id or row['vishnu_id'] != vishnu_id:
                    raise ValueError('Backup belongs to a different Vishnu identity')
                return self.identity()
            con.execute(
                '''INSERT INTO owner_identity(singleton,owner_id,vishnu_id,first_name,last_name,
                   display_name,created_at,identity_version) VALUES(1,?,?,?,?,?,?,?)''', values,
            )
        return self.identity()

    def acquire_first_run_claim(
        self, presented: str | None = None, *, ttl: int = 900,
        allow_pending_identity: bool = False, allow_proposed: bool = False,
    ) -> tuple[str, bool]:
        """Reserve the uninitialized install for one short-lived setup client.

        Only a hash of the setup claim is persisted. Repeated calls from the
        same browser are retry-safe; a second device cannot race a separate
        first-owner ceremony while the first claim is live.
        """
        now = int(time.time())
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM first_run_claim WHERE singleton=1').fetchone()
            if row is not None and int(row['expires_at']) >= now:
                if presented and verify_secret(str(presented), row['salt'], row['claim_hash']):
                    return str(presented), False
                raise FirstRunClaimBusy('First-device setup is already in progress on another device.')
            if (not allow_pending_identity
                    and con.execute('SELECT 1 FROM owner_identity WHERE singleton=1').fetchone()):
                raise RuntimeError('Vishnu is already initialized. Connect this device instead.')
            if presented and not allow_pending_identity and not allow_proposed:
                raise FirstRunClaimBusy('The setup session expired. Start the creation ceremony again.')
            token = str(presented) if presented and allow_proposed else secrets.token_urlsafe(32)
            salt = secrets.token_hex(16)
            con.execute(
                '''INSERT INTO first_run_claim(singleton,salt,claim_hash,expires_at,created_at)
                   VALUES(1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET
                   salt=excluded.salt,claim_hash=excluded.claim_hash,
                   expires_at=excluded.expires_at,created_at=excluded.created_at''',
                (salt, hash_secret(token, salt), now + max(60, min(int(ttl), 1800)), _now()),
            )
            return token, True

    def release_first_run_claim(self, presented: str) -> bool:
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM first_run_claim WHERE singleton=1').fetchone()
            if row is None or not verify_secret(str(presented or ''), row['salt'], row['claim_hash']):
                return False
            result = con.execute('DELETE FROM first_run_claim WHERE singleton=1')
            return result.rowcount == 1

    def rotate_first_run_claim(self, *, ttl: int = 900) -> str:
        """Issue a new short-lived claim for the already trusted first device.

        The caller must independently authenticate that device and confirm the
        setup is still pending. Rotation lets an interrupted local setup recover
        after its browser claim cookie expires without rerunning owner creation.
        """
        token = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        now = int(time.time())
        with self._con() as con:
            con.execute(
                '''INSERT INTO first_run_claim(singleton,salt,claim_hash,expires_at,created_at)
                   VALUES(1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET
                   salt=excluded.salt,claim_hash=excluded.claim_hash,
                   expires_at=excluded.expires_at,created_at=excluded.created_at''',
                (salt, hash_secret(token, salt), now + max(60, min(int(ttl), 1800)), _now()),
            )
        return token

    def initialize_identity(
        self,
        *,
        first_name: str,
        last_name: str = '',
        display_name: str = '',
    ) -> tuple[dict, bool]:
        """Atomically create the one owner identity or return the existing one.

        The SQLite write lock makes simultaneous first-run attempts converge on
        exactly one identity. Retrying after a crash is safe and never creates
        another owner/Vishnu ID pair.
        """
        first = str(first_name or '').strip()[:80]
        last = str(last_name or '').strip()[:80]
        display = str(display_name or '').strip()[:120] or ' '.join(
            part for part in (first, last) if part
        )
        if not first:
            raise ValueError('First name is required')
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute(
                '''SELECT owner_id,vishnu_id,first_name,last_name,display_name,
                          created_at,identity_version
                   FROM owner_identity WHERE singleton=1'''
            ).fetchone()
            if row is not None:
                return dict(row), False
            identity = {
                'owner_id': f'OWNER-{uuid.uuid4().hex.upper()}',
                'vishnu_id': f'VISHNU-{uuid.uuid4().hex.upper()}',
                'first_name': first,
                'last_name': last,
                'display_name': display or first,
                'created_at': _now(),
                'identity_version': 1,
            }
            con.execute(
                '''INSERT INTO owner_identity(singleton,owner_id,vishnu_id,first_name,last_name,
                       display_name,created_at,identity_version) VALUES(1,?,?,?,?,?,?,?)''',
                (identity['owner_id'], identity['vishnu_id'], identity['first_name'],
                 identity['last_name'], identity['display_name'], identity['created_at'],
                 identity['identity_version']),
            )
            return identity, True

    def password_configured(self) -> bool:
        with self._con() as con:
            return con.execute('SELECT 1 FROM owner_password WHERE id=1').fetchone() is not None

    def set_password(self, password: str):
        if len(password) < 12:
            raise ValueError('Owner password must contain at least 12 characters')
        salt = secrets.token_hex(16)
        with self._con() as con:
            con.execute(
                '''INSERT INTO owner_password(id,salt,password_hash,updated_at) VALUES(1,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET salt=excluded.salt,password_hash=excluded.password_hash,
                   updated_at=excluded.updated_at''',
                (salt, hash_secret(password, salt), _now()),
            )

    def verify_password(self, password: str) -> bool:
        with self._con() as con:
            row = con.execute('SELECT salt,password_hash FROM owner_password WHERE id=1').fetchone()
        return bool(row and verify_secret(password, row['salt'], row['password_hash']))

    def regenerate_recovery_codes(self, count: int = 8) -> list[str]:
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        codes = []
        rows = []
        for _ in range(max(4, min(count, 12))):
            raw = ''.join(secrets.choice(alphabet) for _ in range(12))
            code = '-'.join(raw[index:index + 4] for index in range(0, 12, 4))
            salt = secrets.token_hex(16)
            codes.append(code)
            rows.append((str(uuid.uuid4()), salt, hash_secret(code, salt), _now()))
        with self._con() as con:
            con.execute('DELETE FROM recovery_codes')
            con.executemany(
                'INSERT INTO recovery_codes(id,salt,code_hash,created_at,used_at) VALUES(?,?,?,?,NULL)',
                rows,
            )
        return codes

    def recovery_codes_remaining(self) -> int:
        with self._con() as con:
            row = con.execute('SELECT COUNT(*) AS count FROM recovery_codes WHERE used_at IS NULL').fetchone()
        return int(row['count'])

    def consume_recovery_code(self, code: str) -> bool:
        candidate = str(code or '').strip().upper()
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            rows = con.execute('SELECT id,salt,code_hash FROM recovery_codes WHERE used_at IS NULL').fetchall()
            for row in rows:
                if verify_secret(candidate, row['salt'], row['code_hash']):
                    consumed = con.execute(
                        'UPDATE recovery_codes SET used_at=? WHERE id=? AND used_at IS NULL',
                        (_now(), row['id']),
                    )
                    return consumed.rowcount == 1
        return False

    def save_passkey(self, credential_id: bytes, public_key: bytes, sign_count: int, name: str, transports=''):
        with self._con() as con:
            con.execute(
                '''INSERT INTO passkeys(credential_id,public_key,sign_count,name,transports,created_at,last_used_at)
                   VALUES(?,?,?,?,?,?,NULL)
                   ON CONFLICT(credential_id) DO UPDATE SET public_key=excluded.public_key,
                   sign_count=excluded.sign_count,name=excluded.name,transports=excluded.transports''',
                (credential_id, public_key, int(sign_count), str(name or 'Owner passkey')[:120], str(transports), _now()),
            )

    def passkeys(self) -> list[dict]:
        with self._con() as con:
            rows = con.execute(
                'SELECT credential_id,name,transports,created_at,last_used_at FROM passkeys ORDER BY created_at'
            ).fetchall()
        return [
            {
                'credential_id': _encode(bytes(row['credential_id'])),
                'name': row['name'],
                'transports': row['transports'],
                'created_at': row['created_at'],
                'last_used_at': row['last_used_at'],
            }
            for row in rows
        ]

    def passkey(self, credential_id: bytes):
        with self._con() as con:
            row = con.execute('SELECT * FROM passkeys WHERE credential_id=?', (credential_id,)).fetchone()
        return dict(row) if row else None

    def use_passkey(self, credential_id: bytes, sign_count: int):
        with self._con() as con:
            con.execute(
                'UPDATE passkeys SET sign_count=?,last_used_at=? WHERE credential_id=?',
                (int(sign_count), _now(), credential_id),
            )

    def create_challenge(self, kind: str, challenge: bytes, rp_id: str, origin: str, *, device_id=None, ttl=180):
        challenge_id = str(uuid.uuid4())
        expires_at = int(datetime.now(timezone.utc).timestamp()) + max(30, min(int(ttl), 300))
        with self._con() as con:
            con.execute('DELETE FROM auth_challenges WHERE expires_at<?', (int(datetime.now(timezone.utc).timestamp()),))
            con.execute(
                'INSERT INTO auth_challenges VALUES(?,?,?,?,?,?,?)',
                (challenge_id, kind, challenge, device_id, rp_id, origin, expires_at),
            )
        return challenge_id

    def consume_challenge(self, challenge_id: str, kind: str, *, device_id=None):
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM auth_challenges WHERE id=?', (challenge_id,)).fetchone()
            if row is None:
                return None
            consumed = con.execute('DELETE FROM auth_challenges WHERE id=?', (challenge_id,))
            if consumed.rowcount != 1:
                return None
        if row['kind'] != kind:
            return None
        if int(row['expires_at']) < int(datetime.now(timezone.utc).timestamp()):
            return None
        if row['device_id'] is not None and row['device_id'] != device_id:
            return None
        return dict(row)
