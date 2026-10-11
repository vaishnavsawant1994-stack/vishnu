from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SignedLicense:
    payload: dict
    signature: str
    key_id: str

    def as_dict(self) -> dict:
        return {"payload": dict(self.payload), "signature": self.signature, "key_id": self.key_id}


class LicenseAuthority:
    """Owner-side Ed25519 license signer.

    The private key belongs in Vishnu's encrypted vault/signing environment and
    must never be included in a client product. Exported runtimes receive only
    the public verification key.
    """

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key
        self.public_key = private_key.public_key()
        self.key_id = self.public_key_id(self.public_key)

    @classmethod
    def generate(cls) -> "LicenseAuthority":
        return cls(Ed25519PrivateKey.generate())

    @staticmethod
    def public_key_id(public_key: Ed25519PublicKey) -> str:
        raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return hashlib.sha256(raw).hexdigest()[:24]

    def issue(
        self,
        *,
        license_id: str,
        product_id: str,
        client_id: str,
        license_type: str,
        expires_at: str | None = None,
        device_limit: int | None = None,
        user_limit: int | None = None,
        managed_ai_allowed: bool = False,
        entitlements: dict | None = None,
    ) -> SignedLicense:
        if not license_id or not product_id or not client_id:
            raise ValueError("license_id, product_id and client_id are required")
        if device_limit is not None and int(device_limit) < 1:
            raise ValueError("device_limit must be positive")
        if user_limit is not None and int(user_limit) < 1:
            raise ValueError("user_limit must be positive")
        payload = {
            "schema": "vishnu.license/v1",
            "license_id": str(license_id),
            "product_id": str(product_id),
            "client_id": str(client_id),
            "license_type": str(license_type),
            "issued_at": _now(),
            "expires_at": expires_at,
            "device_limit": int(device_limit) if device_limit is not None else None,
            "user_limit": int(user_limit) if user_limit is not None else None,
            "managed_ai_allowed": bool(managed_ai_allowed),
            "entitlements": dict(entitlements or {}),
        }
        signature = self._private_key.sign(_canonical(payload))
        return SignedLicense(payload, base64.urlsafe_b64encode(signature).decode("ascii"), self.key_id)


class LicenseVerifier:
    def __init__(self, public_keys: dict[str, Ed25519PublicKey]):
        self.public_keys = dict(public_keys)

    def verify(self, document: dict, *, product_id: str | None = None, now: datetime | None = None) -> dict:
        payload = document.get("payload")
        signature = document.get("signature")
        key_id = str(document.get("key_id") or "")
        if not isinstance(payload, dict) or not signature or key_id not in self.public_keys:
            raise ValueError("Invalid license document")
        try:
            raw_signature = base64.urlsafe_b64decode(str(signature).encode("ascii"))
            self.public_keys[key_id].verify(raw_signature, _canonical(payload))
        except Exception as exc:
            raise ValueError("License signature verification failed") from exc
        if payload.get("schema") != "vishnu.license/v1":
            raise ValueError("Unsupported license schema")
        if product_id is not None and payload.get("product_id") != product_id:
            raise ValueError("License is for a different product")
        expires_at = payload.get("expires_at")
        if expires_at:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            current = now or datetime.now(timezone.utc)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if current >= expiry:
                raise ValueError("License has expired")
        return dict(payload)
