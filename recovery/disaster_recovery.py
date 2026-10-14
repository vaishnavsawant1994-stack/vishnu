from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path
import secrets
import struct
import tempfile
import time
import zipfile
from typing import Callable, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from recovery.backup import BackupError, BackupService, MEMORY_KEY_ENVELOPE


DISASTER_RECOVERY_MAGIC = b"VISHNUDR1\n"
DISASTER_RECOVERY_VERSION = 1
DISASTER_RECOVERY_TAG_BYTES = 16
DISASTER_RECOVERY_HEADER_MAX = 64 * 1024
DISASTER_RECOVERY_CHUNK = 1024 * 1024
DISASTER_RECOVERY_INFO = b"vishnu-disaster-recovery-v1"
RECOVERY_KEY_BYTES = 32
DR_MEMORY_KEY_KIND = "vishnu-disaster-recovery-memory-dek"
DR_MEMORY_KEY_INFO = b"vishnu-disaster-recovery-memory-dek-wrap-v1"
RECOVERY_KEY_FILE_MAGIC = b"VISHNU-RECOVERY-KEY-1\n"
RECOVERY_KEY_FILE_KDF_N = 2**15


class DisasterRecoveryError(RuntimeError):
    pass


class RecoveryKeyProvider(Protocol):
    """Provider-neutral source for a high-entropy disaster-recovery key.

    A future cloud/KMS implementation may release this key only after owner
    authentication. The bundle format does not depend on any one provider.
    """

    def recovery_key(self, key_id: str) -> bytes: ...


def generate_recovery_key() -> bytes:
    """Generate portable recovery key material.

    The caller must store this outside the source machine (for example in a
    trusted recovery vault). The key is never written into recovery bundles.
    """

    return secrets.token_bytes(RECOVERY_KEY_BYTES)


def _validate_recovery_key(value: bytes | bytearray) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != RECOVERY_KEY_BYTES:
        raise DisasterRecoveryError("recovery key must be exactly 32 bytes")
    return bytes(value)


def encrypt_recovery_key_file(recovery_key: bytes, passphrase: str) -> bytes:
    """Return an authenticated, passphrase-encrypted recovery-key file."""
    key = _validate_recovery_key(recovery_key)
    phrase = str(passphrase or "")
    if len(phrase) < 12:
        raise ValueError("recovery passphrase must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    header = json.dumps({
        "version": 1, "kdf": "scrypt", "n": RECOVERY_KEY_FILE_KDF_N,
        "r": 8, "p": 1, "cipher": "AES-256-GCM",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    derived = Scrypt(salt=salt, length=32, n=RECOVERY_KEY_FILE_KDF_N, r=8, p=1).derive(phrase.encode("utf-8"))
    return RECOVERY_KEY_FILE_MAGIC + struct.pack(">I", len(header)) + header + AESGCM(derived).encrypt(nonce, key, RECOVERY_KEY_FILE_MAGIC + header)


def decrypt_recovery_key_file(envelope: bytes, passphrase: str) -> bytes:
    """Authenticate and decrypt an exported recovery-key file."""
    try:
        if not envelope.startswith(RECOVERY_KEY_FILE_MAGIC):
            raise ValueError("unsupported recovery key file")
        offset = len(RECOVERY_KEY_FILE_MAGIC)
        size = struct.unpack(">I", envelope[offset:offset + 4])[0]
        if size <= 0 or size > 4096:
            raise ValueError("invalid recovery key header")
        start = offset + 4
        header_bytes = envelope[start:start + size]
        header = json.loads(header_bytes)
        if (set(header) != {"version", "kdf", "n", "r", "p", "cipher", "salt", "nonce"}
                or header["version"] != 1 or header["kdf"] != "scrypt"
                or header["n"] != RECOVERY_KEY_FILE_KDF_N or header["r"] != 8
                or header["p"] != 1 or header["cipher"] != "AES-256-GCM"):
            raise ValueError("unsupported recovery key parameters")
        salt = base64.b64decode(header["salt"], validate=True)
        nonce = base64.b64decode(header["nonce"], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError("invalid recovery key parameters")
        derived = Scrypt(salt=salt, length=32, n=RECOVERY_KEY_FILE_KDF_N, r=8, p=1).derive(str(passphrase or "").encode("utf-8"))
        key = AESGCM(derived).decrypt(nonce, envelope[start + size:], RECOVERY_KEY_FILE_MAGIC + header_bytes)
        return _validate_recovery_key(key)
    except Exception as exc:
        raise DisasterRecoveryError("recovery key file could not be authenticated") from exc


def _owner_binding(recovery_key: bytes, owner_id: str) -> str:
    owner = str(owner_id or "").strip()
    if not owner:
        raise ValueError("owner_id is required")
    return hmac.new(recovery_key, b"owner:" + owner.encode("utf-8"), hashlib.sha256).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DISASTER_RECOVERY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DisasterRecoveryBundleCodec:
    """Authenticated portable encryption independent of a host keychain."""

    @staticmethod
    def _derive_key(recovery_key: bytes, salt: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=DISASTER_RECOVERY_INFO,
        ).derive(_validate_recovery_key(recovery_key))

    @staticmethod
    def _header_bytes(header: dict) -> bytes:
        return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def encrypt_payload(
        self,
        payload: str | Path,
        target: str | Path,
        *,
        recovery_key: bytes,
        owner_id: str,
        key_id: str,
    ) -> Path:
        source = Path(payload).expanduser().resolve()
        destination = Path(target).expanduser().resolve()
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(source)
        key_ref = str(key_id or "").strip()
        if not key_ref:
            raise ValueError("key_id is required")
        key = _validate_recovery_key(recovery_key)
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        header = {
            "version": DISASTER_RECOVERY_VERSION,
            "cipher": "AES-256-GCM",
            "kdf": "HKDF-SHA256",
            "key_id": key_ref,
            "owner_binding": _owner_binding(key, owner_id),
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "created_at": int(time.time()),
        }
        encoded = self._header_bytes(header)
        if len(encoded) > DISASTER_RECOVERY_HEADER_MAX:
            raise DisasterRecoveryError("disaster recovery header is too large")
        raw_len = struct.pack(">I", len(encoded))
        aad = DISASTER_RECOVERY_MAGIC + raw_len + encoded
        encryption_key = self._derive_key(key, salt)
        encryptor = Cipher(algorithms.AES(encryption_key), modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(aad)

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(6)}.tmp")
        try:
            with source.open("rb") as src, temporary.open("wb") as dst:
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                dst.write(aad)
                for chunk in iter(lambda: src.read(DISASTER_RECOVERY_CHUNK), b""):
                    dst.write(encryptor.update(chunk))
                dst.write(encryptor.finalize())
                dst.write(encryptor.tag)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(temporary, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def decrypt_payload(
        self,
        bundle: str | Path,
        *,
        recovery_key: bytes,
        owner_id: str | None = None,
        expected_key_id: str | None = None,
    ) -> tuple[Path, dict]:
        source = Path(bundle).expanduser().resolve()
        key = _validate_recovery_key(recovery_key)
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(source)
        handle = tempfile.NamedTemporaryFile(
            prefix="vishnu-disaster-recovery-payload-", suffix=".zip", delete=False
        )
        target = Path(handle.name)
        handle.close()
        try:
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            with source.open("rb") as src:
                if src.read(len(DISASTER_RECOVERY_MAGIC)) != DISASTER_RECOVERY_MAGIC:
                    raise DisasterRecoveryError("unsupported disaster recovery bundle")
                raw_len = src.read(4)
                if len(raw_len) != 4:
                    raise DisasterRecoveryError("disaster recovery header is truncated")
                size = struct.unpack(">I", raw_len)[0]
                if size <= 0 or size > DISASTER_RECOVERY_HEADER_MAX:
                    raise DisasterRecoveryError("disaster recovery header is invalid")
                encoded = src.read(size)
                if len(encoded) != size:
                    raise DisasterRecoveryError("disaster recovery header is truncated")
                try:
                    header = json.loads(encoded)
                    if (
                        int(header.get("version", 0)) != DISASTER_RECOVERY_VERSION
                        or header.get("cipher") != "AES-256-GCM"
                        or header.get("kdf") != "HKDF-SHA256"
                    ):
                        raise ValueError("unsupported recovery header")
                    salt = bytes.fromhex(str(header["salt"]))
                    nonce = bytes.fromhex(str(header["nonce"]))
                    key_id = str(header["key_id"])
                    binding = str(header["owner_binding"])
                except Exception as exc:
                    raise DisasterRecoveryError("disaster recovery header is invalid") from exc
                if len(salt) != 16 or len(nonce) != 12 or not key_id:
                    raise DisasterRecoveryError("disaster recovery header is invalid")
                if expected_key_id is not None and key_id != str(expected_key_id):
                    raise DisasterRecoveryError("disaster recovery key id mismatch")
                ciphertext_start = src.tell()
                total = source.stat().st_size
                ciphertext_size = total - ciphertext_start - DISASTER_RECOVERY_TAG_BYTES
                if ciphertext_size < 0:
                    raise DisasterRecoveryError("disaster recovery ciphertext is truncated")
                src.seek(total - DISASTER_RECOVERY_TAG_BYTES)
                tag = src.read(DISASTER_RECOVERY_TAG_BYTES)
                if len(tag) != DISASTER_RECOVERY_TAG_BYTES:
                    raise DisasterRecoveryError("disaster recovery authentication tag is missing")
                src.seek(ciphertext_start)

                aad = DISASTER_RECOVERY_MAGIC + raw_len + encoded
                decryption_key = self._derive_key(key, salt)
                decryptor = Cipher(algorithms.AES(decryption_key), modes.GCM(nonce, tag)).decryptor()
                decryptor.authenticate_additional_data(aad)
                remaining = ciphertext_size
                with target.open("wb") as dst:
                    while remaining:
                        chunk = src.read(min(DISASTER_RECOVERY_CHUNK, remaining))
                        if not chunk:
                            raise DisasterRecoveryError("disaster recovery ciphertext is truncated")
                        remaining -= len(chunk)
                        dst.write(decryptor.update(chunk))
                    try:
                        dst.write(decryptor.finalize())
                    except InvalidTag as exc:
                        raise DisasterRecoveryError("disaster recovery authentication failed") from exc
                    dst.flush()
                    os.fsync(dst.fileno())
            bound_owner_id = str(owner_id or "").strip() or self._owner_id_from_payload(target)
            if not bound_owner_id or not hmac.compare_digest(
                binding, _owner_binding(key, bound_owner_id),
            ):
                raise PermissionError("disaster recovery bundle owner mismatch")
            if owner_id and self._owner_id_from_payload(target) not in {None, bound_owner_id}:
                raise PermissionError("disaster recovery bundle identity mismatch")
            header["_verified_owner_id"] = bound_owner_id
            return target, header
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _owner_id_from_payload(payload: Path) -> str | None:
        """Read the stable owner ID only from the authenticated encrypted payload."""
        try:
            with zipfile.ZipFile(payload) as archive:
                info = archive.getinfo("manifest.json")
                if info.file_size > 1024 * 1024:
                    raise DisasterRecoveryError("recovery manifest is too large")
                manifest = json.loads(archive.read(info))
            identity = manifest.get("identity_metadata")
            owner_id = identity.get("owner_id") if isinstance(identity, dict) else None
            return str(owner_id).strip() if owner_id else None
        except DisasterRecoveryError:
            raise
        except Exception as exc:
            raise DisasterRecoveryError("recovery identity manifest is invalid") from exc


class DisasterRecoveryService:
    """Create and restore owner recovery bundles without the source host key.

    Creation uses the existing BackupService snapshot rules, so secret files,
    runtime caches and unsafe SQLite sidecars remain excluded. Restore rewraps
    the authenticated portable payload with the *new host's* root key and then
    delegates mutation/rollback to BackupService.restore(). Security-authority
    databases therefore keep the existing non-restorable policy.
    """

    def __init__(
        self,
        backups: BackupService,
        *,
        codec: DisasterRecoveryBundleCodec | None = None,
        maintenance_mode: bool = False,
    ) -> None:
        self.backups = backups
        self.codec = codec or DisasterRecoveryBundleCodec()
        self.maintenance_mode = bool(maintenance_mode)

    @staticmethod
    def _rewrite_memory_key_envelope(payload: Path, transform: Callable[[bytes], bytes]) -> bool:
        payload = Path(payload)
        temporary = payload.with_name(f".{payload.name}.{secrets.token_hex(6)}.rewrite")
        try:
            with zipfile.ZipFile(payload, "r") as source:
                names = {item.filename for item in source.infolist() if not item.is_dir()}
                if MEMORY_KEY_ENVELOPE not in names:
                    return False
                try:
                    manifest = json.loads(source.read("manifest.json"))
                    envelope = source.read(MEMORY_KEY_ENVELOPE)
                except Exception as exc:
                    raise DisasterRecoveryError("recovery payload key envelope is invalid") from exc
                replacement = transform(envelope)
                records = manifest.get("files")
                if not isinstance(records, list):
                    raise DisasterRecoveryError("recovery payload manifest is invalid")
                record = next(
                    (item for item in records if item.get("path") == MEMORY_KEY_ENVELOPE),
                    None,
                )
                if record is None:
                    raise DisasterRecoveryError("recovery payload key envelope is unlisted")
                record["sha256"] = hashlib.sha256(replacement).hexdigest()
                record["size"] = len(replacement)
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for info in source.infolist():
                        if info.is_dir() or info.filename == "manifest.json":
                            continue
                        if info.filename == MEMORY_KEY_ENVELOPE:
                            target.writestr(info.filename, replacement)
                            continue
                        with source.open(info, "r") as reader, target.open(info.filename, "w") as writer:
                            shutil.copyfileobj(reader, writer, DISASTER_RECOVERY_CHUNK)
                    target.writestr(
                        "manifest.json",
                        json.dumps(manifest, sort_keys=True, indent=2),
                    )
            os.replace(temporary, payload)
            return True
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _wrap_memory_key_portably(
        self,
        envelope: bytes,
        *,
        recovery_key: bytes,
        owner_id: str,
        key_id: str,
    ) -> bytes:
        try:
            dek = self.backups._unwrap_memory_key(envelope)
            key = _validate_recovery_key(recovery_key)
            salt = secrets.token_bytes(16)
            nonce = secrets.token_bytes(12)
            header = {
                "version": 1,
                "kind": DR_MEMORY_KEY_KIND,
                "cipher": "AES-256-GCM",
                "kdf": "HKDF-SHA256",
                "key_id": key_id,
                "owner_binding": _owner_binding(key, owner_id),
                "salt": base64.b64encode(salt).decode("ascii"),
                "nonce": base64.b64encode(nonce).decode("ascii"),
            }
            wrapping_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                info=DR_MEMORY_KEY_INFO,
            ).derive(key)
            aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
            wrapped_key = AESGCM(wrapping_key).encrypt(nonce, dek, aad)
            return json.dumps(
                {
                    **header,
                    "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except BackupError:
            raise
        except Exception as exc:
            raise DisasterRecoveryError("MemoryStore key could not be wrapped for recovery") from exc

    def _unwrap_portable_memory_key(
        self,
        envelope: bytes,
        *,
        recovery_key: bytes,
        owner_id: str,
        key_id: str,
    ) -> bytes:
        try:
            obj = json.loads(envelope)
            if not isinstance(obj, dict) or obj.get("kind") != DR_MEMORY_KEY_KIND:
                # Older bundles contain the original host-wrapped envelope.
                return envelope
            header = {name: obj[name] for name in (
                "version", "kind", "cipher", "kdf", "key_id",
                "owner_binding", "salt", "nonce",
            )}
            if set(obj) != {*header, "wrapped_key"}:
                raise ValueError("invalid portable key envelope fields")
            if (
                header["version"] != 1
                or header["cipher"] != "AES-256-GCM"
                or header["kdf"] != "HKDF-SHA256"
                or header["key_id"] != key_id
            ):
                raise ValueError("unsupported portable key envelope")
            key = _validate_recovery_key(recovery_key)
            if not hmac.compare_digest(
                str(header["owner_binding"]),
                _owner_binding(key, owner_id),
            ):
                raise ValueError("portable key envelope owner mismatch")
            salt = base64.b64decode(header["salt"], validate=True)
            nonce = base64.b64decode(header["nonce"], validate=True)
            wrapped_key = base64.b64decode(obj["wrapped_key"], validate=True)
            if len(salt) != 16 or len(nonce) != 12 or len(wrapped_key) != 48:
                raise ValueError("invalid portable key envelope size")
            wrapping_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                info=DR_MEMORY_KEY_INFO,
            ).derive(key)
            aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
            dek = AESGCM(wrapping_key).decrypt(nonce, wrapped_key, aad)
            if len(dek) != 32:
                raise ValueError("invalid MemoryStore key size")
            return self.backups._wrap_memory_key(dek)
        except (BackupError, DisasterRecoveryError):
            raise
        except Exception as exc:
            raise DisasterRecoveryError("portable MemoryStore key envelope is invalid") from exc

    def create_bundle(
        self,
        target: str | Path,
        *,
        recovery_key: bytes,
        owner_id: str,
        key_id: str,
    ) -> dict:
        handle = tempfile.NamedTemporaryFile(
            prefix="vishnu-disaster-recovery-source-", suffix=".zip", delete=False
        )
        payload = Path(handle.name)
        handle.close()
        try:
            try:
                os.chmod(payload, 0o600)
            except OSError:
                pass
            manifest = self.backups._build_payload(payload)
            # Validate and rewrap a MemoryStore DEK for portable recovery. The
            # recovery key, never the source host key, protects this envelope.
            self.backups._inspect_zip(payload, encrypted=True)
            self._rewrite_memory_key_envelope(
                payload,
                lambda envelope: self._wrap_memory_key_portably(
                    envelope,
                    recovery_key=recovery_key,
                    owner_id=owner_id,
                    key_id=str(key_id),
                ),
            )
            self.backups._inspect_zip(payload, encrypted=True)
            destination = self.codec.encrypt_payload(
                payload,
                target,
                recovery_key=recovery_key,
                owner_id=owner_id,
                key_id=key_id,
            )
            return {
                "ok": True,
                "bundle_path": str(destination),
                "bundle_sha256": _sha256(destination),
                "bundle_size": destination.stat().st_size,
                "key_id": str(key_id),
                "file_count": len(manifest.get("files") or ()),
                "portable": True,
                "source_host_key_required_for_restore": False,
            }
        finally:
            payload.unlink(missing_ok=True)

    def validate_bundle(
        self,
        bundle: str | Path,
        *,
        recovery_key: bytes,
        owner_id: str | None = None,
        expected_key_id: str | None = None,
    ) -> dict:
        payload, header = self.codec.decrypt_payload(
            bundle,
            recovery_key=recovery_key,
            owner_id=owner_id,
            expected_key_id=expected_key_id,
        )
        try:
            manifest = self.backups._inspect_zip(payload, encrypted=True)
            identity = manifest.get("identity_metadata")
            bound_owner = str(header.get("_verified_owner_id") or owner_id or "")
            if identity and str(identity.get("owner_id")) != bound_owner:
                raise DisasterRecoveryError("recovery identity does not match its owner binding")
            return {
                "valid": True,
                "key_id": str(header["key_id"]),
                "owner_id": str(header.get("_verified_owner_id") or owner_id or ""),
                "file_count": len(manifest.get("files") or ()),
                "encrypted": True,
            }
        finally:
            payload.unlink(missing_ok=True)

    def restore_bundle(
        self,
        bundle: str | Path,
        *,
        recovery_key: bytes,
        owner_id: str | None = None,
        expected_key_id: str | None = None,
    ) -> dict:
        if not self.maintenance_mode:
            raise DisasterRecoveryError("disaster recovery restore requires maintenance mode")
        payload, header = self.codec.decrypt_payload(
            bundle,
            recovery_key=recovery_key,
            owner_id=owner_id,
            expected_key_id=expected_key_id,
        )
        owner_id = str(header.get("_verified_owner_id") or owner_id or "")
        rewrapped_handle = tempfile.NamedTemporaryFile(
            prefix="vishnu-disaster-recovery-rewrapped-", suffix=".paibackup", delete=False
        )
        rewrapped = Path(rewrapped_handle.name)
        rewrapped_handle.close()
        try:
            # Verify before crossing the restore boundary, then rewrap the
            # portable DEK under the target host's canonical root authority.
            self.backups._inspect_zip(payload, encrypted=True)
            self._rewrite_memory_key_envelope(
                payload,
                lambda envelope: self._unwrap_portable_memory_key(
                    envelope,
                    recovery_key=recovery_key,
                    owner_id=owner_id,
                    key_id=str(header["key_id"]),
                ),
            )
            self.backups._inspect_zip(payload, encrypted=True)
            # The old host key is intentionally not required in this path.
            self.backups._encrypt_payload(payload, rewrapped)
            result = self.backups.restore(rewrapped)
            return {
                **result,
                "key_id": str(header["key_id"]),
                "portable_disaster_recovery": True,
                "credentials_rebind_required": True,
            }
        finally:
            payload.unlink(missing_ok=True)
            rewrapped.unlink(missing_ok=True)
