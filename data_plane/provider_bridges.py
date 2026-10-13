from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path
from typing import Any, Mapping

from integrations.contracts import ConnectorOperation

from .provider_adapters import (
    MAX_PROVIDER_OBJECT_BYTES,
    ProviderAdapterError,
    ProviderAdapterFactory,
    ProviderObjectInfo,
)


_DRIVE_FILE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
_DRIVE_DELETE_OPERATION = ConnectorOperation(
    name='drive.files.data_plane_delete',
    effect='destructive',
    risk='destructive',
    approval='required',
    requires_reauth=True,
    required_scopes=(_DRIVE_FILE_SCOPE,),
    allowed_data_classifications=('public', 'internal', 'sensitive'),
    prohibited_data_classifications=('secret', 'restricted'),
    destination_types=('drive_file',),
    idempotency_supported=True,
    verification_supported=True,
    rollback_available=False,
)


def _validated_object_key(value: str) -> str:
    key = str(value or '').strip().lstrip('/')
    if not key or len(key) > 900 or '\x00' in key or any(part == '..' for part in key.split('/')):
        raise ValueError('invalid provider object key')
    return key


class CanonicalGoogleDriveObjectAdapter:
    """Ciphertext object bridge over Vishnu's existing governed Drive adapter.

    This class never receives or stores a Google OAuth token. It delegates every
    provider request to the already-connected canonical integration adapter.
    Object names are hashes so data-plane identifiers are not leaked into Drive.
    """

    PROVIDER_MIME = 'application/json'

    def __init__(self, *, provider_id: str, config: Mapping[str, Any], drive_adapter: Any):
        if drive_adapter is None:
            raise ProviderAdapterError('canonical Google Drive integration is unavailable')
        self.provider_id = str(provider_id)
        self.config = dict(config or {})
        self.drive = drive_adapter
        self.account_ref = str(self.config.get('account_ref') or 'integration:drive')
        self.parent_id = str(self.config.get('parent_id') or '').strip() or None
        self.max_bytes = min(
            MAX_PROVIDER_OBJECT_BYTES,
            int(getattr(self.drive, 'MAX_FILE_BYTES', 10 * 1024 * 1024)),
        )

    @staticmethod
    def _name(object_key: str) -> str:
        key = _validated_object_key(object_key)
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return f'vishnu-{digest}.json'

    @staticmethod
    def _request_id(prefix: str, object_key: str) -> str:
        digest = hashlib.sha256(_validated_object_key(object_key).encode('utf-8')).hexdigest()
        return f'data-plane:{prefix}:{digest}'

    def _query(self, object_key: str) -> str:
        return f"name = '{self._name(object_key)}' and trashed = false"

    def _find(self, object_key: str) -> dict[str, Any] | None:
        result = self.drive.list_files(q=self._query(object_key), page_size=3)
        files = result.get('files') if isinstance(result, dict) else None
        if not isinstance(files, list):
            raise ProviderAdapterError('canonical Google Drive adapter returned invalid metadata')
        exact = [item for item in files if isinstance(item, dict) and item.get('name') == self._name(object_key)]
        if len(exact) > 1:
            raise ProviderAdapterError('duplicate Google Drive data-plane object is ambiguous')
        return exact[0] if exact else None

    def verify(self) -> dict[str, Any]:
        result = self.drive.list_files(page_size=1)
        if not isinstance(result, dict):
            raise ProviderAdapterError('canonical Google Drive integration did not verify')
        return {'ok': True, 'provider_id': self.provider_id, 'authority': 'canonical_integration'}

    def put(self, object_key: str, payload: bytes, *, content_type: str = 'application/octet-stream') -> ProviderObjectInfo:
        key = _validated_object_key(object_key)
        data = bytes(payload)
        if len(data) > self.max_bytes:
            raise ValueError('Google Drive object exceeds canonical connector byte limit')
        existing = self._find(key)
        if existing is None:
            result = self.drive.upload_file(
                self._name(key),
                self.PROVIDER_MIME,
                data,
                parent_id=self.parent_id,
                provider_account=self.account_ref,
                request_id=self._request_id('create', key),
            )
        else:
            result = self.drive.update_content(
                str(existing['id']),
                self.PROVIDER_MIME,
                data,
                expected_version=str(existing.get('version') or ''),
                provider_account=self.account_ref,
                request_id=self._request_id('update', key),
            )
        verification = result.get('verification') if isinstance(result, dict) else None
        file_id = str((verification or {}).get('provider_file_id') or result.get('id') or (existing or {}).get('id') or '')
        etag = str((verification or {}).get('version') or result.get('version') or '') or None
        if not file_id:
            raise ProviderAdapterError('Google Drive write did not return verified provider identity')
        return ProviderObjectInfo(key, size=len(data), etag=etag, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        key = _validated_object_key(object_key)
        existing = self._find(key)
        if existing is None:
            raise FileNotFoundError(key)
        result = self.drive.read_file(str(existing['id']))
        data = result.get('content') if isinstance(result, dict) else None
        if not isinstance(data, (bytes, bytearray)):
            raise ProviderAdapterError('Google Drive object content is unavailable')
        data = bytes(data)
        if len(data) > self.max_bytes:
            raise ProviderAdapterError('Google Drive object exceeds canonical connector byte limit')
        return data

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        key = _validated_object_key(object_key)
        existing = self._find(key)
        if existing is None:
            return None
        size = existing.get('size')
        return ProviderObjectInfo(
            key,
            size=int(size) if size not in {None, ''} else None,
            etag=str(existing.get('version') or '') or None,
            content_type=str(existing.get('mimeType') or '') or None,
        )

    def delete(self, object_key: str) -> bool:
        key = _validated_object_key(object_key)
        existing = self._find(key)
        if existing is None:
            return False
        file_id = str(existing.get('id') or '')
        if not file_id:
            raise ProviderAdapterError('Google Drive object identity is unavailable')
        result = self.drive.request(
            'DELETE',
            f'files/{file_id}',
            operation=_DRIVE_DELETE_OPERATION,
            operation_parameters={
                'file_id': file_id,
                'object_key_hash': hashlib.sha256(key.encode('utf-8')).hexdigest(),
                'provider_account': self.account_ref,
            },
            destination=file_id,
            idempotency_key=self._request_id('delete', key),
            provider_account=self.account_ref,
        )
        if self._find(key) is not None:
            raise ProviderAdapterError('Google Drive did not verify encrypted object deletion')
        operation_id = result.get('_personal_ai_operation_id') if isinstance(result, dict) else None
        gateway = getattr(self.drive, 'gateway', None)
        if operation_id and gateway is not None:
            gateway.state.transition_operation(
                operation_id,
                'verified',
                verification_state='verified',
                verification_evidence={'provider_file_id': file_id, 'deleted': True, 'rollback_available': False},
            )
            gateway.state.audit(
                'verification.succeeded',
                connector_id='drive',
                correlation_id=operation_id,
                payload={'operation': _DRIVE_DELETE_OPERATION.name, 'provider_file_id': file_id, 'deleted': True},
            )
        return True


class ICloudDriveFilesystemBridgeAdapter:
    """Apple-host-only bridge to an explicitly owner-configured iCloud Drive root.

    The root path is supplied by runtime configuration and is never persisted in
    data-plane provider metadata. Only encrypted Vishnu provider packages should
    be passed to this adapter by EncryptedProviderStore.
    """

    def __init__(self, *, provider_id: str, bridge_root: str | os.PathLike[str]):
        if platform.system() != 'Darwin':
            raise ProviderAdapterError('Apple iCloud bridge is only available on supported Apple hosts')
        root = Path(bridge_root).expanduser()
        if not root.is_absolute():
            raise ProviderAdapterError('Apple iCloud bridge root must be an absolute owner-configured path')
        try:
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise ProviderAdapterError('Apple iCloud bridge root is unavailable') from exc
        if not resolved.is_dir():
            raise ProviderAdapterError('Apple iCloud bridge root is not a directory')
        self.provider_id = str(provider_id)
        self.root = resolved

    @staticmethod
    def _relative(object_key: str) -> Path:
        key = _validated_object_key(object_key)
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return Path('Vishnu') / 'EncryptedObjects' / digest[:2] / f'{digest}.vishnu'

    def _path(self, object_key: str) -> Path:
        candidate = (self.root / self._relative(object_key)).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ProviderAdapterError('Apple iCloud bridge path escaped configured root') from exc
        return candidate

    def verify(self) -> dict[str, Any]:
        if not os.access(self.root, os.R_OK | os.W_OK):
            raise ProviderAdapterError('Apple iCloud bridge root is not readable and writable')
        return {'ok': True, 'provider_id': self.provider_id, 'authority': 'native_runtime_bridge'}

    def put(self, object_key: str, payload: bytes, *, content_type: str = 'application/octet-stream') -> ProviderObjectInfo:
        key = _validated_object_key(object_key)
        data = bytes(payload)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ValueError('Apple iCloud bridge object exceeds bounded data-plane limit')
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f'.{target.name}.tmp-{os.getpid()}')
        try:
            with open(temporary, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
        return ProviderObjectInfo(key, size=len(data), etag=hashlib.sha256(data).hexdigest(), content_type=content_type)

    def get(self, object_key: str) -> bytes:
        key = _validated_object_key(object_key)
        target = self._path(key)
        try:
            size = target.stat().st_size
        except FileNotFoundError:
            raise FileNotFoundError(key)
        if size > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError('Apple iCloud bridge object exceeds bounded data-plane limit')
        return target.read_bytes()

    def delete(self, object_key: str) -> bool:
        target = self._path(object_key)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        return True

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        key = _validated_object_key(object_key)
        target = self._path(key)
        try:
            stat = target.stat()
        except FileNotFoundError:
            return None
        if stat.st_size > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError('Apple iCloud bridge object exceeds bounded data-plane limit')
        return ProviderObjectInfo(key, size=int(stat.st_size), content_type='application/vnd.vishnu.encrypted+json')


class GovernedProviderAdapterFactory(ProviderAdapterFactory):
    """Adds canonical integration/native bridges without duplicating credentials."""

    def __init__(self, manager, vault, *, runtime: Mapping[str, Any], client_factory=None):
        super().__init__(manager, vault, client_factory=client_factory)
        self.runtime = runtime

    def build(self, provider_id: str):
        provider_id = str(provider_id)
        status = self.manager.provider_status(provider_id)
        if not status.get('available'):
            raise PermissionError('online storage provider is not connected, enabled, and verified')
        reference = str(status.get('credential_ref') or '')
        if provider_id == 'google_drive':
            if reference != 'integration:drive':
                raise ProviderAdapterError('Google Drive must use the canonical integration reference')
            drive = (self.runtime.get('integration_adapters') or {}).get('drive')
            return CanonicalGoogleDriveObjectAdapter(
                provider_id=provider_id,
                config=status.get('config') or {},
                drive_adapter=drive,
            )
        if provider_id == 'icloud_bridge':
            if reference not in {'', 'native:icloud_bridge'}:
                raise ProviderAdapterError('Apple iCloud must use the canonical native bridge reference')
            root = (self.runtime.get('native_storage_bridges') or {}).get('icloud_bridge')
            if root is None:
                raise ProviderAdapterError('Apple iCloud native bridge is unavailable')
            return ICloudDriveFilesystemBridgeAdapter(provider_id=provider_id, bridge_root=root)
        return super().build(provider_id)
