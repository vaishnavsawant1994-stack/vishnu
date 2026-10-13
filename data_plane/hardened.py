from __future__ import annotations

import json
import secrets
from typing import Any, Mapping

from .enforced import PolicyEnforcedDataPlane
from .manager import _json, _now


class HardenedDataPlane(PolicyEnforcedDataPlane):
    """Production-facing hardening around the canonical policy-enforced plane.

    This layer deliberately reuses the existing DeviceRegistry, DeviceGateway,
    approval/tool authority and persistence model. It adds explicit data scopes,
    schema migration evidence and a verified durable-copy removal workflow.
    """

    SCHEMA_VERSION = 2
    DATA_READ_SCOPE = 'data:read'
    DATA_SYNC_SCOPE = 'data:sync'
    DATA_ADMIN_SCOPE = 'data:admin'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._migrate_schema()

    def _migrate_schema(self):
        with self._lock, self._con() as con:
            row = con.execute(
                'SELECT schema_version FROM data_plane_settings WHERE singleton=1'
            ).fetchone()
            current = int(row['schema_version']) if row is not None else 0
            if current > self.SCHEMA_VERSION:
                raise RuntimeError('data-plane schema is newer than this Vishnu runtime')
            con.executescript(
                '''
                CREATE TABLE IF NOT EXISTS data_plane_schema_migrations(
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_plane_copy_removals(
                    removal_id TEXT PRIMARY KEY,
                    global_id TEXT NOT NULL,
                    location_type TEXT NOT NULL,
                    location_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    verified_at TEXT,
                    verification_ref TEXT,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_data_plane_copy_removals_item
                    ON data_plane_copy_removals(global_id,verified_at);
                '''
            )
            if current < self.SCHEMA_VERSION:
                con.execute(
                    'UPDATE data_plane_settings SET schema_version=?,updated_at=? WHERE singleton=1',
                    (self.SCHEMA_VERSION, _now()),
                )
            con.execute(
                'INSERT OR IGNORE INTO data_plane_schema_migrations(version,applied_at) VALUES(?,?)',
                (self.SCHEMA_VERSION, _now()),
            )

    def _require_scope(self, device_id: str, scope: str):
        device_id = str(device_id or '').strip()
        if not device_id:
            raise ValueError('device_id is required')
        if self.device_registry is None:
            return
        if not self.device_registry.is_active(device_id):
            raise PermissionError('trusted active device required')
        if hasattr(self.device_registry, 'authorize') and not self.device_registry.authorize(device_id, scope):
            raise PermissionError(f'device is not permitted for {scope}')

    def grant_remote_access(
        self,
        global_id: str,
        *,
        requester_device_id: str,
        purpose: str = 'view',
        allow_persist: bool = False,
        ttl_seconds: int = 120,
    ) -> dict[str, Any]:
        item = self.item(global_id)
        source_device_id = str(item['primary_device_id'])
        self._require_scope(requester_device_id, self.DATA_READ_SCOPE)
        self._require_scope(source_device_id, self.DATA_READ_SCOPE)
        lease = super().grant_remote_access(
            global_id,
            requester_device_id=requester_device_id,
            purpose=purpose,
            allow_persist=allow_persist,
            ttl_seconds=ttl_seconds,
        )
        # These directives are mandatory for any future raw/derived streaming
        # transport consuming this lease. The lease itself never materializes data.
        return {
            **lease,
            'cache_policy': 'no_store',
            'index_allowed': False,
            'backup_allowed': False,
            'offline_copy_allowed': bool(lease['persist_allowed']),
        }

    def validate_remote_lease(self, lease_id: str, *, require_persist: bool = False) -> dict[str, Any]:
        lease = super().validate_remote_lease(lease_id, require_persist=require_persist)
        self._require_scope(lease['requester_device_id'], self.DATA_READ_SCOPE)
        self._require_scope(lease['source_device_id'], self.DATA_READ_SCOPE)
        return {
            **lease,
            'cache_policy': 'no_store',
            'index_allowed': False,
            'backup_allowed': False,
            'offline_copy_allowed': bool(lease['persist_allowed']),
        }

    def receive_sync_event(self, device_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        self._require_scope(device_id, self.DATA_SYNC_SCOPE)
        origin = str(event.get('origin_device_id') or '').strip()
        if origin:
            self._require_scope(origin, self.DATA_SYNC_SCOPE)
        return super().receive_sync_event(device_id, event)

    def pending_progress_events(self, device_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        self._require_scope(device_id, self.DATA_SYNC_SCOPE)
        return super().pending_progress_events(device_id, limit=limit)

    def acknowledge_sync_event(self, device_id: str, event_id: str) -> bool:
        self._require_scope(device_id, self.DATA_SYNC_SCOPE)
        return super().acknowledge_sync_event(device_id, event_id)

    def begin_copy_removal(
        self,
        global_id: str,
        *,
        location_type: str,
        location_id: str,
    ) -> dict[str, Any]:
        """Record intent to remove a durable copy without claiming it is gone."""
        item = self.item(global_id)
        primary = str(item['primary_device_id'])
        matches = [
            location
            for location in item['locations']
            if location['location_type'] == str(location_type)
            and location['location_id'] == str(location_id)
            and location['has_bytes']
        ]
        if not matches:
            raise KeyError('durable data location not found')
        location = matches[0]
        if (
            location['location_type'] == 'device'
            and location['location_id'] == primary
            and location['provider_id'] == 'local'
        ):
            raise PermissionError('primary authoritative copy cannot be removed by copy-removal workflow')
        removal_id = secrets.token_urlsafe(24)
        with self._con() as con:
            con.execute(
                '''INSERT INTO data_plane_copy_removals(
                   removal_id,global_id,location_type,location_id,provider_id,requested_at,verified_at,verification_ref
                   ) VALUES(?,?,?,?,?,?,NULL,NULL)''',
                (
                    removal_id,
                    str(global_id),
                    location['location_type'],
                    location['location_id'],
                    location['provider_id'],
                    _now(),
                ),
            )
        self._emit(
            'data_plane.copy_removal_requested',
            global_id=str(global_id),
            removal_id=removal_id,
            location_type=location['location_type'],
            location_id=location['location_id'],
        )
        return {
            'removal_id': removal_id,
            'global_id': str(global_id),
            'location_type': location['location_type'],
            'location_id': location['location_id'],
            'provider_id': location['provider_id'],
            'verified': False,
        }

    def confirm_copy_removal(self, removal_id: str, *, verification_ref: str) -> dict[str, Any]:
        """Forget a location only after the owning adapter independently verified deletion."""
        verification_ref = str(verification_ref or '').strip()
        if not verification_ref or len(verification_ref) > 500:
            raise ValueError('bounded verification_ref is required')
        with self._lock, self._con() as con:
            row = con.execute(
                'SELECT * FROM data_plane_copy_removals WHERE removal_id=?',
                (str(removal_id),),
            ).fetchone()
            if row is None:
                raise KeyError('copy-removal request not found')
            if row['verified_at'] is not None:
                return self.copy_removal_status(removal_id)
            location = con.execute(
                '''SELECT provider_id,has_bytes FROM data_plane_locations
                   WHERE global_id=? AND location_type=? AND location_id=?''',
                (row['global_id'], row['location_type'], row['location_id']),
            ).fetchone()
            if location is None or not bool(location['has_bytes']):
                raise RuntimeError('durable location changed before deletion verification')
            if str(location['provider_id']) != str(row['provider_id']):
                raise RuntimeError('provider changed before deletion verification')
            con.execute(
                '''DELETE FROM data_plane_locations
                   WHERE global_id=? AND location_type=? AND location_id=?''',
                (row['global_id'], row['location_type'], row['location_id']),
            )
            con.execute(
                '''UPDATE data_plane_copy_removals SET verified_at=?,verification_ref=?
                   WHERE removal_id=?''',
                (_now(), verification_ref, str(removal_id)),
            )
        self._emit(
            'data_plane.copy_removal_verified',
            global_id=str(row['global_id']),
            removal_id=str(removal_id),
        )
        return self.copy_removal_status(removal_id)

    def copy_removal_status(self, removal_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute(
                'SELECT * FROM data_plane_copy_removals WHERE removal_id=?',
                (str(removal_id),),
            ).fetchone()
        if row is None:
            raise KeyError('copy-removal request not found')
        result = dict(row)
        result['verified'] = result.pop('verified_at') is not None
        return result

    def diagnostics(self) -> dict[str, Any]:
        base = super().diagnostics()
        with self._con() as con:
            migrations = [
                int(row['version'])
                for row in con.execute(
                    'SELECT version FROM data_plane_schema_migrations ORDER BY version'
                ).fetchall()
            ]
            pending_removals = con.execute(
                'SELECT COUNT(*) FROM data_plane_copy_removals WHERE verified_at IS NULL'
            ).fetchone()[0]
        return {
            **base,
            'schema_migrations': migrations,
            'pending_copy_removals': int(pending_removals),
            'data_access_scopes': {
                'read': self.DATA_READ_SCOPE,
                'sync': self.DATA_SYNC_SCOPE,
                'admin': self.DATA_ADMIN_SCOPE,
            },
            'remote_cache_policy': 'no_store',
        }
