from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from integrations.oauth import OAuthProvider


_SAFE = re.compile(r"[^a-zA-Z0-9._:-]+")


@dataclass(frozen=True)
class CapabilityOAuthBinding:
    capability_id: str
    provider_id: str
    credential_ref: str
    scopes: tuple[str, ...]
    connected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "credential_ref": self.credential_ref,
            "scopes": list(self.scopes),
            "connected": self.connected,
        }


class CapabilityOAuthLifecycle:
    """Capability-specific OAuth using Vishnu's existing PKCE manager and vault.

    Tokens never enter Forge storage or generated packages.  A capability gets a
    unique provider namespace in the existing OAuth vault so two capabilities
    using the same upstream provider cannot accidentally share/revoke each
    other's grant.  Durable OAuth state, PKCE, owner/device/session binding and
    security-epoch checks remain owned by OAuthAccountManager.
    """

    AUTH_TYPE = "oauth2_pkce"

    def __init__(self, *, oauth, catalog, providers: dict[str, OAuthProvider], events=None):
        self.oauth = oauth
        self.catalog = catalog
        self.providers = dict(providers or {})
        self.events = events

    @staticmethod
    def _provider_namespace(capability_id: str, provider_id: str) -> str:
        capability = _SAFE.sub("-", str(capability_id or "").strip()).strip("-._:")
        provider = _SAFE.sub("-", str(provider_id or "").strip()).strip("-._:")
        if not capability or not provider or len(capability) > 160 or len(provider) > 120:
            raise ValueError("invalid capability OAuth binding")
        return f"capability:{capability}:{provider}"

    def _base_provider(self, provider_id: str) -> OAuthProvider:
        provider = self.providers.get(str(provider_id))
        if provider is None:
            raise KeyError(f"OAuth provider is not configured: {provider_id}")
        return provider

    def _scoped_provider(self, capability_id: str, provider_id: str) -> OAuthProvider:
        base = self._base_provider(provider_id)
        return OAuthProvider(
            self._provider_namespace(capability_id, base.id),
            base.authorize_url,
            base.token_url,
            base.client_id,
            list(base.scopes),
            base.client_secret,
            base.revoke_url,
        )

    def _capability(self, capability_id: str) -> dict[str, Any]:
        item = self.catalog.get(str(capability_id))
        if item is None:
            raise KeyError(capability_id)
        return item

    def begin(
        self,
        capability_id: str,
        provider_id: str,
        *,
        scopes: list[str] | tuple[str, ...] | None = None,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
        security_epoch: int | None = None,
        redirect_uri: str | None = None,
        relink_intent: str = "connect",
    ) -> dict[str, Any]:
        self._capability(capability_id)
        base = self._base_provider(provider_id)
        requested = tuple(str(x).strip() for x in (scopes or base.scopes) if str(x).strip())
        allowed = set(base.scopes)
        if not requested or not set(requested).issubset(allowed):
            raise PermissionError("requested OAuth scopes exceed the configured provider scope boundary")
        scoped = self._scoped_provider(capability_id, provider_id)
        result = self.oauth.begin(
            scoped,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            connector_id=str(capability_id),
            scopes=list(requested),
            redirect_uri=redirect_uri,
            security_epoch=security_epoch,
            relink_intent=relink_intent,
        )
        return {
            "state": result["state"],
            "url": result["url"],
            "expires_in": result["expires_in"],
            "capability_id": str(capability_id),
            "provider_id": str(provider_id),
            "scopes": list(requested),
        }

    def complete(
        self,
        capability_id: str,
        provider_id: str,
        *,
        state: str,
        code: str,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
        security_epoch: int | None = None,
    ) -> CapabilityOAuthBinding:
        self._capability(capability_id)
        scoped = self._scoped_provider(capability_id, provider_id)
        result = self.oauth.complete(
            state,
            code,
            scoped,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            connector_id=str(capability_id),
            security_epoch=security_epoch,
        )
        credential_ref = f"oauth:{scoped.id}"
        self.catalog.connect(
            str(capability_id),
            server_url="oauth://provider",
            auth_type=self.AUTH_TYPE,
            credential_ref=credential_ref,
            approved_by=str(owner_id or "owner"),
            approved_at=time.time(),
            connector_id=str(capability_id),
        )
        binding = CapabilityOAuthBinding(
            capability_id=str(capability_id),
            provider_id=str(provider_id),
            credential_ref=credential_ref,
            scopes=tuple(result.get("scopes") or ()),
            connected=True,
        )
        if self.events is not None:
            self.events.emit(
                "capability_forge.oauth_connected",
                capability_id=binding.capability_id,
                provider_id=binding.provider_id,
                scopes=list(binding.scopes),
            )
        return binding

    def token(self, capability_id: str, provider_id: str) -> str:
        """Internal adapter hook. Never expose this value through owner/Forge APIs."""
        connection = self.catalog.connection(str(capability_id), include_credential_ref=True)
        if not connection or connection.get("status") != "connected" or connection.get("auth_type") != self.AUTH_TYPE:
            raise PermissionError("capability OAuth connection is not active")
        scoped = self._scoped_provider(capability_id, provider_id)
        expected = f"oauth:{scoped.id}"
        if connection.get("credential_ref") != expected:
            raise PermissionError("capability OAuth credential binding mismatch")
        return self.oauth.token(scoped)

    def status(self, capability_id: str) -> dict[str, Any]:
        connection = self.catalog.connection(str(capability_id), include_credential_ref=False)
        if not connection:
            return {"capability_id": str(capability_id), "connected": False, "auth_type": None}
        return {
            "capability_id": str(capability_id),
            "connected": connection.get("status") == "connected",
            "auth_type": connection.get("auth_type"),
            "approved_by": connection.get("approved_by"),
            "approved_at": connection.get("approved_at"),
        }

    def revoke(
        self,
        capability_id: str,
        provider_id: str,
        *,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        scoped = self._scoped_provider(capability_id, provider_id)
        revoked_ref = self.catalog.revoke(str(capability_id))
        expected = f"oauth:{scoped.id}"
        if revoked_ref not in {None, expected}:
            raise PermissionError("capability OAuth credential binding mismatch during revocation")
        result = self.oauth.unlink(
            scoped.id,
            provider=scoped,
            connector_id=str(capability_id),
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            attempt_provider_revocation=True,
        )
        if self.events is not None:
            self.events.emit(
                "capability_forge.oauth_revoked",
                capability_id=str(capability_id),
                provider_id=str(provider_id),
                provider_revocation=result.get("provider_revocation"),
            )
        return {"capability_id": str(capability_id), **result}
