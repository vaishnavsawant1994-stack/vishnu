from __future__ import annotations

import secrets


class KeychainSecretStore:
    """Opaque-handle adapter over Vishnu's existing security Keychain."""

    def __init__(self, keychain, *, prefix: str = "trust-continuity.oauth"):
        self.keychain = keychain
        self.prefix = prefix

    def put(self, name: str, value: str) -> str:
        if not value:
            raise ValueError("secret value is required")
        handle = f"{self.prefix}:{name[:120]}:{secrets.token_hex(16)}"
        self.keychain.set(handle, value)
        return handle

    def get(self, handle: str) -> str:
        if not handle.startswith(f"{self.prefix}:"):
            raise PermissionError("secret handle is outside the trust-continuity namespace")
        value = self.keychain.get(handle)
        if value is None:
            raise KeyError("secret handle is unavailable")
        return value

    def delete(self, handle: str) -> None:
        if not handle.startswith(f"{self.prefix}:"):
            raise PermissionError("secret handle is outside the trust-continuity namespace")
        self.keychain.delete(handle)
