from __future__ import annotations

import json
from typing import Any

from .manager import UnifiedDataPlane
from .policy import StoragePolicy


class PolicyEnforcedDataPlane(UnifiedDataPlane):
    """Runtime data plane with fail-closed reachability/provider enforcement.

    UnifiedDataPlane owns the persistence model. This runtime wrapper tightens
    cross-device and provider boundaries so no unverified online target can be
    recorded as usable and no cross-device lease can be issued without the
    canonical DeviceGateway proving the source is online.
    """

    def provider_status(self, provider_id: str) -> dict[str, Any]:
        if str(provider_id) == 'local':
            descriptor = self.providers.get('local')
            return {
                **descriptor.__dict__,
                'configured': True,
                'enabled': True,
                'credential_ref': None,
                'config': {},
                'verified_at': 'local',
                'available': True,
            }
        return super().provider_status(provider_id)

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
        if target is StoragePolicy.DEVICE_ONLY:
            item = self.item(global_id)
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
        return super().set_policy(
            global_id,
            target,
            copy_allowed=copy_allowed,
            remote_access_allowed=remote_access_allowed,
        )

    def pending_progress_events(self, device_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return only bounded progress/tombstone events not acked by a device.

        Sync-everywhere domain payloads are intentionally not returned here;
        their durable bytes require domain/file-specific replication paths.
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
                          e.payload_json,e.payload_hash,e.created_at,i.entity_type,i.storage_policy
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
                'event_id': row['event_id'],
                'global_id': row['global_id'],
                'version': int(row['version']),
                'origin_device_id': row['origin_device_id'],
                'event_kind': row['event_kind'],
                'payload': json.loads(row['payload_json'] or '{}'),
                'payload_hash': row['payload_hash'],
                'created_at': row['created_at'],
                'entity_type': row['entity_type'],
                'storage_policy': row['storage_policy'],
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
                'INSERT OR IGNORE INTO data_plane_sync_receipts(device_id,event_id,received_at) VALUES(?,?,datetime(\'now\'))',
                (device_id, event_id),
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
