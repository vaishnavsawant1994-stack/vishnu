from __future__ import annotations

import json
import secrets
from typing import Any, Mapping

from .manager import UnifiedDataPlane, _hash, _json, _now
from .policy import BackupMode, CloudMode, StoragePolicy, contains_secret_or_raw_content, progress_projection


class PolicyEnforcedDataPlane(UnifiedDataPlane):
    """Runtime data plane with fail-closed reachability/provider enforcement.

    UnifiedDataPlane owns the persistence model. This runtime wrapper tightens
    cross-device and provider boundaries so no unverified online target can be
    recorded as usable and no cross-device lease can be issued without the
    canonical DeviceGateway proving the source is online.
    """

    SYNC_SCHEMA_VERSION = 1
    SYNC_EVENT_KINDS = frozenset({'update', 'delete'})

    def update_settings(
        self,
        *,
        cloud_enabled: bool | None = None,
        cloud_mode: str | CloudMode | None = None,
        remote_access_enabled: bool | None = None,
        default_policy: str | StoragePolicy | None = None,
        encrypted_backup_enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Update effective owner policy without erasing provider preferences.

        Cloud OFF is an execution deny switch. It must not rewrite history or
        imply that already-persisted provider bytes disappeared. Configured
        provider enable preferences are preserved and become effective again
        only after the owner re-enables online storage.
        """
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
        stamp = _now()
        with self._con() as con:
            con.execute(
                '''UPDATE data_plane_settings SET schema_version=?,cloud_enabled=?,cloud_mode=?,
                   remote_access_enabled=?,default_policy=?,encrypted_backup_enabled=?,updated_at=? WHERE singleton=1''',
                (self.SCHEMA_VERSION, int(enabled), mode.value, int(remote), policy.value, int(backup), stamp),
            )
            if current['remote_access_enabled'] and not remote:
                con.execute(
                    'UPDATE data_plane_remote_leases SET revoked_at=? WHERE revoked_at IS NULL AND expires_at>?',
                    (__import__('time').time(), __import__('time').time()),
                )
        result = self.settings()
        self._emit('data_plane.settings_changed', **result)
        return result

    def provider_status(self, provider_id: str) -> dict[str, Any]:
        if str(provider_id) == 'local':
            descriptor = self.providers.get('local')
            return {
                **descriptor.__dict__,
                'configured': True,
                'configured_enabled': True,
                'enabled': True,
                'credential_ref': None,
                'config': {},
                'verified_at': 'local',
                'available': True,
            }
        descriptor = self.providers.get(provider_id)
        with self._con() as con:
            row = con.execute('SELECT * FROM data_plane_provider_configs WHERE provider_id=?', (provider_id,)).fetchone()
        configured = row is not None
        cloud_enabled = self.settings()['cloud_enabled']
        configured_enabled = bool(row['enabled']) if row is not None else False
        verified = bool(row is not None and row['verified_at'])
        return {
            **descriptor.__dict__,
            'configured': configured,
            'configured_enabled': configured_enabled,
            'enabled': bool(configured_enabled and cloud_enabled),
            'credential_ref': row['credential_ref'] if row is not None else None,
            'config': json.loads(row['config_json'] or '{}') if row is not None else {},
            'verified_at': row['verified_at'] if row is not None else None,
            'available': bool(configured and configured_enabled and cloud_enabled and verified),
        }

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
        provider_id = str(provider_id)
        if provider_id != 'local':
            status = self.provider_status(provider_id)
            if not status['available']:
                raise PermissionError('online storage provider is not connected and verified')
        return super().mark_location(
            global_id,
            location_type=location_type,
            location_id=location_id,
            provider_id=provider_id,
            has_bytes=has_bytes,
            available=available,
        )

    def set_policy(
        self,
        global_id: str,
        policy: str | StoragePolicy,
        *,
        copy_allowed: bool | None = None,
        remote_access_allowed: bool | None = None,
    ) -> dict[str, Any]:
        target = StoragePolicy(policy)
        item = self.item(global_id)
        if target is StoragePolicy.DEVICE_ONLY:
            primary = item['primary_device_id']
            durable_elsewhere = [
                location
                for location in item['locations']
                if location['has_bytes']
                and not (
                    location['location_type'] == 'device'
                    and location['location_id'] == primary
                    and location['provider_id'] == 'local'
                )
            ]
            if durable_elsewhere:
                raise PermissionError(
                    'cannot switch to device_only while durable bytes remain at another location; '
                    'remove and verify those copies first'
                )
        result = super().set_policy(
            global_id,
            target,
            copy_allowed=copy_allowed,
            remote_access_allowed=remote_access_allowed,
        )
        if item['remote_access_allowed'] and not result['remote_access_allowed']:
            now = __import__('time').time()
            with self._con() as con:
                con.execute(
                    'UPDATE data_plane_remote_leases SET revoked_at=? WHERE global_id=? AND revoked_at IS NULL AND expires_at>?',
                    (now, str(global_id), now),
                )
        return result

    @staticmethod
    def _sync_identity_body(event: Mapping[str, Any]) -> dict[str, Any]:
        return {
            'schema_version': int(event['schema_version']),
            'global_id': str(event['global_id']),
            'entity_type': str(event['entity_type']),
            'storage_policy': str(event['storage_policy']),
            'primary_device_id': str(event['primary_device_id']),
            'version': int(event['version']),
            'origin_device_id': str(event['origin_device_id']),
            'event_kind': str(event['event_kind']),
            'payload': dict(event.get('payload') or {}),
        }

    def prepare_sync_event(
        self,
        global_id: str,
        *,
        origin_device_id: str,
        payload: Mapping[str, Any] | None = None,
        event_kind: str = 'update',
    ) -> dict[str, Any] | None:
        item = self.item(global_id)
        kind = str(event_kind)
        if kind not in self.SYNC_EVENT_KINDS:
            raise ValueError('unsupported data-plane sync event kind')
        if item['tombstone'] and kind != 'delete':
            raise ValueError('cannot update a deleted data-plane item')
        if item['storage_policy'] == StoragePolicy.DEVICE_ONLY.value:
            return None
        raw_payload = dict(payload or {})
        if contains_secret_or_raw_content(raw_payload):
            raise ValueError('sync payload contains secrets or raw content')
        if item['storage_policy'] == StoragePolicy.PROGRESS_ONLY.value:
            clean = progress_projection(raw_payload)
        else:
            # sync_everywhere and on_demand still exclude raw bytes here. The
            # actual byte-transfer/materialization channel is separately governed.
            clean = raw_payload
        body = {
            'schema_version': self.SYNC_SCHEMA_VERSION,
            'global_id': str(global_id),
            'entity_type': item['entity_type'],
            'storage_policy': item['storage_policy'],
            'primary_device_id': item['primary_device_id'],
            'version': int(item['version']),
            'origin_device_id': str(origin_device_id),
            'event_kind': kind,
            'payload': clean,
        }
        event_id = _hash(body)
        payload_hash = _hash(clean)
        with self._con() as con:
            con.execute(
                '''INSERT OR IGNORE INTO data_plane_sync_events(
                   event_id,global_id,version,origin_device_id,event_kind,payload_json,payload_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)''',
                (event_id, str(global_id), int(item['version']), str(origin_device_id), kind, _json(clean), payload_hash, _now()),
            )
        return {'event_id': event_id, **body, 'payload_hash': payload_hash}

    def _record_conflict(self, global_id: str, local_version: int, incoming_version: int, event_id: str, reason: str) -> dict[str, Any]:
        conflict_id = secrets.token_hex(16)
        with self._con() as con:
            con.execute(
                'INSERT INTO data_plane_conflicts VALUES(?,?,?,?,?,?,NULL,?)',
                (conflict_id, global_id, local_version, incoming_version, event_id, _json({'reason': reason}), _now()),
            )
        return {'applied': False, 'duplicate': False, 'conflict': True, 'conflict_id': conflict_id, 'reason': reason}

    def receive_sync_event(self, device_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        device_id = str(device_id or '').strip()
        if not device_id:
            raise ValueError('device_id is required')
        schema_version = int(event.get('schema_version') or 0)
        if schema_version != self.SYNC_SCHEMA_VERSION:
            raise ValueError('unsupported data-plane sync schema version')
        event_id = str(event.get('event_id') or '')
        global_id = str(event.get('global_id') or '')
        entity_type = str(event.get('entity_type') or '').strip()
        storage_policy = StoragePolicy(str(event.get('storage_policy') or ''))
        primary_device_id = str(event.get('primary_device_id') or '').strip()
        origin_device_id = str(event.get('origin_device_id') or '').strip()
        event_kind = str(event.get('event_kind') or '')
        incoming_version = int(event.get('version') or 0)
        if not event_id or not global_id or not entity_type or not primary_device_id or not origin_device_id:
            raise ValueError('complete sync identity is required')
        if event_kind not in self.SYNC_EVENT_KINDS or incoming_version < 1:
            raise ValueError('invalid sync event kind or version')
        if storage_policy is StoragePolicy.DEVICE_ONLY:
            raise PermissionError('device-only item rejects replicated payloads')
        self._assert_active_device(origin_device_id, 'ai:chat')
        payload = dict(event.get('payload') or {})
        expected_hash = str(event.get('payload_hash') or '')
        if not expected_hash or _hash(payload) != expected_hash:
            raise ValueError('sync payload integrity check failed')
        if contains_secret_or_raw_content(payload):
            raise ValueError('sync payload contains prohibited data')
        if storage_policy is StoragePolicy.PROGRESS_ONLY and payload != progress_projection(payload):
            raise PermissionError('progress-only item rejects non-progress fields')
        expected_event_id = _hash(self._sync_identity_body({**event, 'schema_version': schema_version}))
        if not secrets.compare_digest(event_id, expected_event_id):
            raise ValueError('sync event identity integrity check failed')
        with self._con() as con:
            receipt = con.execute(
                'SELECT 1 FROM data_plane_sync_receipts WHERE device_id=? AND event_id=?',
                (device_id, event_id),
            ).fetchone()
            if receipt:
                return {'applied': False, 'duplicate': True, 'event_id': event_id}
            local = con.execute('SELECT * FROM data_plane_items WHERE global_id=?', (global_id,)).fetchone()

        if local is None:
            # A device may create continuation state while every other device is
            # offline. The first authenticated envelope bootstraps only bounded
            # metadata; it never materializes raw file bytes.
            self.register_item(
                global_id,
                entity_type=entity_type,
                primary_device_id=primary_device_id,
                policy=storage_policy,
                origin_device_id=origin_device_id,
                metadata=payload,
            )
            with self._con() as con:
                con.execute(
                    '''UPDATE data_plane_items SET version=?,origin_device_id=?,tombstone=?,metadata_json=?,updated_at=?
                       WHERE global_id=?''',
                    (incoming_version, origin_device_id, int(event_kind == 'delete'), _json(payload), _now(), global_id),
                )
        else:
            local_version = int(local['version'])
            local_policy = str(local['storage_policy'])
            if local_policy == StoragePolicy.DEVICE_ONLY.value:
                raise PermissionError('device-only item rejects replicated payloads')
            if local_policy != storage_policy.value:
                return self._record_conflict(global_id, local_version, incoming_version, event_id, 'policy_mismatch')
            if incoming_version < local_version:
                return self._record_conflict(global_id, local_version, incoming_version, event_id, 'stale_incoming')
            if incoming_version > local_version + 1:
                return self._record_conflict(global_id, local_version, incoming_version, event_id, 'version_gap')
            if incoming_version == local_version and str(local['origin_device_id']) != origin_device_id:
                return self._record_conflict(global_id, local_version, incoming_version, event_id, 'concurrent_same_version')
            with self._con() as con:
                con.execute(
                    '''UPDATE data_plane_items SET entity_type=?,primary_device_id=?,version=?,origin_device_id=?,
                       tombstone=?,metadata_json=?,updated_at=? WHERE global_id=?''',
                    (entity_type, primary_device_id, incoming_version, origin_device_id,
                     int(event_kind == 'delete'), _json(payload), _now(), global_id),
                )

        with self._con() as con:
            con.execute(
                '''INSERT OR IGNORE INTO data_plane_sync_events(
                   event_id,global_id,version,origin_device_id,event_kind,payload_json,payload_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)''',
                (event_id, global_id, incoming_version, origin_device_id, event_kind, _json(payload), expected_hash, _now()),
            )
            con.execute(
                'INSERT OR IGNORE INTO data_plane_sync_receipts(device_id,event_id,received_at) VALUES(?,?,?)',
                (device_id, event_id, _now()),
            )
        self._emit('data_plane.sync_received', global_id=global_id, origin_device_id=origin_device_id, version=incoming_version)
        return {'applied': True, 'duplicate': False, 'event_id': event_id, 'payload': payload}

    def pending_progress_events(self, device_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return only bounded progress/tombstone events not acked by a device.

        Sync-everywhere/on-demand domain payloads are intentionally not returned
        here; their durable bytes/reference materialization require their own
        governed transfer paths.
        """
        device_id = str(device_id or '').strip()
        if not device_id:
            raise ValueError('device_id is required')
        if self.device_registry is not None and not self.device_registry.is_active(device_id):
            raise PermissionError('trusted active device required')
        limit = max(1, min(int(limit), 500))
        with self._con() as con:
            rows = con.execute(
                '''SELECT e.event_id,e.global_id,e.version,e.origin_device_id,e.event_kind,
                          e.payload_json,e.payload_hash,e.created_at,i.entity_type,i.storage_policy,i.primary_device_id
                   FROM data_plane_sync_events e
                   JOIN data_plane_items i ON i.global_id=e.global_id
                   LEFT JOIN data_plane_sync_receipts r
                     ON r.event_id=e.event_id AND r.device_id=?
                   WHERE r.event_id IS NULL
                     AND i.storage_policy='progress_only'
                     AND e.origin_device_id<>?
                   ORDER BY e.created_at,e.event_id
                   LIMIT ?''',
                (device_id, device_id, limit),
            ).fetchall()
        return [
            {
                'schema_version': self.SYNC_SCHEMA_VERSION,
                'event_id': row['event_id'],
                'global_id': row['global_id'],
                'entity_type': row['entity_type'],
                'storage_policy': row['storage_policy'],
                'primary_device_id': row['primary_device_id'],
                'version': int(row['version']),
                'origin_device_id': row['origin_device_id'],
                'event_kind': row['event_kind'],
                'payload': json.loads(row['payload_json'] or '{}'),
                'payload_hash': row['payload_hash'],
                'created_at': row['created_at'],
            }
            for row in rows
        ]

    def acknowledge_sync_event(self, device_id: str, event_id: str) -> bool:
        device_id = str(device_id or '').strip()
        event_id = str(event_id or '').strip()
        if not device_id or not event_id:
            raise ValueError('device_id and event_id are required')
        if self.device_registry is not None and not self.device_registry.is_active(device_id):
            raise PermissionError('trusted active device required')
        with self._con() as con:
            known = con.execute('SELECT 1 FROM data_plane_sync_events WHERE event_id=?', (event_id,)).fetchone()
            if not known:
                raise KeyError('sync event not found')
            before = con.total_changes
            con.execute(
                'INSERT OR IGNORE INTO data_plane_sync_receipts(device_id,event_id,received_at) VALUES(?,?,?)',
                (device_id, event_id, _now()),
            )
            return con.total_changes > before

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
        source = item['primary_device_id']
        if source != str(requester_device_id):
            if self.device_gateway is None:
                raise RuntimeError('canonical device gateway is required for cross-device access')
            if source not in self.online_devices():
                raise RuntimeError('source device is offline')
        return super().grant_remote_access(
            global_id,
            requester_device_id=requester_device_id,
            purpose=purpose,
            allow_persist=allow_persist,
            ttl_seconds=ttl_seconds,
        )

    def validate_remote_lease(self, lease_id: str, *, require_persist: bool = False) -> dict[str, Any]:
        observed = super().validate_remote_lease(lease_id, require_persist=require_persist)
        if not self.settings()['remote_access_enabled']:
            raise PermissionError('remote data access is disabled by owner policy')
        item = self.item(observed['global_id'])
        if item['tombstone'] or not item['remote_access_allowed']:
            raise PermissionError('remote access is no longer allowed for this item')
        if require_persist and not item['copy_allowed']:
            raise PermissionError('current item policy no longer permits persistence')
        source = str(observed['source_device_id'])
        requester = str(observed['requester_device_id'])
        if source != requester:
            if self.device_gateway is None:
                raise RuntimeError('canonical device gateway is required for cross-device access')
            if source not in self.online_devices():
                raise RuntimeError('source device is offline')
        return observed

    def diagnostics(self) -> dict[str, Any]:
        result = super().diagnostics()
        with self._con() as con:
            result['remote_durable_locations'] = con.execute(
                "SELECT COUNT(*) FROM data_plane_locations WHERE has_bytes=1 AND NOT(location_type='device' AND provider_id='local')"
            ).fetchone()[0]
            result['active_remote_leases'] = con.execute(
                'SELECT COUNT(*) FROM data_plane_remote_leases WHERE revoked_at IS NULL AND expires_at>?',
                (__import__('time').time(),),
            ).fetchone()[0]
        result['cloud_bytes_present'] = bool(result['remote_durable_locations'])
        return result
