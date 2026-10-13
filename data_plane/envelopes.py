from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .manager import _json, _now

ALGORITHM = "AES-256-GCM"
ENVELOPE_VERSION = 1
_VAULT_PREFIX = "data_plane:kek:"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(str(text), validate=True)
    except Exception as exc:
        raise ValueError("invalid base64 in data envelope") from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class EnvelopeKeyManager:
    """Wrap per-object data keys with KEKs held by Vishnu's canonical vault."""

    def __init__(self, data_plane, vault):
        if vault is None:
            raise RuntimeError("secure data envelopes require Vishnu's canonical secret vault")
        self.data_plane = data_plane
        self.vault = vault
        self._init_schema()

    def _init_schema(self):
        with self.data_plane._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_plane_key_epochs(
                    epoch INTEGER PRIMARY KEY,
                    vault_name TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    retired_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_data_plane_one_active_epoch
                    ON data_plane_key_epochs(active) WHERE active=1;
                CREATE TABLE IF NOT EXISTS data_plane_object_envelopes(
                    global_id TEXT NOT NULL,
                    object_version INTEGER NOT NULL,
                    envelope_version INTEGER NOT NULL,
                    key_epoch INTEGER NOT NULL,
                    algorithm TEXT NOT NULL,
                    wrapped_key TEXT NOT NULL,
                    wrap_nonce TEXT NOT NULL,
                    content_nonce TEXT NOT NULL,
                    plaintext_size INTEGER NOT NULL,
                    ciphertext_size INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    aad_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(global_id,object_version,envelope_version),
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE,
                    FOREIGN KEY(key_epoch) REFERENCES data_plane_key_epochs(epoch)
                );
                """
            )

    @staticmethod
    def _vault_name(epoch: int) -> str:
        return f"{_VAULT_PREFIX}{int(epoch)}"

    def _read_kek(self, epoch: int) -> bytes:
        raw = self.vault.get(self._vault_name(epoch))
        if raw is None:
            raise RuntimeError("data-envelope key material is unavailable from the canonical vault")
        key = _unb64(raw)
        if len(key) != 32:
            raise RuntimeError("invalid data-envelope key material")
        return key

    def active_epoch(self) -> int:
        with self.data_plane._lock, self.data_plane._con() as con:
            row = con.execute("SELECT epoch FROM data_plane_key_epochs WHERE active=1").fetchone()
            if row is not None:
                epoch = int(row["epoch"])
                self._read_kek(epoch)
                return epoch
            epoch = int(con.execute("SELECT COALESCE(MAX(epoch),0)+1 FROM data_plane_key_epochs").fetchone()[0])
            name = self._vault_name(epoch)
            if self.vault.get(name) is None:
                self.vault.set(name, _b64(secrets.token_bytes(32)))
            con.execute(
                "INSERT INTO data_plane_key_epochs(epoch,vault_name,active,created_at) VALUES(?,?,1,?)",
                (epoch, name, _now()),
            )
            return epoch

    def rotate_epoch(self) -> int:
        """Rotate the data-plane KEK without rewriting or exposing object plaintext."""
        with self.data_plane._lock, self.data_plane._con() as con:
            current = con.execute("SELECT epoch FROM data_plane_key_epochs WHERE active=1").fetchone()
            epoch = int(con.execute("SELECT COALESCE(MAX(epoch),0)+1 FROM data_plane_key_epochs").fetchone()[0])
            name = self._vault_name(epoch)
            self.vault.set(name, _b64(secrets.token_bytes(32)))
            if current is not None:
                con.execute(
                    "UPDATE data_plane_key_epochs SET active=0,retired_at=? WHERE epoch=?",
                    (_now(), int(current["epoch"])),
                )
            con.execute(
                "INSERT INTO data_plane_key_epochs(epoch,vault_name,active,created_at) VALUES(?,?,1,?)",
                (epoch, name, _now()),
            )
        self.data_plane._emit("data_plane.key_epoch_rotated", key_epoch=epoch)
        return epoch

    @staticmethod
    def _wrap_aad(context: str, version: int, epoch: int) -> bytes:
        return f"vishnu-data-key-v1:{context}:{int(version)}:{int(epoch)}".encode("utf-8")

    def wrap_key(self, context: str, version: int, key: bytes) -> dict[str, Any]:
        if len(key) != 32:
            raise ValueError("data key must be exactly 32 bytes")
        epoch = self.active_epoch()
        nonce = secrets.token_bytes(12)
        wrapped = AESGCM(self._read_kek(epoch)).encrypt(
            nonce, key, self._wrap_aad(str(context), int(version), epoch)
        )
        return {"key_epoch": epoch, "wrapped_key": _b64(wrapped), "wrap_nonce": _b64(nonce)}

    def unwrap_key(self, context: str, version: int, envelope: Mapping[str, Any]) -> bytes:
        epoch = int(envelope["key_epoch"])
        try:
            key = AESGCM(self._read_kek(epoch)).decrypt(
                _unb64(envelope["wrap_nonce"]),
                _unb64(envelope["wrapped_key"]),
                self._wrap_aad(str(context), int(version), epoch),
            )
        except InvalidTag as exc:
            raise ValueError("data-key envelope authentication failed") from exc
        if len(key) != 32:
            raise ValueError("unwrapped data key has invalid length")
        return key

    def encrypt_bytes(
        self,
        global_id: str,
        object_version: int,
        plaintext: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if int(object_version) < 1:
            raise ValueError("object_version must be positive")
        data = bytes(plaintext)
        data_key = secrets.token_bytes(32)
        wrapped = self.wrap_key(str(global_id), int(object_version), data_key)
        aad = {
            "envelope_version": ENVELOPE_VERSION,
            "global_id": str(global_id),
            "object_version": int(object_version),
            "content_type": str(content_type),
        }
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(data_key).encrypt(nonce, data, _json(aad).encode("utf-8"))
        digest = hashlib.sha256(data).hexdigest()
        package = {
            **aad,
            "algorithm": ALGORITHM,
            **wrapped,
            "content_nonce": _b64(nonce),
            "plaintext_size": len(data),
            "ciphertext_size": len(ciphertext),
            "content_digest": digest,
            "ciphertext": _b64(ciphertext),
        }
        with self.data_plane._con() as con:
            con.execute(
                """INSERT INTO data_plane_object_envelopes(
                   global_id,object_version,envelope_version,key_epoch,algorithm,wrapped_key,
                   wrap_nonce,content_nonce,plaintext_size,ciphertext_size,content_digest,aad_json,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(global_id,object_version,envelope_version) DO UPDATE SET
                   key_epoch=excluded.key_epoch,algorithm=excluded.algorithm,wrapped_key=excluded.wrapped_key,
                   wrap_nonce=excluded.wrap_nonce,content_nonce=excluded.content_nonce,
                   plaintext_size=excluded.plaintext_size,ciphertext_size=excluded.ciphertext_size,
                   content_digest=excluded.content_digest,aad_json=excluded.aad_json,created_at=excluded.created_at""",
                (
                    str(global_id), int(object_version), ENVELOPE_VERSION, int(wrapped["key_epoch"]),
                    ALGORITHM, wrapped["wrapped_key"], wrapped["wrap_nonce"], package["content_nonce"],
                    len(data), len(ciphertext), digest, _json(aad), _now(),
                ),
            )
        return package

    def decrypt_bytes(self, package: Mapping[str, Any]) -> bytes:
        if int(package.get("envelope_version") or 0) != ENVELOPE_VERSION:
            raise ValueError("unsupported data-envelope version")
        if str(package.get("algorithm")) != ALGORITHM:
            raise ValueError("unsupported data-envelope algorithm")
        global_id = str(package["global_id"])
        object_version = int(package["object_version"])
        aad = {
            "envelope_version": ENVELOPE_VERSION,
            "global_id": global_id,
            "object_version": object_version,
            "content_type": str(package.get("content_type") or "application/octet-stream"),
        }
        data_key = self.unwrap_key(global_id, object_version, package)
        try:
            plaintext = AESGCM(data_key).decrypt(
                _unb64(package["content_nonce"]),
                _unb64(package["ciphertext"]),
                _json(aad).encode("utf-8"),
            )
        except InvalidTag as exc:
            raise ValueError("encrypted data authentication failed") from exc
        if len(plaintext) != int(package["plaintext_size"]):
            raise ValueError("encrypted data size verification failed")
        if not secrets.compare_digest(hashlib.sha256(plaintext).hexdigest(), str(package["content_digest"])):
            raise ValueError("encrypted data digest verification failed")
        return plaintext

    def rewrap_package(self, package: Mapping[str, Any]) -> dict[str, Any]:
        global_id = str(package["global_id"])
        version = int(package["object_version"])
        data_key = self.unwrap_key(global_id, version, package)
        result = dict(package)
        result.update(self.wrap_key(global_id, version, data_key))
        return result

    def diagnostics(self) -> dict[str, Any]:
        with self.data_plane._con() as con:
            epochs = [
                {"epoch": int(row["epoch"]), "active": bool(row["active"]), "created_at": row["created_at"], "retired_at": row["retired_at"]}
                for row in con.execute("SELECT epoch,active,created_at,retired_at FROM data_plane_key_epochs ORDER BY epoch").fetchall()
            ]
            envelope_count = int(con.execute("SELECT COUNT(*) FROM data_plane_object_envelopes").fetchone()[0])
        return {
            "algorithm": ALGORITHM,
            "envelope_version": ENVELOPE_VERSION,
            "epochs": epochs,
            "object_envelopes": envelope_count,
            "raw_keys_in_database": False,
        }
