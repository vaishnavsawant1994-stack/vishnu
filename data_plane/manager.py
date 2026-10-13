from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .policy import BackupMode, CloudMode, StoragePolicy, contains_secret_or_raw_content, progress_projection
from .providers import ProviderRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


class UnifiedDataPlane:
    """Local-first location, sync-policy and remote-access authority.

    This does not replace Vishnu's domain databases. It records where domain
    objects are allowed to live and which bounded metadata may move between
    trusted devices. Actual domain writes remain owned by their existing stores.
    """

    SCHEMA_VERSION = 1
    MAX_METADATA_BYTES = 64 * 1024
    MAX_LEASE_SECONDS = 300

    def __init__(self, path: Path, *, device_registry=None, device_gateway=None, events=None, providers=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.device_registry = device_registry
        self.device_gateway = device_gateway
        self.events = events
        self.providers = providers or ProviderRegistry()
        self._lock = RLock()
        self._init_db()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=30000')
        return con

    def _init_db(self):
        with self._con() as con:
            con.executescript(
                '''
                CREATE TABLE IF NOT EXISTS data_plane_settings(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    schema_version INTEGER NOT NULL,
                    cloud_enabled INTEGER NOT NULL DEFAULT 0,
                    cloud_mode TEXT NOT NULL DEFAULT 'local_only',
                    remote_access_enabled INTEGER NOT NULL DEFAULT 1,
                    default_policy TEXT NOT NULL DEFAULT 'progress_only',
                    encrypted_backup_enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO data_plane_settings(
                    singleton,schema_version,cloud_enabled,cloud_mode,
                    remote_access_enabled,default_policy,encrypted_backup_enabled,updated_at
                ) VALUES(1,1,0,'local_only',1,'progress_only',0,'1970-01-01T00:00:00+00:00');

                CREATE TABLE IF NOT EXISTS data_plane_items(
                    global_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    primary_device_id TEXT NOT NULL,
                    storage_policy TEXT NOT NULL,
                    remote_access_allowed INTEGER NOT NULL,
                    copy_allowed INTEGER NOT NULL,
                    backup_mode TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    origin_device_id TEXT NOT NULL,
                    content_digest TEXT,
                    tombstone INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_plane_locations(
                    global_id TEXT NOT NULL,
                    location_type TEXT NOT NULL,
                    location_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    has_bytes INTEGER NOT NULL,
                    available INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(global_id,location_type,location_id),
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS data_plane_sync_events(
                    event_id TEXT PRIMARY KEY,
                    global_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    origin_device_id TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS data_plane_sync_receipts(
                    device_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    PRIMARY KEY(device_id,event_id)
                );
                CREATE TABLE IF NOT EXISTS data_plane_conflicts(
                    conflict_id TEXT PRIMARY KEY,
                    global_id TEXT NOT NULL,
                    local_version INTEGER NOT NULL,
                    incoming_version INTEGER NOT NULL,
                    incoming_event_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    resolved_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_plane_provider_configs(
                    provider_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    credential_ref TEXT,
                    config_json TEXT NOT NULL,
                    verified_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_plane_remote_leases(
                    lease_id TEXT PRIMARY KEY,
                    global_id TEXT NOT NULL,
                    requester_device_id TEXT NOT NULL,
                    source_device_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    persist_allowed INTEGER NOT NULL DEFAULT 0,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_data_plane_events_item ON data_plane_sync_events(global_id,version);
                CREATE INDEX IF NOT EXISTS idx_data_plane_locations_item ON data_plane_locations(global_id);
                '''
            )

    def _emit(self, topic: str, **payload):
        if self.events is not None:
            try:
                self.events.emit(topic, **payload)
            except Exception:
                pass

    def settings(self) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute('SELECT * FROM data_plane_settings WHERE singleton=1').fetchone()
        return {
            'schema_version': int(row['schema_version']),
            'cloud_enabled': bool(row['cloud_enabled']),
            'cloud_mode': row['cloud_mode'],
            'remote_access_enabled': bool(row['remote_access_enabled']),
            'default_policy': row['default_policy'],
            'encrypted_backup_enabled': bool(row['encrypted_backup_enabled']),
            'updated_at': row['updated_at'],
        }

    def update_settings(
        self,
        *,
        cloud_enabled: bool | None = None,
        cloud_mode: str | CloudMode | None = None,
        remote_access_enabled: bool | None = None,
        default_policy: str | StoragePolicy | None = None,
        encrypted_backup_enabled: bool | None = None,
    ) -> dict[str, Any]:
        current = self.settings()
        enabled = current['cloud_enabled'] if cloud_enabled is None else bool(cloud_enabled)
        mode = CloudMode(cloud_mode or current['cloud_mode'])
        if not enabled:
            mode = CloudMode.LOCAL_ONLY
        elif mode is CloudMode.LOCAL_ONLY:
            raise ValueError('cloud mode cannot be local_only while online storage is enabled')
        policy = StoragePolicy(default_policy or current['default_policy'])
        remote = current['remote_access_enabled'] if remote_access_enabled is None else bool(remote_access_enabled)
        backup = current['encrypted_backup_enabled'] if encrypted_backup_enabled is None else bool(encrypted_backup_enabled)
        with self._con() as con:
            con.execute(
                '''UPDATE data_plane_settings SET schema_version=?,cloud_enabled=?,cloud_mode=?,
                   remote_access_enabled=?,default_policy=?,encrypted_backup_enabled=?,updated_at=? WHERE singleton=1''',
                (self.SCHEMA_VERSION, int(enabled), mode.value, int(remote), policy.value, int(backup), _now()),
            )
            if not enabled:
                con.execute('UPDATE data_plane_provider_configs SET enabled=0,updated_at=?', (_now(),))
        result = self.settings()
        self._emit('data_plane.settings_changed', **result)
        return result

    def register_item(
        self,
        global_id: str,
        *,
        entity_type: str,
        primary_device_id: str,
        policy: str | StoragePolicy | None = None,
        remote_access_allowed: bool = True,
        copy_allowed: bool = False,
        backup_mode: str | BackupMode = BackupMode.OFF,
        origin_device_id: str | None = None,
        content_digest: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        global_id = str(global_id or '').strip()
        entity_type = str(entity_type or '').strip()
        primary_device_id = str(primary_device_id or '').strip()
        if not global_id or not entity_type or not primary_device_id:
            raise ValueError('global_id, entity_type and primary_device_id are required')
        metadata = dict(metadata or {})
        if contains_secret_or_raw_content(metadata):
            raise ValueError('data-plane metadata must not contain secrets or raw content')
        encoded = _json(metadata).encode('utf-8')
        if len(encoded) > self.MAX_METADATA_BYTES:
            raise ValueError('data-plane metadata is too large')
        storage_policy = StoragePolicy(policy or self.settings()['default_policy'])
        backup = BackupMode(backup_mode)
        origin = str(origin_device_id or primary_device_id)
        stamp = _now()
        with self._lock, self._con() as con:
            existing = con.execute('SELECT version FROM data_plane_items WHERE global_id=?', (global_id,)).fetchone()
            version = int(existing['version']) + 1 if existing else 1
            con.execute(
                '''INSERT INTO data_plane_items(
                    global_id,entity_type,primary_device_id,storage_policy,remote_access_allowed,
                    copy_allowed,backup_mode,version,origin_device_id,content_digest,tombstone,metadata_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(global_id) DO UPDATE SET
                    entity_type=excluded.entity_type,primary_device_id=excluded.primary_device_id,
                    storage_policy=excluded.storage_policy,remote_access_allowed=excluded.remote_access_allowed,
                    copy_allowed=excluded.copy_allowed,backup_mode=excluded.backup_mode,version=excluded.version,
                    origin_device_id=excluded.origin_device_id,content_digest=excluded.content_digest,
                    tombstone=0,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at''',
                (global_id, entity_type, primary_device_id, storage_policy.value, int(remote_access_allowed),
                 int(copy_allowed), backup.value, version, origin, content_digest, 0, _json(metadata), stamp),
            )
            con.execute(
                '''INSERT INTO data_plane_locations(global_id,location_type,location_id,provider_id,has_bytes,available,updated_at)
                   VALUES(?,?,?,?,1,1,?)
                   ON CONFLICT(global_id,location_type,location_id) DO UPDATE SET has_bytes=1,available=1,updated_at=excluded.updated_at''',
                (global_id, 'device', primary_device_id, 'local', stamp),
            )
        self._emit('data_plane.item_registered', global_id=global_id, storage_policy=storage_policy.value)
        return self.item(global_id)

    def item(self, global_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute('SELECT * FROM data_plane_items WHERE global_id=?', (str(global_id),)).fetchone()
        if row is None:
            raise KeyError('data-plane item not found')
        result = dict(row)
        result['remote_access_allowed'] = bool(result['remote_access_allowed'])
        result['copy_allowed'] = bool(result['copy_allowed'])
        result['tombstone'] = bool(result['tombstone'])
        result['metadata'] = json.loads(result.pop('metadata_json') or '{}')
        result['locations'] = self.locations(global_id)
        return result

    def locations(self, global_id: str) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute(
                'SELECT * FROM data_plane_locations WHERE global_id=? ORDER BY location_type,location_id',
                (str(global_id),),
            ).fetchall()
        return [
            {**dict(row), 'has_bytes': bool(row['has_bytes']), 'available': bool(row['available'])}
            for row in rows
        ]

    def mark_location(
        self,
        global_id: str,
        *,
        location_type: str,
        location_id: str,
        provider_id: str = 'local',
        has_bytes: bool = True,
        available: bool = True,
    ) -> dict[str, Any]:
        item = self.item(global_id)
        cloud_enabled = self.settings()['cloud_enabled']
        self.providers.assert_allowed(provider_id, cloud_enabled=cloud_enabled)
        if item['storage_policy'] == StoragePolicy.DEVICE_ONLY.value and location_type != 'device':
            raise PermissionError('device-only data cannot gain a cloud/provider byte location')
        if item['storage_policy'] == StoragePolicy.DEVICE_ONLY.value and has_bytes and location_id != item['primary_device_id']:
            raise PermissionError('device-only data cannot be copied to another device')
        with self._con() as con:
            con.execute(
                '''INSERT INTO data_plane_locations(global_id,location_type,location_id,provider_id,has_bytes,available,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(global_id,location_type,location_id) DO UPDATE SET
                       provider_id=excluded.provider_id,has_bytes=excluded.has_bytes,
                       available=excluded.available,updated_at=excluded.updated_at''',
                (str(global_id), str(location_type), str(location_id), str(provider_id), int(has_bytes), int(available), _now()),
            )
        return self.item(global_id)

    def set_policy(self, global_id: str, policy: str | StoragePolicy, *, copy_allowed: bool | None = None, remote_access_allowed: bool | None = None) -> dict[str, Any]:
        item = self.item(global_id)
        target = StoragePolicy(policy)
        copy_value = item['copy_allowed'] if copy_allowed is None else bool(copy_allowed)
        remote_value = item['remote_access_allowed'] if remote_access_allowed is None else bool(remote_access_allowed)
        with self._con() as con:
            con.execute(
                '''UPDATE data_plane_items SET storage_policy=?,copy_allowed=?,remote_access_allowed=?,
                   version=version+1,updated_at=? WHERE global_id=?''',
                (target.value, int(copy_value), int(remote_value), _now(), str(global_id)),
            )
            if target is StoragePolicy.DEVICE_ONLY:
                con.execute(
                    '''DELETE FROM data_plane_locations
                       WHERE global_id=? AND NOT(location_type='device' AND location_id=?)''',
                    (str(global_id), item['primary_device_id']),
                )
        self._emit('data_plane.policy_changed', global_id=str(global_id), storage_policy=target.value)
        return self.item(global_id)

    def configure_provider(self, provider_id: str, *, enabled: bool, credential_ref: str | None = None, config: Mapping[str, Any] | None = None, verified: bool = False) -> dict[str, Any]:
        settings = self.settings()
        descriptor = self.providers.assert_allowed(provider_id, cloud_enabled=settings['cloud_enabled'])
        if descriptor.provider_id == 'local':
            raise ValueError('local storage is always available and is not configured as a cloud provider')
        config = dict(config or {})
        if contains_secret_or_raw_content(config):
            raise ValueError('provider configuration must contain references, never raw credentials/secrets')
        if enabled and not credential_ref and descriptor.credential_kind not in {'managed', 'native_bridge'}:
            raise ValueError('enabled provider requires a credential/connector reference')
        stamp = _now()
        with self._con() as con:
            con.execute(
                '''INSERT INTO data_plane_provider_configs(provider_id,enabled,credential_ref,config_json,verified_at,updated_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(provider_id) DO UPDATE SET
                   enabled=excluded.enabled,credential_ref=excluded.credential_ref,
                   config_json=excluded.config_json,verified_at=excluded.verified_at,updated_at=excluded.updated_at''',
                (provider_id, int(enabled), credential_ref, _json(config), stamp if verified else None, stamp),
            )
        return self.provider_status(provider_id)

    def provider_status(self, provider_id: str) -> dict[str, Any]:
        descriptor = self.providers.get(provider_id)
        with self._con() as con:
            row = con.execute('SELECT * FROM data_plane_provider_configs WHERE provider_id=?', (provider_id,)).fetchone()
        configured = row is not None
        cloud_enabled = self.settings()['cloud_enabled']
        return {
            **descriptor.__dict__,
            'configured': configured,
            'enabled': bool(row['enabled']) if row is not None and cloud_enabled else False,
            'credential_ref': row['credential_ref'] if row is not None else None,
            'config': json.loads(row['config_json'] or '{}') if row is not None else {},
            'verified_at': row['verified_at'] if row is not None else None,
            'available': bool(configured and row['enabled'] and cloud_enabled and row['verified_at']),
        }

    def provider_inventory(self) -> list[dict[str, Any]]:
        return [self.provider_status(item['provider_id']) for item in self.providers.list()]

    def prepare_sync_event(self, global_id: str, *, origin_device_id: str, payload: Mapping[str, Any] | None = None, event_kind: str = 'update') -> dict[str, Any] | None:
        item = self.item(global_id)
        if item['tombstone'] and event_kind != 'delete':
            raise ValueError('cannot update a deleted data-plane item')
        if item['storage_policy'] == StoragePolicy.DEVICE_ONLY.value:
            return None
        raw_payload = dict(payload or {})
        if contains_secret_or_raw_content(raw_payload):
            raise ValueError('sync payload contains secrets or raw content')
        if item['storage_policy'] == StoragePolicy.PROGRESS_ONLY.value:
            clean = progress_projection(raw_payload)
        else:
            clean = raw_payload
        body = {
            'global_id': str(global_id),
            'version': int(item['version']),
            'origin_device_id': str(origin_device_id),
            'event_kind': str(event_kind),
            'payload': clean,
        }
        event_id = hashlib.sha256(_json(body).encode('utf-8')).hexdigest()
        payload_hash = _hash(clean)
        with self._con() as con:
            con.execute(
                '''INSERT OR IGNORE INTO data_plane_sync_events(
                   event_id,global_id,version,origin_device_id,event_kind,payload_json,payload_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)''',
                (event_id, str(global_id), int(item['version']), str(origin_device_id), str(event_kind), _json(clean), payload_hash, _now()),
            )
        return {'event_id': event_id, **body, 'payload_hash': payload_hash}

    def receive_sync_event(self, device_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        event_id = str(event.get('event_id') or '')
        global_id = str(event.get('global_id') or '')
        if not event_id or not global_id:
            raise ValueError('event_id and global_id are required')
        with self._con() as con:
            receipt = con.execute('SELECT 1 FROM data_plane_sync_receipts WHERE device_id=? AND event_id=?', (device_id, event_id)).fetchone()
            if receipt:
                return {'applied': False, 'duplicate': True, 'event_id': event_id}
        item = self.item(global_id)
        incoming_version = int(event.get('version') or 0)
        payload = dict(event.get('payload') or {})
        expected_hash = str(event.get('payload_hash') or '')
        if not expected_hash or _hash(payload) != expected_hash:
            raise ValueError('sync payload integrity check failed')
        if contains_secret_or_raw_content(payload):
            raise ValueError('sync payload contains prohibited data')
        if item['storage_policy'] == StoragePolicy.DEVICE_ONLY.value:
            raise PermissionError('device-only item rejects replicated payloads')
        if item['storage_policy'] == StoragePolicy.PROGRESS_ONLY.value and payload != progress_projection(payload):
            raise PermissionError('progress-only item rejects non-progress fields')
        if incoming_version < int(item['version']):
            conflict_id = secrets.token_hex(16)
            with self._con() as con:
                con.execute(
                    'INSERT INTO data_plane_conflicts VALUES(?,?,?,?,?,?,NULL,?)',
                    (conflict_id, global_id, int(item['version']), incoming_version, event_id, _json({'reason': 'stale_incoming'}), _now()),
                )
            return {'applied': False, 'duplicate': False, 'conflict': True, 'conflict_id': conflict_id}
        with self._con() as con:
            con.execute('INSERT INTO data_plane_sync_receipts(device_id,event_id,received_at) VALUES(?,?,?)', (str(device_id), event_id, _now()))
        return {'applied': True, 'duplicate': False, 'event_id': event_id, 'payload': payload}

    def delete_item(self, global_id: str, *, origin_device_id: str) -> dict[str, Any]:
        item = self.item(global_id)
        with self._con() as con:
            con.execute(
                'UPDATE data_plane_items SET tombstone=1,version=version+1,origin_device_id=?,updated_at=? WHERE global_id=?',
                (str(origin_device_id), _now(), str(global_id)),
            )
        updated = self.item(global_id)
        event = self.prepare_sync_event(global_id, origin_device_id=origin_device_id, payload={'updated_at': updated['updated_at']}, event_kind='delete')
        return {'item': updated, 'sync_event': event}

    def _assert_active_device(self, device_id: str, scope: str):
        if self.device_registry is None:
            return
        if not self.device_registry.is_active(device_id):
            raise PermissionError('trusted active device required')
        if hasattr(self.device_registry, 'authorize') and not self.device_registry.authorize(device_id, scope):
            raise PermissionError(f'device is not permitted for {scope}')

    def online_devices(self) -> list[str]:
        if self.device_gateway is None:
            return []
        return list(self.device_gateway.online())

    def grant_remote_access(
        self,
        global_id: str,
        *,
        requester_device_id: str,
        purpose: str = 'view',
        allow_persist: bool = False,
        ttl_seconds: int = 120,
    ) -> dict[str, Any]:
        config = self.settings()
        if not config['remote_access_enabled']:
            raise PermissionError('remote data access is disabled by owner policy')
        item = self.item(global_id)
        if item['tombstone'] or not item['remote_access_allowed']:
            raise PermissionError('remote access is not allowed for this item')
        self._assert_active_device(requester_device_id, 'ai:chat')
        source = item['primary_device_id']
        if source != requester_device_id:
            self._assert_active_device(source, 'ai:chat')
            if self.device_gateway is not None and source not in self.online_devices():
                raise RuntimeError('source device is offline')
        persist_allowed = bool(allow_persist and item['copy_allowed'])
        if allow_persist and not persist_allowed:
            raise PermissionError('view/use authority does not permit permanent copy or move')
        ttl = max(1, min(int(ttl_seconds), self.MAX_LEASE_SECONDS))
        lease_id = secrets.token_urlsafe(24)
        expires_at = time.time() + ttl
        with self._con() as con:
            con.execute(
                '''INSERT INTO data_plane_remote_leases(
                   lease_id,global_id,requester_device_id,source_device_id,purpose,persist_allowed,expires_at,revoked_at,created_at
                   ) VALUES(?,?,?,?,?,?,?,NULL,?)''',
                (lease_id, str(global_id), str(requester_device_id), source, str(purpose)[:120], int(persist_allowed), expires_at, _now()),
            )
        self._emit('data_plane.remote_access_granted', global_id=str(global_id), requester_device_id=requester_device_id, source_device_id=source, persist_allowed=persist_allowed)
        return {
            'lease_id': lease_id,
            'global_id': str(global_id),
            'requester_device_id': requester_device_id,
            'source_device_id': source,
            'purpose': str(purpose)[:120],
            'persist_allowed': persist_allowed,
            'expires_at': expires_at,
        }

    def validate_remote_lease(self, lease_id: str, *, require_persist: bool = False) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute('SELECT * FROM data_plane_remote_leases WHERE lease_id=?', (str(lease_id),)).fetchone()
        if row is None or row['revoked_at'] is not None or float(row['expires_at']) <= time.time():
            raise PermissionError('remote access lease is unavailable or expired')
        if require_persist and not bool(row['persist_allowed']):
            raise PermissionError('remote access lease does not permit persistence')
        self._assert_active_device(row['requester_device_id'], 'ai:chat')
        self._assert_active_device(row['source_device_id'], 'ai:chat')
        return {**dict(row), 'persist_allowed': bool(row['persist_allowed'])}

    def revoke_remote_lease(self, lease_id: str) -> bool:
        with self._con() as con:
            cur = con.execute('UPDATE data_plane_remote_leases SET revoked_at=? WHERE lease_id=? AND revoked_at IS NULL', (time.time(), str(lease_id)))
        return bool(cur.rowcount)

    def diagnostics(self) -> dict[str, Any]:
        with self._con() as con:
            counts = {
                'items': con.execute('SELECT COUNT(*) FROM data_plane_items').fetchone()[0],
                'locations': con.execute('SELECT COUNT(*) FROM data_plane_locations').fetchone()[0],
                'events': con.execute('SELECT COUNT(*) FROM data_plane_sync_events').fetchone()[0],
                'conflicts': con.execute('SELECT COUNT(*) FROM data_plane_conflicts WHERE resolved_at IS NULL').fetchone()[0],
            }
        return {
            'settings': self.settings(),
            'providers': self.provider_inventory(),
            'online_devices': self.online_devices(),
            **counts,
        }
