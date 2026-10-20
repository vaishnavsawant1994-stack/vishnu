from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import struct
import tempfile
import time
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from security.keychain import KeychainUnavailable, RootKeyStore
from security.vault import SecretVault
from memory.crypto import SENSITIVE_FIELDS, VAULT_KEY_NAME


EXCLUDED_NAMES = {'vault.json', '.env', 'secrets.json'}
EXCLUDED_DIRS = {'browser-profile', 'cache', 'tmp'}
# Security authority is intentionally non-restorable from ordinary data backups.
# Restoring an older copy could resurrect revoked devices/sessions, roll back the
# approval security epoch, or weaken owner/policy controls.
NON_RESTORABLE_SECURITY_NAMES = {
    'devices.sqlite3',
    'pwa-sessions.sqlite3',
    'cloud-sessions.sqlite3',
    'trusted-actions.sqlite3',
    'runtime-controls.sqlite3',
    'operator-policies.sqlite3',
    'operator-transactions.sqlite3',
    'owner-access.sqlite3',
    # Continuation leases, epochs, grants and checkpoints are host-local
    # authority. Cross-host imports recreate only the authenticated checkpoint
    # and one-time grant on the target; restoring this database would both
    # overwrite live SQLite state on Windows and risk rolling back target
    # authority.
    'agent-continuity.sqlite3',
    'connectors.sqlite3',
}
SQLITE_SUFFIXES = {'.sqlite3', '.sqlite', '.db'}
SQLITE_SIDECARS = ('-wal', '-shm', '-journal')

BACKUP_MAGIC = b'PAIBACKUP2\n'
BACKUP_VERSION = 2
BACKUP_TAG_BYTES = 16
BACKUP_HEADER_MAX = 64 * 1024
BACKUP_INFO = b'personal-ai-backup-v2'
MEMORY_KEY_ENVELOPE = 'system-key-envelopes/memory-field-key.v1.json'
MEMORY_KEY_AAD = b'vishnu-backup-memory-field-key-v1'
MEMORY_KEY_INFO = b'vishnu-backup-memory-field-key-wrap-v1'
COPY_CHUNK = 1024 * 1024


class BackupError(RuntimeError):
    pass


class BackupService:
    """Authenticated encrypted backups for owner data.

    New backups are always encrypted with AES-256-GCM. A per-backup encryption
    key is derived from the owner root key using HKDF-SHA256 and a random salt.
    The owner root key itself is never written into the archive.

    Legacy v1 plaintext ZIP backups remain readable so existing owner recovery
    artifacts are not stranded, but this service never creates new plaintext
    backups.
    """

    def __init__(
        self,
        data_dir: Path,
        root_key_store: RootKeyStore | None = None,
        *,
        vault: SecretVault | None = None,
        vault_password: str | None = None,
    ):
        self.data_dir = Path(data_dir).resolve()
        self.backup_dir = self.data_dir / 'backups'
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.root_key_store = root_key_store or RootKeyStore()
        self.vault = vault
        self.vault_password = vault_password

    @staticmethod
    def _sha(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(COPY_CHUNK), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_rel(value: str) -> Path:
        rel = Path(value)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise BackupError('unsafe backup path')
        return rel

    def _safe_destination(self, rel: Path) -> Path:
        """Return a restore destination proven to stay inside the owner data root."""
        destination = self.data_dir / rel
        root = self.data_dir.resolve()
        resolved = destination.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise BackupError(f'unsafe restore destination: {rel.as_posix()}')
        current = self.data_dir
        for part in rel.parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise BackupError(f'unsafe restore destination: {rel.as_posix()}')
        if destination.exists() and destination.is_symlink():
            raise BackupError(f'unsafe restore destination: {rel.as_posix()}')
        return destination

    def _eligible(self):
        files = []
        for path in self.data_dir.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            if self.backup_dir in path.parents:
                continue
            rel = path.relative_to(self.data_dir)
            if path.name in EXCLUDED_NAMES:
                continue
            if path.name.endswith(SQLITE_SIDECARS):
                continue
            if any(part.lower() in EXCLUDED_DIRS for part in rel.parts[:-1]):
                continue
            files.append(path)
        return sorted(files)

    @staticmethod
    def _sqlite_integrity(path: Path) -> None:
        try:
            uri = path.resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True, timeout=30) as con:
                row = con.execute('PRAGMA integrity_check').fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupError(f'database integrity failure: {path.name}') from exc
        if not row or row[0] != 'ok':
            raise BackupError(f'database integrity failure: {path.name}')

    @classmethod
    def _is_valid_sqlite(cls, path: Path) -> bool:
        try:
            cls._sqlite_integrity(path)
            return True
        except BackupError:
            return False

    @staticmethod
    def _snapshot_sqlite(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source_uri = source.resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(source_uri, uri=True, timeout=30) as src:
                with sqlite3.connect(destination, timeout=30) as dst:
                    src.backup(dst)
                    row = dst.execute('PRAGMA integrity_check').fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupError(f'cannot snapshot database safely: {source.name}') from exc
        if not row or row[0] != 'ok':
            raise BackupError(f'cannot snapshot database safely: {source.name}')

    def _snapshot_file(self, source: Path, destination: Path) -> None:
        if source.suffix.lower() in SQLITE_SUFFIXES:
            self._snapshot_sqlite(source, destination)
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    @staticmethod
    def _restore_sqlite_snapshot(source: Path, destination: Path) -> None:
        """Restore SQLite contents without replacing an open Windows database.

        SQLite's online backup API coordinates with other connections and keeps
        the destination file identity stable, unlike ``os.replace`` which fails
        on Windows whenever the runtime still has the database open.
        """
        try:
            source_uri = source.resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(source_uri, uri=True, timeout=30) as src:
                with sqlite3.connect(destination, timeout=30) as dst:
                    src.backup(dst)
                    row = dst.execute('PRAGMA integrity_check').fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupError(f'cannot restore database safely: {destination.name}') from exc
        if not row or row[0] != 'ok':
            raise BackupError(f'cannot restore database safely: {destination.name}')

    def _memory_key_envelope(self) -> bytes | None:
        vault_path = self.data_dir / 'vault.json'
        vault = self.vault or SecretVault.live(vault_path)
        encrypted_memory_data = False
        database = self.data_dir / 'assistant.sqlite3'
        if database.is_file():
            try:
                with sqlite3.connect(database) as con:
                    for table, fields in SENSITIVE_FIELDS.items():
                        present = con.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                        ).fetchone()
                        if not present:
                            continue
                        columns = {row[1] for row in con.execute(f'PRAGMA table_info({table})')}
                        for field in fields:
                            if field in columns and con.execute(
                                f"SELECT 1 FROM {table} WHERE {field} LIKE 'v1:%' LIMIT 1"
                            ).fetchone():
                                encrypted_memory_data = True
                                break
                        if encrypted_memory_data:
                            break
            except sqlite3.DatabaseError as exc:
                raise BackupError('cannot inspect MemoryStore key availability') from exc
        if vault is None and not encrypted_memory_data:
            return None
        if vault is None and vault_path.exists():
            try:
                vault = SecretVault.get_or_create_live(
                    vault_path, password=self.vault_password,
                    root_key_store=self.root_key_store,
                )
            except Exception as exc:
                raise BackupError('canonical SecretVault is unavailable for encrypted data backup') from exc
        if vault is None:
            if encrypted_memory_data:
                raise BackupError(
                    'encrypted MemoryStore data has no available canonical SecretVault'
                )
            return None
        encoded = vault.get(VAULT_KEY_NAME)
        if encoded is None:
            return None
        try:
            dek = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise BackupError('memory data-encryption key is invalid') from exc
        if len(dek) != 32:
            raise BackupError('memory data-encryption key is invalid')
        return self._wrap_memory_key(dek)

    def _identity_metadata(self) -> dict | None:
        """Read only stable owner identifiers; never include auth/device state."""
        path = self.data_dir / 'owner-access.sqlite3'
        if path.is_symlink():
            raise BackupError('owner identity metadata path is unsafe')
        if not path.is_file():
            return None
        try:
            with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
                table = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='owner_identity'"
                ).fetchone()
                if not table:
                    return None
                con.row_factory = sqlite3.Row
                row = con.execute(
                    '''SELECT owner_id,vishnu_id,first_name,last_name,display_name,
                              created_at,identity_version
                       FROM owner_identity WHERE singleton=1'''
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.DatabaseError as exc:
            raise BackupError('cannot read stable identity metadata for backup') from exc

    def _wrap_memory_key(self, dek: bytes) -> bytes:
        if len(dek) != 32:
            raise BackupError('memory data-encryption key is invalid')
        try:
            root_key = self.root_key_store.get_or_create()
        except (KeychainUnavailable, OSError, RuntimeError) as exc:
            raise BackupError('backup key authority is unavailable') from exc
        wrap_key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=b'vishnu-backup-memory-field-key-v1', info=MEMORY_KEY_INFO,
        ).derive(bytes(root_key))
        nonce = secrets.token_bytes(12)
        wrapped = AESGCM(wrap_key).encrypt(nonce, dek, MEMORY_KEY_AAD)
        return json.dumps({
            'version': 1,
            'cipher': 'AES-256-GCM',
            'nonce': base64.b64encode(nonce).decode('ascii'),
            'wrapped_key': base64.b64encode(wrapped).decode('ascii'),
        }, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def _unwrap_memory_key(self, envelope: bytes) -> bytes:
        try:
            obj = json.loads(envelope)
            if obj.get('version') != 1 or obj.get('cipher') != 'AES-256-GCM':
                raise ValueError('unsupported key envelope')
            nonce = base64.b64decode(obj['nonce'], validate=True)
            wrapped = base64.b64decode(obj['wrapped_key'], validate=True)
            if len(nonce) != 12 or len(wrapped) != 48:
                raise ValueError('invalid key envelope size')
            root_key = self.root_key_store.get_or_create()
            wrap_key = HKDF(
                algorithm=hashes.SHA256(), length=32,
                salt=b'vishnu-backup-memory-field-key-v1', info=MEMORY_KEY_INFO,
            ).derive(bytes(root_key))
            dek = AESGCM(wrap_key).decrypt(nonce, wrapped, MEMORY_KEY_AAD)
            if len(dek) != 32:
                raise ValueError('invalid data-encryption key size')
            return dek
        except (KeychainUnavailable, OSError, RuntimeError) as exc:
            raise BackupError('backup key authority is unavailable') from exc
        except Exception as exc:
            raise BackupError('memory data-encryption key envelope is invalid') from exc

    def _restore_memory_key(self, dek: bytes) -> None:
        try:
            vault = self.vault or SecretVault.get_or_create_live(
                self.data_dir / 'vault.json', password=self.vault_password,
                root_key_store=self.root_key_store,
            )
            vault.set(VAULT_KEY_NAME, base64.b64encode(dek).decode('ascii'))
        except Exception as exc:
            raise BackupError('memory data-encryption key restore failed') from exc

    def _derive_key(self, salt: bytes) -> bytes:
        try:
            root_key = self.root_key_store.get_or_create()
        except (KeychainUnavailable, OSError, RuntimeError) as exc:
            raise BackupError('backup encryption key is unavailable') from exc
        if not isinstance(root_key, (bytes, bytearray)) or len(root_key) != 32:
            raise BackupError('backup encryption key is invalid')
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=BACKUP_INFO,
        ).derive(bytes(root_key))

    @staticmethod
    def _canonical_header(header: dict) -> bytes:
        return json.dumps(header, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def _encrypt_payload(self, payload: Path, target: Path) -> None:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        header = {
            'version': BACKUP_VERSION,
            'cipher': 'AES-256-GCM',
            'kdf': 'HKDF-SHA256',
            'salt': base64.b64encode(salt).decode('ascii'),
            'nonce': base64.b64encode(nonce).decode('ascii'),
        }
        header_bytes = self._canonical_header(header)
        header_len = struct.pack('>I', len(header_bytes))
        aad = BACKUP_MAGIC + header_len + header_bytes
        key = self._derive_key(salt)
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(aad)

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f'.{target.name}.{secrets.token_hex(6)}.tmp')
        try:
            with payload.open('rb') as src, temp_target.open('wb') as dst:
                try:
                    os.chmod(temp_target, 0o600)
                except OSError:
                    pass
                dst.write(aad)
                for chunk in iter(lambda: src.read(COPY_CHUNK), b''):
                    dst.write(encryptor.update(chunk))
                dst.write(encryptor.finalize())
                dst.write(encryptor.tag)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(temp_target, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
        finally:
            temp_target.unlink(missing_ok=True)

    def _decrypt_payload(self, archive: Path) -> Path:
        archive = Path(archive)
        handle = tempfile.NamedTemporaryFile(
            prefix='personal-ai-backup-decrypted-', suffix='.zip', delete=False
        )
        temp_path = Path(handle.name)
        handle.close()
        try:
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            with archive.open('rb') as src:
                if src.read(len(BACKUP_MAGIC)) != BACKUP_MAGIC:
                    raise BackupError('unsupported encrypted backup format')
                raw_len = src.read(4)
                if len(raw_len) != 4:
                    raise BackupError('backup header is truncated')
                header_size = struct.unpack('>I', raw_len)[0]
                if header_size <= 0 or header_size > BACKUP_HEADER_MAX:
                    raise BackupError('backup header is invalid')
                header_bytes = src.read(header_size)
                if len(header_bytes) != header_size:
                    raise BackupError('backup header is truncated')
                try:
                    header = json.loads(header_bytes)
                    if (
                        int(header.get('version', 0)) != BACKUP_VERSION
                        or header.get('cipher') != 'AES-256-GCM'
                        or header.get('kdf') != 'HKDF-SHA256'
                    ):
                        raise ValueError('unsupported header')
                    salt = base64.b64decode(header['salt'], validate=True)
                    nonce = base64.b64decode(header['nonce'], validate=True)
                except Exception as exc:
                    raise BackupError('backup header is invalid') from exc
                if len(salt) != 16 or len(nonce) != 12:
                    raise BackupError('backup header is invalid')

                ciphertext_start = src.tell()
                archive_size = archive.stat().st_size
                ciphertext_size = archive_size - ciphertext_start - BACKUP_TAG_BYTES
                if ciphertext_size < 0:
                    raise BackupError('backup ciphertext is truncated')
                src.seek(archive_size - BACKUP_TAG_BYTES)
                tag = src.read(BACKUP_TAG_BYTES)
                if len(tag) != BACKUP_TAG_BYTES:
                    raise BackupError('backup authentication tag is missing')
                src.seek(ciphertext_start)

                aad = BACKUP_MAGIC + raw_len + header_bytes
                key = self._derive_key(salt)
                decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
                decryptor.authenticate_additional_data(aad)
                remaining = ciphertext_size
                with temp_path.open('wb') as dst:
                    while remaining:
                        chunk = src.read(min(COPY_CHUNK, remaining))
                        if not chunk:
                            raise BackupError('backup ciphertext is truncated')
                        remaining -= len(chunk)
                        dst.write(decryptor.update(chunk))
                    try:
                        dst.write(decryptor.finalize())
                    except InvalidTag as exc:
                        raise BackupError('backup authentication failed') from exc
                    dst.flush()
                    os.fsync(dst.fileno())
            return temp_path
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _build_payload(self, payload: Path) -> dict:
        stage = Path(tempfile.mkdtemp(prefix='personal-ai-backup-stage-'))
        try:
            manifest = {
                'version': BACKUP_VERSION,
                'created_at': time.time(),
                'encrypted': True,
                'cipher': 'AES-256-GCM',
                'files': [],
                'excludes': sorted(EXCLUDED_NAMES),
                'database_snapshot': 'sqlite-online-backup',
                # This is identity continuity metadata, not an authentication
                # database. The whole manifest is inside the encrypted archive.
                'identity_metadata': self._identity_metadata(),
            }
            for source in self._eligible():
                rel = source.relative_to(self.data_dir)
                snapshot = stage / rel
                self._snapshot_file(source, snapshot)
                manifest['files'].append({
                    'path': rel.as_posix(),
                    'sha256': self._sha(snapshot),
                    'size': snapshot.stat().st_size,
                })

            key_envelope = self._memory_key_envelope()
            if key_envelope is not None:
                envelope_path = stage / MEMORY_KEY_ENVELOPE
                envelope_path.parent.mkdir(parents=True, exist_ok=True)
                envelope_path.write_bytes(key_envelope)
                manifest['files'].append({
                    'path': MEMORY_KEY_ENVELOPE,
                    'sha256': hashlib.sha256(key_envelope).hexdigest(),
                    'size': len(key_envelope),
                    'purpose': 'restore encrypted MemoryStore fields',
                })

            with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for item in manifest['files']:
                    archive.write(stage / item['path'], item['path'])
                archive.writestr(
                    'manifest.json',
                    json.dumps(manifest, sort_keys=True, indent=2),
                )
            return manifest
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def create(self, name: str | None = None) -> Path:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        target = self.backup_dir / (name or f'personal-ai-{stamp}.paibackup')
        if target.suffix != '.paibackup':
            target = target.with_suffix('.paibackup')

        handle = tempfile.NamedTemporaryFile(
            prefix='personal-ai-backup-payload-', suffix='.zip', delete=False
        )
        payload = Path(handle.name)
        handle.close()
        try:
            try:
                os.chmod(payload, 0o600)
            except OSError:
                pass
            self._build_payload(payload)
            self._encrypt_payload(payload, target)
            return target
        finally:
            payload.unlink(missing_ok=True)

    @staticmethod
    def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
        mode = (info.external_attr >> 16) & 0o170000
        return mode == stat.S_IFLNK

    def _inspect_zip(self, payload: Path, *, encrypted: bool) -> dict:
        try:
            with zipfile.ZipFile(payload) as archive:
                infos = [item for item in archive.infolist() if not item.is_dir()]
                if len({item.filename for item in infos}) != len(infos):
                    raise BackupError('backup contains duplicate payload paths')
                for info in infos:
                    self._safe_rel(info.filename)
                    if self._zip_member_is_symlink(info):
                        raise BackupError('backup contains a symbolic link')
                names = {item.filename for item in infos}
                try:
                    manifest = json.loads(archive.read('manifest.json'))
                except Exception as exc:
                    raise BackupError('backup manifest missing or invalid') from exc
                version = int(manifest.get('version', 0))
                if version not in {1, BACKUP_VERSION} or not isinstance(manifest.get('files'), list):
                    raise BackupError('unsupported backup manifest')
                if version >= BACKUP_VERSION and not encrypted:
                    raise BackupError('encrypted backup manifest is not inside an encrypted envelope')
                identity = manifest.get('identity_metadata')
                if identity is not None:
                    try:
                        valid_identity = (
                            isinstance(identity, dict)
                            and re.fullmatch(r'OWNER-[0-9A-F]{32}', str(identity['owner_id']))
                            and re.fullmatch(r'VISHNU-[0-9A-F]{32}', str(identity['vishnu_id']))
                            and bool(str(identity['first_name']).strip())
                            and bool(str(identity['display_name']).strip())
                            and int(identity['identity_version']) >= 1
                        )
                    except (KeyError, TypeError, ValueError):
                        valid_identity = False
                    if not valid_identity:
                        raise BackupError('backup identity metadata is invalid')

                listed: dict[str, dict] = {}
                for item in manifest['files']:
                    if not isinstance(item, dict) or 'path' not in item:
                        raise BackupError('backup manifest contains an invalid file record')
                    rel = self._safe_rel(str(item['path'])).as_posix()
                    if rel in listed:
                        raise BackupError('backup manifest contains duplicate file records')
                    listed[rel] = item
                expected = set(listed) | {'manifest.json'}
                if names != expected:
                    raise BackupError('backup contains unlisted or missing payloads')

                for rel, item in listed.items():
                    path = Path(rel)
                    if path.name in EXCLUDED_NAMES:
                        raise BackupError('backup contains forbidden secret file')
                    if path.name.endswith(SQLITE_SIDECARS):
                        raise BackupError('backup contains forbidden SQLite sidecar')
                    if any(part.lower() in EXCLUDED_DIRS for part in path.parts[:-1]):
                        raise BackupError('backup contains excluded runtime directory')
                    data = archive.read(rel)
                    try:
                        expected_size = int(item['size'])
                        expected_sha = str(item['sha256'])
                    except Exception as exc:
                        raise BackupError('backup manifest contains invalid integrity metadata') from exc
                    if len(data) != expected_size:
                        raise BackupError(f'backup size mismatch: {rel}')
                    if hashlib.sha256(data).hexdigest() != expected_sha:
                        raise BackupError(f'backup integrity failure: {rel}')

                result = dict(manifest)
                result['encrypted'] = bool(encrypted)
                return result
        except zipfile.BadZipFile as exc:
            raise BackupError('backup payload is not a valid archive') from exc

    def _payload_for_read(
        self, archive: Path,
    ) -> tuple[Path, bool, bool]:
        archive = Path(archive)
        try:
            with archive.open('rb') as handle:
                prefix = handle.read(len(BACKUP_MAGIC))
        except OSError as exc:
            raise BackupError('backup cannot be opened') from exc
        if prefix == BACKUP_MAGIC:
            return self._decrypt_payload(archive), True, True
        if zipfile.is_zipfile(archive):
            return archive, False, False
        raise BackupError('unsupported backup format')

    def inspect(self, archive: Path) -> dict:
        payload, encrypted, cleanup = self._payload_for_read(Path(archive))
        try:
            return self._inspect_zip(payload, encrypted=encrypted)
        finally:
            if cleanup:
                payload.unlink(missing_ok=True)

    @staticmethod
    def _copy_fsynced(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, destination.open('wb') as dst:
            shutil.copyfileobj(src, dst, COPY_CHUNK)
            dst.flush()
            os.fsync(dst.fileno())
        try:
            shutil.copystat(source, destination)
        except OSError:
            pass

    def restore(self, archive: Path) -> dict:
        payload, encrypted, cleanup_payload = self._payload_for_read(Path(archive))
        stage = Path(tempfile.mkdtemp(prefix='personal-ai-restore-'))
        rollback = Path(tempfile.mkdtemp(prefix='personal-ai-restore-rollback-'))
        touched: list[tuple[Path, Path | None]] = []
        try:
            manifest = self._inspect_zip(payload, encrypted=encrypted)
            identity = manifest.get('identity_metadata')
            identity_store = self.data_dir / 'owner-access.sqlite3'
            if identity is not None and identity_store.is_file():
                from security.owner_access import OwnerAccessStore
                current_identity = OwnerAccessStore(identity_store).identity()
                if current_identity and (
                    current_identity['owner_id'] != identity['owner_id']
                    or current_identity['vishnu_id'] != identity['vishnu_id']
                ):
                    raise BackupError('backup belongs to a different Vishnu identity')
            with zipfile.ZipFile(payload) as zipped:
                for item in manifest['files']:
                    rel = self._safe_rel(item['path'])
                    staged = (stage / rel).resolve()
                    if stage.resolve() not in staged.parents:
                        raise BackupError('unsafe restore path')
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    staged.write_bytes(zipped.read(item['path']))

            memory_key = None
            memory_key_path = stage / MEMORY_KEY_ENVELOPE
            if memory_key_path.exists():
                memory_key = self._unwrap_memory_key(memory_key_path.read_bytes())

            destinations: list[tuple[Path, Path, Path]] = []
            skipped_security_state: list[str] = []
            for item in manifest['files']:
                rel = self._safe_rel(item['path'])
                if rel.as_posix() == MEMORY_KEY_ENVELOPE:
                    continue
                staged = stage / rel
                if staged.suffix.lower() in SQLITE_SUFFIXES:
                    self._sqlite_integrity(staged)
                if rel.name in NON_RESTORABLE_SECURITY_NAMES:
                    skipped_security_state.append(rel.as_posix())
                    continue
                destination = self._safe_destination(rel)
                destinations.append((rel, staged, destination))

            # Snapshot all existing targets before mutating anything. If any
            # snapshot fails, the restore aborts with owner state untouched.
            for rel, _, destination in destinations:
                rollback_copy = None
                if destination.exists():
                    if not destination.is_file() or destination.is_symlink():
                        raise BackupError(f'unsafe restore destination: {rel.as_posix()}')
                    rollback_copy = rollback / rel
                    if (destination.suffix.lower() in SQLITE_SUFFIXES
                            and self._is_valid_sqlite(destination)):
                        self._snapshot_sqlite(destination, rollback_copy)
                    else:
                        self._copy_fsynced(destination, rollback_copy)
                touched.append((destination, rollback_copy))

            restored = 0
            try:
                for _, source, destination in destinations:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temp_destination = destination.with_name(
                        f'.{destination.name}.{secrets.token_hex(6)}.restore'
                    )
                    try:
                        if (source.suffix.lower() in SQLITE_SUFFIXES and destination.exists()
                                and self._is_valid_sqlite(destination)):
                            self._restore_sqlite_snapshot(source, destination)
                        elif source.suffix.lower() in SQLITE_SUFFIXES and destination.exists():
                            # A corrupt/non-SQLite legacy file cannot be updated
                            # through SQLite's backup API. Preserve a byte-for-
                            # byte rollback copy above, then rewrite in place;
                            # replacing a file can be denied on Windows even
                            # when no SQLite connection can consume it.
                            self._copy_fsynced(source, destination)
                        else:
                            self._copy_fsynced(source, temp_destination)
                            os.replace(temp_destination, destination)
                        restored += 1
                    finally:
                        temp_destination.unlink(missing_ok=True)
                if memory_key is not None:
                    self._restore_memory_key(memory_key)
                if identity is not None:
                    from security.owner_access import OwnerAccessStore
                    OwnerAccessStore(self.data_dir / 'owner-access.sqlite3').restore_identity_metadata(identity)
            except Exception as exc:
                rollback_errors = []
                for destination, rollback_copy in reversed(touched[:restored]):
                    try:
                        if rollback_copy is None:
                            destination.unlink(missing_ok=True)
                        else:
                            if (destination.suffix.lower() in SQLITE_SUFFIXES and destination.exists()
                                    and self._is_valid_sqlite(rollback_copy)):
                                self._restore_sqlite_snapshot(rollback_copy, destination)
                            elif destination.suffix.lower() in SQLITE_SUFFIXES and destination.exists():
                                self._copy_fsynced(rollback_copy, destination)
                            else:
                                rollback_temp = destination.with_name(
                                    f'.{destination.name}.{secrets.token_hex(6)}.rollback'
                                )
                                try:
                                    self._copy_fsynced(rollback_copy, rollback_temp)
                                    os.replace(rollback_temp, destination)
                                finally:
                                    rollback_temp.unlink(missing_ok=True)
                    except Exception as rollback_exc:  # pragma: no cover - catastrophic filesystem failure
                        rollback_errors.append(f'{destination}: {rollback_exc}')
                if rollback_errors:
                    raise BackupError(
                        'restore failed and rollback was incomplete: ' + '; '.join(rollback_errors)
                    ) from exc
                raise BackupError('restore failed; original owner state was rolled back') from exc

            return {
                'ok': True,
                'restored': restored,
                'created_at': manifest['created_at'],
                'encrypted': bool(encrypted),
                'skipped_security_state': sorted(skipped_security_state),
                'identity_preserved': bool(manifest.get('identity_metadata')),
            }
        finally:
            shutil.rmtree(stage, ignore_errors=True)
            shutil.rmtree(rollback, ignore_errors=True)
            if cleanup_payload:
                payload.unlink(missing_ok=True)
