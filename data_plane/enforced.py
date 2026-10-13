from __future__ import annotations

from typing import Any

from .manager import UnifiedDataPlane


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
