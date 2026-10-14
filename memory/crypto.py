from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from enum import Enum
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ENVELOPE_VERSION = 1
ENVELOPE_PREFIX = "v1:"
ALGORITHM = "AES-256-GCM"
VAULT_KEY_NAME = "memory_store:field_key:v1"
INDEX_INFO = b"vishnu-memory-store-blind-index-v1"


class DataClass(str, Enum):
    OPERATIONAL = "operational"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


# Explicit classification keeps encryption deliberate: identifiers, timestamps,
# lifecycle state and relationship keys remain queryable operational metadata;
# owner-authored/content-bearing values are encrypted.
FIELD_CLASSIFICATION: dict[str, dict[str, DataClass]] = {
    "messages": {
        "id": DataClass.OPERATIONAL,
        "role": DataClass.OPERATIONAL,
        "content": DataClass.HIGHLY_SENSITIVE,
        "conversation_id": DataClass.OPERATIONAL,
        "device_id": DataClass.OPERATIONAL,
        "metadata_json": DataClass.SENSITIVE,
        "created_at": DataClass.OPERATIONAL,
    },
    "memories": {
        "id": DataClass.OPERATIONAL,
        "type": DataClass.OPERATIONAL,
        "subject": DataClass.HIGHLY_SENSITIVE,
        "content": DataClass.HIGHLY_SENSITIVE,
        "source": DataClass.SENSITIVE,
        "tags_json": DataClass.SENSITIVE,
        "evidence_json": DataClass.HIGHLY_SENSITIVE,
        "metadata_json": DataClass.HIGHLY_SENSITIVE,
    },
    "tasks": {"title": DataClass.SENSITIVE, "payload_json": DataClass.HIGHLY_SENSITIVE},
    "audit": {"payload_json": DataClass.HIGHLY_SENSITIVE},
    "memory_usage": {"query": DataClass.HIGHLY_SENSITIVE},
    "memory_conflicts": {"reason": DataClass.SENSITIVE},
}

SENSITIVE_FIELDS: dict[str, tuple[str, ...]] = {
    table: tuple(field for field, classification in fields.items() if classification != DataClass.OPERATIONAL)
    for table, fields in FIELD_CLASSIFICATION.items()
}


class MemoryEncryptionError(RuntimeError):
    pass


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise MemoryEncryptionError("memory ciphertext envelope is invalid") from exc


class MemoryFieldCipher:
    """Versioned AES-GCM field encryption rooted in Vishnu's canonical SecretVault."""

    def __init__(self, vault):
        if vault is None:
            raise MemoryEncryptionError("MemoryStore encryption requires Vishnu's canonical SecretVault")
        self.vault = vault
        self._key: bytes | None = None
        self._index_key: bytes | None = None

    @staticmethod
    def is_encrypted(value: Any) -> bool:
        return isinstance(value, str) and value.startswith(ENVELOPE_PREFIX)

    def ensure_key(self, *, allow_create: bool) -> bytes:
        if self._key is not None:
            return self._key
        encoded = self.vault.get(VAULT_KEY_NAME)
        if encoded is None:
            if not allow_create:
                raise MemoryEncryptionError(
                    "MemoryStore encryption key is unavailable; refusing to replace key material for existing ciphertext"
                )
            encoded = _b64(secrets.token_bytes(32))
            self.vault.set(VAULT_KEY_NAME, encoded)
        try:
            key = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise MemoryEncryptionError("MemoryStore encryption key is invalid") from exc
        if len(key) != 32:
            raise MemoryEncryptionError("MemoryStore encryption key is invalid")
        self._key = key
        self._index_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=INDEX_INFO
        ).derive(key)
        return key

    @staticmethod
    def _aad(table: str, row_id: str, field: str) -> bytes:
        return json.dumps(
            {"v": ENVELOPE_VERSION, "table": str(table), "row": str(row_id), "field": str(field)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def encrypt(self, table: str, row_id: str, field: str, value: Any) -> Any:
        if value is None:
            return None
        text = str(value)
        if self.is_encrypted(text):
            # Verification makes retry/idempotency fail closed on wrong-key/tamper.
            self.decrypt(table, row_id, field, text)
            return text
        key = self.ensure_key(allow_create=True)
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(
            nonce, text.encode("utf-8"), self._aad(table, row_id, field)
        )
        return ENVELOPE_PREFIX + _b64(nonce + ciphertext)

    def decrypt(self, table: str, row_id: str, field: str, value: Any) -> Any:
        if value is None:
            return None
        text = str(value)
        if not self.is_encrypted(text):
            raise MemoryEncryptionError("MemoryStore contains unexpected plaintext in an encrypted field")
        raw = _unb64(text[len(ENVELOPE_PREFIX):])
        if len(raw) < 12 + 16:
            raise MemoryEncryptionError("memory ciphertext envelope is invalid")
        key = self.ensure_key(allow_create=False)
        try:
            plaintext = AESGCM(key).decrypt(
                raw[:12], raw[12:], self._aad(table, row_id, field)
            )
        except InvalidTag as exc:
            raise MemoryEncryptionError("MemoryStore ciphertext authentication failed") from exc
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MemoryEncryptionError("MemoryStore ciphertext plaintext encoding is invalid") from exc

    @staticmethod
    def normalize_index(value: Any) -> bytes:
        return " ".join(str(value or "").strip().casefold().split()).encode("utf-8")

    def blind_index(self, value: Any) -> str:
        self.ensure_key(allow_create=False)
        assert self._index_key is not None
        return hmac.new(self._index_key, self.normalize_index(value), hashlib.sha256).hexdigest()
