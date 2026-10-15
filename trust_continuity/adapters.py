from __future__ import annotations

import secrets
from typing import Any, Callable

from .services import OAuthLifecycleManager


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
            raise PermissionError(
                "secret handle is outside the trust-continuity namespace"
            )
        value = self.keychain.get(handle)
        if value is None:
            raise KeyError("secret handle is unavailable")
        return value

    def delete(self, handle: str) -> None:
        if not handle.startswith(f"{self.prefix}:"):
            raise PermissionError(
                "secret handle is outside the trust-continuity namespace"
            )
        self.keychain.delete(handle)


class VerifiedOAuthLifecycleManager(OAuthLifecycleManager):
    """Production OAuth boundary that refuses unverified provider exchange."""

    def complete(
        self,
        flow_id: str,
        *,
        owner_id: str,
        state: str,
        authorization_code: str,
        exchange: Callable[[str, str, str], dict[str, Any]],
    ) -> str:
        def verified_exchange(
            code: str,
            verifier: str,
            redirect_uri: str,
        ) -> dict[str, Any]:
            tokens = exchange(code, verifier, redirect_uri)
            if not bool(tokens.get("provider_verified", False)):
                raise PermissionError("OAuth provider verification is required")
            return tokens

        return super().complete(
            flow_id,
            owner_id=owner_id,
            state=state,
            authorization_code=authorization_code,
            exchange=verified_exchange,
        )
