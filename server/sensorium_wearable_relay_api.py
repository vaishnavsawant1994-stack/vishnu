from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Header, HTTPException

from devices.gateway import DeviceCommand


def sensorium_wearable_relay_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/v2/mobile", tags=["sensorium", "wearables"])
    registry = runtime.get("device_registry") if runtime else None
    gateway = runtime.get("device_gateway") if runtime else None
    permissions = runtime.get("sensor_permissions") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None:
        raise RuntimeError("Wearable relay requires device registry")

    def auth(authorization: str | None, device_id: str | None, *scopes: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in scopes:
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def target_access(controller: str, target: str) -> None:
        if gateway is None or permissions is None:
            raise HTTPException(503, "Mobile wearable Sensorium gateway is unavailable")
        if not target or not registry.is_active(target):
            raise HTTPException(404, "Target device is not active")
        if not registry.authorize(target, "device:read") or not registry.authorize(target, "sensor:wearable"):
            raise HTTPException(403, "Target device does not permit wearable Sensorium requests")
        if target != controller and not registry.authorize(controller, "device:admin"):
            raise HTTPException(403, "Cross-device wearable observation requires device:admin")

    async def request(target: str, action: str, *, timeout: float = 15.0) -> dict:
        response = await gateway.request(
            target,
            DeviceCommand(action=action, parameters={}, request_id=str(uuid.uuid4())),
            timeout=max(1.0, min(float(timeout), 30.0)),
        )
        if not isinstance(response, dict) or response.get("device_id") != target:
            raise HTTPException(409, "Wearable relay response identity mismatch")
        if response.get("ok") is not True:
            raise HTTPException(409, str(response.get("error") or "Wearable relay request failed")[:240])
        result = response.get("result")
        if not isinstance(result, dict):
            raise HTTPException(409, "Wearable relay returned an invalid result")
        return result

    @router.get("/{target_device_id}/wearables/inventory")
    async def wearable_inventory(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller = auth(authorization, x_device_id, "device:read", "sensor:wearable")
        target_access(controller, target_device_id)
        result = await request(target_device_id, "wearable_inventory", timeout=10.0)
        result["execution_authority"] = False
        return result

    @router.get("/{target_device_id}/wearables/snapshot")
    async def wearable_snapshot(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller = auth(authorization, x_device_id, "device:read", "sensor:wearable", "memory:sensitive")
        target_access(controller, target_device_id)
        result = await request(target_device_id, "wearable_snapshot", timeout=15.0)
        if result.get("raw_media_retained") is not False or result.get("execution_authority") is not False:
            raise HTTPException(403, "Wearable relay violated the semantic-only evidence boundary")
        proof = result.get("session") if isinstance(result.get("session"), dict) else None
        if proof is None:
            observations = result.get("observations") if isinstance(result.get("observations"), list) else []
            proof = observations[0] if observations and isinstance(observations[0], dict) else None
        if not isinstance(proof, dict) or proof.get("local_consent") is not True:
            raise HTTPException(403, "Wearable relay requires explicit local consent")
        session_id = str(proof.get("sensor_session_id") or "")
        resource_id = str(proof.get("resource_id") or "*")[:240]
        if len(session_id) < 8 or len(session_id) > 200:
            raise HTTPException(403, "Wearable relay did not provide a valid sensor session proof")
        if not permissions.can_request(target_device_id, "wearable", resource_id):
            raise HTTPException(403, "Wearable sensing is disabled by the target device policy")
        expires_at = proof.get("expires_at_epoch")
        ttl = 300.0
        if isinstance(expires_at, (int, float)):
            ttl = max(30.0, min(float(expires_at) - time.time(), 600.0))
        permissions.grant_session(
            target_device_id,
            "wearable",
            resource_id,
            ttl_seconds=ttl,
            session_id=session_id,
            reason="mobile companion proved explicit local wearable consent",
        )
        if not permissions.allows(
            target_device_id,
            "wearable",
            resource_id,
            session_id=session_id,
        ):
            raise HTTPException(403, "Wearable session proof was not accepted")
        if events is not None:
            events.emit(
                "sensorium.wearable.mobile_snapshot",
                controller_device_id=controller,
                target_device_id=target_device_id,
                resource_id=resource_id,
                execution_authority=False,
            )
        result["instruction_trust"] = "untrusted"
        result["execution_authority"] = False
        return result

    return router
