from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

import httpx

from .policy import CloudMode


MAX_RELAY_CIPHERTEXT_BYTES = 16 * 1024 * 1024
MAX_RELAY_TTL_SECONDS = 15 * 60
_ALLOWED_FRAME_KEYS = frozenset({
    "protocol", "algorithm", "ciphertext", "nonce", "aad", "key_epoch", "wrapped_key",
    "wrap_nonce", "session_id", "lease_id", "sequence", "eof", "content_digest",
})
_FORBIDDEN_PLAINTEXT_KEYS = frozenset({
    "plaintext", "payload", "content", "raw", "raw_bytes", "file_bytes", "document_content",
})


class RelayError(RuntimeError):
    pass


class OpaqueVishnuRelayClient:
    """Optional off-LAN mailbox for already-encrypted Vishnu frames.

    The relay is transport only. DeviceRegistry remains trust authority, the
    data plane remains residency/sync authority, and encryption happens before
    this client is called. The relay never receives a DEK/KEK or plaintext.
    """

    def __init__(
        self,
        manager,
        vault,
        *,
        endpoint: str,
        credential_ref: str,
        local_device_id: str,
        client: Any | None = None,
        timeout: float = 20.0,
    ):
        self.manager = manager
        self.vault = vault
        self.endpoint = self._endpoint(endpoint)
        self.credential_ref = str(credential_ref or "").strip()
        self.local_device_id = str(local_device_id or "").strip()
        if not self.credential_ref or not self.local_device_id:
            raise RelayError("relay credential reference and local device id are required")
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    @staticmethod
    def _endpoint(value: str) -> str:
        endpoint = str(value or "").rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RelayError("Vishnu relay endpoint must be credential-free HTTPS")
        return endpoint

    def _assert_enabled(self) -> None:
        settings = self.manager.settings()
        if not settings.get("cloud_enabled"):
            raise PermissionError("online/cloud storage is disabled by owner policy")
        mode = CloudMode(settings.get("cloud_mode") or CloudMode.LOCAL_ONLY.value)
        if mode not in {CloudMode.VISHNU_CLOUD, CloudMode.HYBRID}:
            raise PermissionError("Vishnu relay requires Vishnu Cloud or Hybrid owner mode")

    def _token(self) -> str:
        raw = self.vault.get(self.credential_ref) if self.vault is not None else None
        if not raw:
            raise RelayError("relay credential is unavailable from the canonical vault")
        token = str(raw)
        try:
            parsed = json.loads(token)
            if isinstance(parsed, dict):
                token = str(parsed.get("token") or parsed.get("access_token") or "")
        except json.JSONDecodeError:
            pass
        if not token:
            raise RelayError("relay credential is invalid")
        return token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        }

    def _assert_device(self, device_id: str) -> None:
        if hasattr(self.manager, "_assert_active_device"):
            self.manager._assert_active_device(str(device_id), "data:sync")

    @staticmethod
    def _validate_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(frame or {})
        if any(key in item for key in _FORBIDDEN_PLAINTEXT_KEYS):
            raise RelayError("relay frames must not contain plaintext data fields")
        unknown = set(item) - _ALLOWED_FRAME_KEYS
        if unknown:
            raise RelayError("relay frame contains unsupported fields")
        ciphertext = item.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext:
            raise RelayError("relay frame requires encrypted ciphertext")
        try:
            raw = base64.b64decode(ciphertext, validate=True)
        except Exception as exc:
            raise RelayError("relay ciphertext is not valid base64") from exc
        if len(raw) > MAX_RELAY_CIPHERTEXT_BYTES:
            raise RelayError("relay ciphertext exceeds bounded message size")
        if not item.get("algorithm") or not item.get("nonce"):
            raise RelayError("relay frame is missing encryption metadata")
        return item

    def verify(self) -> dict[str, Any]:
        self._assert_enabled()
        self._assert_device(self.local_device_id)
        response = self.client.get(f"{self.endpoint}/v1/relay/health", headers=self._headers())
        response.raise_for_status()
        body = response.json()
        if body.get("service") not in {"vishnu-relay", "vishnu-cloud"}:
            raise RelayError("endpoint is not a compatible Vishnu relay")
        return {"ok": True, "service": body.get("service"), "version": body.get("version")}

    def send_encrypted(
        self,
        target_device_id: str,
        frame: Mapping[str, Any],
        *,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        self._assert_enabled()
        target = str(target_device_id or "").strip()
        if not target:
            raise ValueError("target_device_id is required")
        self._assert_device(self.local_device_id)
        self._assert_device(target)
        encrypted = self._validate_frame(frame)
        ttl = max(1, min(int(ttl_seconds), MAX_RELAY_TTL_SECONDS))
        message_id = secrets.token_urlsafe(24)
        body = {
            "protocol": "vishnu-opaque-relay-v1",
            "message_id": message_id,
            "source_device_id": self.local_device_id,
            "target_device_id": target,
            "expires_at": time.time() + ttl,
            "frame": encrypted,
        }
        response = self.client.post(
            f"{self.endpoint}/v1/relay/messages",
            headers=self._headers(),
            content=json.dumps(body, sort_keys=True, separators=(",", ":")),
        )
        response.raise_for_status()
        result = response.json()
        if str(result.get("message_id") or "") != message_id:
            raise RelayError("relay did not acknowledge the expected opaque message")
        return {"message_id": message_id, "target_device_id": target, "expires_at": body["expires_at"]}

    def receive_encrypted(self, *, cursor: str | None = None, limit: int = 32) -> dict[str, Any]:
        self._assert_enabled()
        self._assert_device(self.local_device_id)
        bounded_limit = max(1, min(int(limit), 100))
        params = {"device_id": self.local_device_id, "limit": bounded_limit}
        if cursor:
            params["cursor"] = str(cursor)
        response = self.client.get(
            f"{self.endpoint}/v1/relay/messages?{urlencode(params)}",
            headers=self._headers(),
        )
        response.raise_for_status()
        body = response.json()
        messages = []
        now = time.time()
        for raw in list(body.get("messages") or []):
            if not isinstance(raw, dict):
                raise RelayError("relay returned an invalid message")
            if raw.get("protocol") != "vishnu-opaque-relay-v1":
                raise RelayError("relay returned an unsupported protocol")
            if str(raw.get("target_device_id") or "") != self.local_device_id:
                raise RelayError("relay returned a message for another device")
            source = str(raw.get("source_device_id") or "")
            self._assert_device(source)
            expires_at = float(raw.get("expires_at") or 0)
            if expires_at <= now:
                continue
            frame = self._validate_frame(raw.get("frame") or {})
            messages.append({
                "message_id": str(raw.get("message_id") or ""),
                "source_device_id": source,
                "expires_at": expires_at,
                "frame": frame,
            })
        return {"messages": messages, "cursor": body.get("cursor")}

    def acknowledge(self, message_id: str) -> bool:
        self._assert_enabled()
        self._assert_device(self.local_device_id)
        message = quote_component(message_id)
        response = self.client.delete(
            f"{self.endpoint}/v1/relay/messages/{message}",
            headers=self._headers(),
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True


def quote_component(value: str) -> str:
    value = str(value or "").strip()
    if not value or len(value) > 256 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value):
        raise ValueError("invalid relay message id")
    return value
