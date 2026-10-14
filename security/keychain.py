from __future__ import annotations

import base64
import os
import re
import secrets
from typing import Protocol, cast

SERVICE = "PersonalAI.RootKey"
ACCOUNT = "default"
ENV_ROOT_KEY = "PERSONAL_AI_ROOT_KEY"
_ROTATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class KeychainUnavailable(RuntimeError):
    pass


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class RootKeyStore:
    def __init__(self, service: str = SERVICE, account: str = ACCOUNT) -> None:
        self.service = service
        self.account = account

    def _env_key(self) -> bytes | None:
        raw = os.getenv(ENV_ROOT_KEY, "").strip()
        if not raw:
            return None
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise KeychainUnavailable(f"{ENV_ROOT_KEY} must be valid base64") from exc
        if len(key) != 32:
            raise KeychainUnavailable(f"{ENV_ROOT_KEY} must decode to exactly 32 bytes")
        return key

    def _kr(self) -> KeyringBackend:
        try:
            import keyring

            return cast(KeyringBackend, keyring)
        except Exception as exc:
            raise KeychainUnavailable("OS keychain backend unavailable") from exc

    def _decode(self, raw: str | None, label: str) -> bytes | None:
        if not raw:
            return None
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise KeychainUnavailable(f"{label} contains invalid root key material") from exc
        if len(key) != 32:
            raise KeychainUnavailable(f"{label} must contain exactly 32 bytes of root key material")
        return key

    def _get_account(self, account: str) -> bytes | None:
        try:
            raw = self._kr().get_password(self.service, account)
        except Exception as exc:
            raise KeychainUnavailable("OS keychain backend unavailable") from exc
        return self._decode(raw, f"OS keychain account {account!r}")

    def _set_account(self, account: str, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("root key must be exactly 32 bytes")
        try:
            self._kr().set_password(
                self.service,
                account,
                base64.b64encode(key).decode(),
            )
        except Exception as exc:
            raise KeychainUnavailable("OS keychain backend cannot persist root key") from exc

    def _delete_account(self, account: str) -> None:
        try:
            self._kr().delete_password(self.service, account)
        except Exception as exc:
            # keyring backends differ on how they report a missing credential.
            # If it is already absent, deletion is complete; otherwise surface the
            # backend failure so callers can leave recovery metadata in place.
            try:
                if self._kr().get_password(self.service, account) is None:
                    return
            except Exception:
                pass
            raise KeychainUnavailable("OS keychain backend cannot delete staged root key") from exc

    def validate_rotation_id(self, rotation_id: str) -> str:
        if not _ROTATION_ID_RE.fullmatch(rotation_id):
            raise ValueError("invalid root-key rotation id")
        return rotation_id

    def _rotation_account(self, rotation_id: str) -> str:
        return f"{self.account}.rotation.{self.validate_rotation_id(rotation_id)}"

    def get(self) -> bytes | None:
        env_key = self._env_key()
        if env_key:
            return env_key
        try:
            return self._get_account(self.account)
        except KeychainUnavailable as exc:
            raise KeychainUnavailable(
                "OS keychain backend unavailable and PERSONAL_AI_ROOT_KEY is not configured"
            ) from exc

    def get_or_create(self) -> bytes:
        key = self.get()
        if key:
            return key
        key = secrets.token_bytes(32)
        try:
            self._set_account(self.account, key)
        except KeychainUnavailable as exc:
            raise KeychainUnavailable(
                "OS keychain backend cannot persist root key; configure "
                "PERSONAL_AI_ROOT_KEY for headless/cloud runtime"
            ) from exc
        return key

    def stage_rotation(self, rotation_id: str) -> bytes:
        if self._env_key():
            raise KeychainUnavailable("Cannot rotate an environment-managed root key in-process")
        account = self._rotation_account(rotation_id)
        existing = self._get_account(account)
        if existing:
            return existing
        key = secrets.token_bytes(32)
        self._set_account(account, key)
        return key

    def get_staged(self, rotation_id: str) -> bytes | None:
        if self._env_key():
            return None
        return self._get_account(self._rotation_account(rotation_id))

    def promote_staged(self, rotation_id: str) -> bytes:
        if self._env_key():
            raise KeychainUnavailable("Cannot rotate an environment-managed root key in-process")
        key = self.get_staged(rotation_id)
        if key is None:
            raise KeychainUnavailable("staged root key is unavailable")
        self._set_account(self.account, key)
        if self._get_account(self.account) != key:
            raise KeychainUnavailable("OS keychain did not persist the promoted root key")
        return key

    def discard_staged(self, rotation_id: str) -> None:
        if self._env_key():
            return
        self._delete_account(self._rotation_account(rotation_id))

    def rotate(self) -> bytes:
        if self._env_key():
            raise KeychainUnavailable("Cannot rotate an environment-managed root key in-process")
        rotation_id = secrets.token_hex(16)
        key = self.stage_rotation(rotation_id)
        self.promote_staged(rotation_id)
        try:
            self.discard_staged(rotation_id)
        except KeychainUnavailable:
            pass
        return key

    def delete(self) -> None:
        if self._env_key():
            return
        try:
            self._delete_account(self.account)
        except KeychainUnavailable:
            pass
