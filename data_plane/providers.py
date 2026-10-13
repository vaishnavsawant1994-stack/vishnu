from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    label: str
    category: str
    cloud: bool
    credential_kind: str | None = None
    notes: str = ''


BUILTIN_PROVIDERS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor('local', 'This device', 'local', False),
    ProviderDescriptor('google_drive', 'Google Drive', 'files', True, 'connector', 'Use the governed Google connection; credentials never belong in data-plane metadata.'),
    ProviderDescriptor('dropbox', 'Dropbox', 'files', True, 'connector'),
    ProviderDescriptor('onedrive', 'Microsoft OneDrive', 'files', True, 'connector'),
    ProviderDescriptor('icloud_bridge', 'Apple iCloud', 'files', True, 'native_bridge', 'Requires a supported Apple-native bridge; fail closed when unavailable.'),
    ProviderDescriptor('s3', 'Amazon S3 / S3-compatible', 'files_backup', True, 'vault'),
    ProviderDescriptor('cloudflare_r2', 'Cloudflare R2', 'files_backup', True, 'vault'),
    ProviderDescriptor('backblaze_b2', 'Backblaze B2', 'files_backup', True, 'vault'),
    ProviderDescriptor('postgres', 'PostgreSQL', 'database', True, 'vault'),
    ProviderDescriptor('supabase', 'Supabase Postgres', 'database', True, 'vault'),
    ProviderDescriptor('neon', 'Neon Postgres', 'database', True, 'vault'),
    ProviderDescriptor('aws_rds', 'AWS RDS PostgreSQL', 'database', True, 'vault'),
    ProviderDescriptor('vishnu_cloud', 'Vishnu Cloud', 'database_files_backup', True, 'managed', 'Reserved for the governed Vishnu-managed service; unavailable until provisioned.'),
)


class ProviderRegistry:
    """Canonical provider catalogue.

    A provider being listed here does not mean it is connected. Connection state
    is recorded separately by UnifiedDataPlane only after a real connector,
    native bridge, managed service, or vault-backed adapter is configured.
    """

    def __init__(self, descriptors: Iterable[ProviderDescriptor] = BUILTIN_PROVIDERS):
        self._providers = {item.provider_id: item for item in descriptors}

    def get(self, provider_id: str) -> ProviderDescriptor:
        try:
            return self._providers[str(provider_id)]
        except KeyError as exc:
            raise KeyError(f'unknown storage provider: {provider_id}') from exc

    def list(self) -> list[dict]:
        return [item.__dict__.copy() for item in self._providers.values()]

    def assert_allowed(self, provider_id: str, *, cloud_enabled: bool) -> ProviderDescriptor:
        item = self.get(provider_id)
        if item.cloud and not cloud_enabled:
            raise PermissionError('online/cloud storage is disabled by owner policy')
        return item
