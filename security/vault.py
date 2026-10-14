from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path
from threading import RLock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .keychain import KeychainUnavailable, RootKeyStore


class SecretVault:
    VERSION = 2
    ROTATION_JOURNAL_VERSION = 1

    def __init__(
        self,
        path: Path,
        password: str | None = None,
        root_key_store: RootKeyStore | None = None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._data = {}
        self._salt = b""
        self._password = password.encode() if password else None
        self._root_key_rotation: str | None = None
        self.root_key_store = root_key_store or RootKeyStore()
        self._rotation_path = self.path.with_suffix(self.path.suffix + ".rotation")
        if self.path.exists():
            self._load()
        else:
            self._salt = secrets.token_bytes(16)
            self._save()

    def _master(self) -> bytes:
        if self._password:
            return Scrypt(salt=self._salt, length=32, n=2**14, r=8, p=1).derive(
                self._password
            )
        return self.root_key_store.get_or_create()

    def _read_rotation_journal(self) -> str | None:
        if not self._rotation_path.exists():
            return None
        try:
            obj = json.loads(self._rotation_path.read_text())
            if int(obj.get("version", 0)) != self.ROTATION_JOURNAL_VERSION:
                raise ValueError("unsupported journal version")
            rotation_id = str(obj["rotation_id"])
            self.root_key_store.validate_rotation_id(rotation_id)
            return rotation_id
        except Exception as exc:
            raise RuntimeError("invalid SecretVault root-key rotation journal") from exc

    def _create_rotation_journal(self, rotation_id: str) -> None:
        payload = json.dumps(
            {"version": self.ROTATION_JOURNAL_VERSION, "rotation_id": rotation_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(self._rotation_path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                self._rotation_path.unlink()
            except OSError:
                pass
            raise

    def _remove_rotation_journal(self) -> None:
        try:
            self._rotation_path.unlink()
        except FileNotFoundError:
            pass

    def _atomic_write_text(self, text: str) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def _decrypt(self, obj: dict, master_key: bytes) -> dict:
        version = int(obj.get("version", 1))
        nonce = base64.b64decode(obj["nonce"])
        ciphertext = base64.b64decode(obj["ciphertext"])
        aad = f"personal-ai-vault-v{version}".encode()
        raw = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
        return json.loads(raw.decode())

    def _load_root_backed(self, obj: dict) -> dict:
        file_rotation = obj.get("root_key_rotation")
        if file_rotation is not None:
            file_rotation = self.root_key_store.validate_rotation_id(str(file_rotation))
        journal_rotation = self._read_rotation_journal()

        active_key = self.root_key_store.get()
        if active_key is not None:
            try:
                data = self._decrypt(obj, active_key)
            except InvalidTag:
                pass
            else:
                # Active key and ciphertext agree. Any journal/staged key is now
                # either an abandoned pre-commit rotation or post-promotion debris.
                cleanup_ids = {rid for rid in (file_rotation, journal_rotation) if rid}
                for rotation_id in cleanup_ids:
                    try:
                        self.root_key_store.discard_staged(rotation_id)
                    except KeychainUnavailable:
                        pass
                if journal_rotation:
                    try:
                        self._remove_rotation_journal()
                    except OSError:
                        pass
                return data

        candidate_ids = []
        for rotation_id in (file_rotation, journal_rotation):
            if rotation_id and rotation_id not in candidate_ids:
                candidate_ids.append(rotation_id)
        for rotation_id in candidate_ids:
            staged_key = self.root_key_store.get_staged(rotation_id)
            if staged_key is None:
                continue
            try:
                data = self._decrypt(obj, staged_key)
            except InvalidTag:
                continue
            # Ciphertext was durably committed under the staged key but promotion
            # did not finish. Complete promotion before allowing further writes.
            self.root_key_store.promote_staged(rotation_id)
            self._root_key_rotation = None
            try:
                self.root_key_store.discard_staged(rotation_id)
            except KeychainUnavailable:
                pass
            if journal_rotation:
                try:
                    self._remove_rotation_journal()
                except OSError:
                    pass
            return data

        if active_key is None:
            raise KeychainUnavailable(
                "SecretVault root key is unavailable; refusing to create a replacement "
                "for existing ciphertext"
            )
        raise KeychainUnavailable(
            "SecretVault ciphertext does not match the active root key and no "
            "recoverable staged rotation key is available"
        )

    def _load(self):
        obj = json.loads(self.path.read_text())
        self._salt = base64.b64decode(obj["salt"])
        self._root_key_rotation = obj.get("root_key_rotation")
        if self._password:
            self._data = self._decrypt(obj, self._master())
        else:
            self._data = self._load_root_backed(obj)

    def _save(self, master_key: bytes | None = None):
        key = master_key or self._master()
        nonce = secrets.token_bytes(12)
        raw = json.dumps(self._data, sort_keys=True, separators=(",", ":")).encode()
        aad = f"personal-ai-vault-v{self.VERSION}".encode()
        ciphertext = AESGCM(key).encrypt(nonce, raw, aad)
        payload = {
            "version": self.VERSION,
            "salt": base64.b64encode(self._salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }
        if self._root_key_rotation and not self._password:
            payload["root_key_rotation"] = self._root_key_rotation
        self._atomic_write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    def set(self, name: str, value: str):
        with self.lock:
            self._data[name] = value
            self._save()

    def get(self, name: str, default=None):
        return self._data.get(name, default)

    def delete(self, name: str):
        with self.lock:
            self._data.pop(name, None)
            self._save()

    def names(self):
        return sorted(self._data)

    def rotate_password(self, new_password: str):
        with self.lock:
            self._password = new_password.encode()
            self._root_key_rotation = None
            self._salt = secrets.token_bytes(16)
            self._save()

    def rotate_root_key(self):
        if self._password:
            raise RuntimeError("vault is password-backed")
        with self.lock:
            pending_rotation = self._read_rotation_journal()
            if pending_rotation:
                raise RuntimeError(
                    "SecretVault root-key rotation recovery is pending; reopen the vault "
                    "before starting another rotation"
                )
            rotation_id = secrets.token_hex(16)
            self._create_rotation_journal(rotation_id)
            new_key = self.root_key_store.stage_rotation(rotation_id)
            self._root_key_rotation = rotation_id
            self._salt = secrets.token_bytes(16)
            self._save(master_key=new_key)
            self.root_key_store.promote_staged(rotation_id)
            # Promotion is durable before the recovery marker is removed. Rewriting
            # once under the promoted key leaves the steady-state envelope clean.
            self._root_key_rotation = None
            self._save(master_key=new_key)
            try:
                self.root_key_store.discard_staged(rotation_id)
            except KeychainUnavailable:
                pass
            try:
                self._remove_rotation_journal()
            except OSError:
                pass

    def migrate_to_keychain(self):
        with self.lock:
            self._password = None
            self._root_key_rotation = None
            self._salt = secrets.token_bytes(16)
            self.root_key_store.get_or_create()
            self._save()
