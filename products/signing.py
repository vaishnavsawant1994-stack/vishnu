from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


SIGNING_KEY_ENV = "VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64"
PUBLIC_KEY_ENV = "VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class SignatureEnvelope:
    algorithm: str
    signature_b64: str
    public_key_b64: str
    key_fingerprint: str

    def as_dict(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "signature_b64": self.signature_b64,
            "public_key_b64": self.public_key_b64,
            "key_fingerprint": self.key_fingerprint,
        }


def _private_key_from_env() -> Ed25519PrivateKey | None:
    encoded = os.environ.get(SIGNING_KEY_ENV, "").strip()
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(f"{SIGNING_KEY_ENV} must be valid base64") from exc
    if len(raw) != 32:
        raise ValueError(f"{SIGNING_KEY_ENV} must decode to exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def signing_available() -> bool:
    return bool(os.environ.get(SIGNING_KEY_ENV, "").strip())


def sign_payload(payload: bytes, *, require_key: bool = True) -> SignatureEnvelope | None:
    key = _private_key_from_env()
    if key is None:
        if require_key:
            raise ValueError("Product signing is not configured")
        return None
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    configured_public = os.environ.get(PUBLIC_KEY_ENV, "").strip()
    if configured_public:
        try:
            expected = base64.b64decode(configured_public, validate=True)
        except Exception as exc:
            raise ValueError(f"{PUBLIC_KEY_ENV} must be valid base64") from exc
        if expected != public_key:
            raise ValueError("Configured product signing public key does not match the product signing private key")
    signature = key.sign(payload)
    return SignatureEnvelope(
        algorithm="ed25519",
        signature_b64=base64.b64encode(signature).decode("ascii"),
        public_key_b64=base64.b64encode(public_key).decode("ascii"),
        key_fingerprint=hashlib.sha256(public_key).hexdigest(),
    )


def verify_payload(payload: bytes, envelope: dict) -> bool:
    if envelope.get("algorithm") != "ed25519":
        return False
    try:
        public_key = base64.b64decode(str(envelope["public_key_b64"]), validate=True)
        signature = base64.b64decode(str(envelope["signature_b64"]), validate=True)
        if hashlib.sha256(public_key).hexdigest() != str(envelope.get("key_fingerprint", "")):
            return False
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
        return True
    except Exception:
        return False
