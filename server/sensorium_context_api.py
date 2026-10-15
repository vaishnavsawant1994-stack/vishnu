from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from devices.gateway import DeviceCommand
from sensorium.attention import AttentionManager
from sensorium.context_service import MobileContextService, SENSOR_SCOPES
from sensorium.episodic_memory import EpisodicMemoryManager
from sensorium.iot import IoTSensorRegistry
from sensorium.l4_qualification import PhysicalDeviceQualification
from sensorium.privacy_zones import PrivacyZoneStore
from sensorium.proactive import ProactivePhysicalAssistant
from sensorium.sensor_health import SensorHealthMonitor
from sensorium.sensor_permissions import SensorPermissionStore
from sensorium.spatial import SpatialWorld
from sensorium.wearables import WearableSensorium
from sensorium.world_model import TemporalWorldModel


class PermissionPolicyBody(BaseModel):
    sensor: str = Field(min_length=2, max_length=40)
    resource_id: str = Field(default="*", min_length=1, max_length=240)
    mode: str = Field(min_length=3, max_length=16)
    reason: str = Field(default="owner changed sensor policy", max_length=500)


class PermissionSessionBody(BaseModel):
    sensor: str = Field(min_length=2, max_length=40)
    resource_id: str = Field(default="*", min_length=1, max_length=240)
    ttl_seconds: float = Field(default=300, ge=30, le=1800)
    session_id: str | None = Field(default=None, min_length=8, max_length=200)
    explicit_consent: bool = False
    reason: str = Field(default="explicit local sensor consent", max_length=500)


class AttentionBody(BaseModel):
    purpose: str = Field(min_length=1, max_length=2000)
    permitted: list[str] = Field(default_factory=list, max_length=32)
    privacy_denied: list[str] = Field(default_factory=list, max_length=32)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    max_active_sensors: int = Field(default=3, ge=1, le=6)


class MobileSessionRequestBody(BaseModel):
    sensor: str = Field(min_length=2, max_length=40)
    resource_id: str = Field(default="*", min_length=1, max_length=240)
    reason: str = Field(default="Vishnu needs temporary sensor context for your request.", max_length=240)


class MobileSnapshotBody(BaseModel):
    sensors: list[str] = Field(min_length=1, max_length=16)
    context_tags: list[str] = Field(default_factory=list, max_length=32)


class ScreenSnapshotBody(BaseModel):
    question: str = Field(default="Describe the visible mobile screen and relevant UI state without acting.", min_length=1, max_length=2000)


class WorldObserveBody(BaseModel):
    entity_id: str = Field(min_length=1, max_length=160)
    kind: str = Field(default="object", max_length=80)
    label: str | None = Field(default=None, max_length=240)
    attribute: str = Field(min_length=1, max_length=120)
    value: Any
    source: str = Field(min_length=1, max_length=160)
    modality: str = Field(min_length=2, max_length=80)
    confidence: float = Field(default=0.7, ge=0, le=1)
    freshness_seconds: float = Field(default=30, gt=0, le=86400)
    captured_at: float | None = None


class WorldRelationBody(BaseModel):
    subject_id: str = Field(min_length=1, max_length=160)
    predicate: str = Field(min_length=1, max_length=120)
    object_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=160)
    confidence: float = Field(default=0.7, ge=0, le=1)
    captured_at: float | None = None


class PrivacyZoneBody(BaseModel):
    zone_id: str | None = Field(default=None, max_length=200)
    label: str = Field(min_length=1, max_length=160)
    enabled: bool = True
    deny_sensors: list[str] = Field(default_factory=list, max_length=64)
    context_tags: list[str] = Field(default_factory=list, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: float | None = Field(default=None, ge=1, le=100000)
    require_local_processing: bool = False
    require_bystander_redaction: bool = False
    forbid_media_retention: bool = False
    private_screen: bool = False
    meeting_mode: bool = False


class PrivacyEvaluateBody(BaseModel):
    context_tags: list[str] = Field(default_factory=list, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class EpisodeBody(BaseModel):
    mode: str = Field(default="none", max_length=32)
    summary: str = Field(min_length=1, max_length=20000)
    modalities: list[str] = Field(default_factory=list, max_length=32)
    event: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.7, ge=0, le=1)
    privacy_forbid_media: bool = False


class IoTRegisterBody(BaseModel):
    source_id: str | None = Field(default=None, max_length=200)
    label: str = Field(min_length=1, max_length=160)
    kind: str = Field(default="sensor", max_length=80)
    observe_capabilities: list[str] = Field(min_length=1, max_length=64)
    action_capabilities: list[str] = Field(default_factory=list, max_length=64)


class IoTObserveBody(BaseModel):
    capability: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0, le=1)


class IoTActionBody(BaseModel):
    capability: str = Field(min_length=1, max_length=120)
    parameters: dict = Field(default_factory=dict)


class WearableRegisterBody(BaseModel):
    device_id: str = Field(min_length=1, max_length=200)
    wearable_type: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=1, max_length=160)
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class WearableIngestBody(BaseModel):
    source: str = Field(default="wearable", max_length=160)
    payload: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0, le=1)
    captured_at: float | None = None


class ProactiveStartBody(BaseModel):
    purpose: str = Field(min_length=1, max_length=1000)
    allowed_sensors: list[str] = Field(min_length=1, max_length=32)
    duration_seconds: float = Field(default=900, ge=30, le=3600)


class ProactiveEvaluateBody(BaseModel):
    sensor: str = Field(min_length=2, max_length=40)
    observation: dict = Field(default_factory=dict)
    significance: float = Field(ge=0, le=1)
    message: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(default=0.7, ge=0, le=1)


class L4EvidenceBody(BaseModel):
    physical_device: bool
    device_class: str = Field(min_length=1, max_length=120)
    os_version: str = Field(default="", max_length=120)
    app_version: str = Field(default="", max_length=120)
    runner_identity: str = Field(default="manual-physical-lab", max_length=160)
    scenarios: dict[str, bool]


def sensorium_context_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/v2", tags=["sensorium", "context-awareness"])
    registry = runtime.get("device_registry") if runtime else None
    gateway = runtime.get("device_gateway") if runtime else None
    settings = runtime.get("settings") if runtime else None
    events = runtime.get("events") if runtime else None
    models = runtime.get("models") if runtime else None
    memory = runtime.get("memory") if runtime else None
    vault = runtime.get("vault") if runtime else None
    if vault is None and models is not None:
        vault = getattr(models, "vault", None)
    if registry is None:
        raise RuntimeError("Sensorium 2 requires device registry")

    data_dir_value = getattr(settings, "data_dir", None)
    data_dir = Path(data_dir_value) if data_dir_value is not None else None

    permissions = runtime.get("sensor_permissions") if runtime else None
    if permissions is None and data_dir is not None:
        permissions = SensorPermissionStore(data_dir / "sensor-permissions.sqlite3", events=events)
        runtime["sensor_permissions"] = permissions

    attention = runtime.get("sensorium_attention") if runtime else None
    if attention is None:
        attention = AttentionManager(events=events)
        runtime["sensorium_attention"] = attention

    health = runtime.get("sensorium_health") if runtime else None
    if health is None:
        health = SensorHealthMonitor(events=events)
        runtime["sensorium_health"] = health

    world = runtime.get("sensorium_world") if runtime else None
    if world is None and data_dir is not None:
        world = TemporalWorldModel(data_dir / "sensorium-world.sqlite3", events=events)
        runtime["sensorium_world"] = world

    zones = runtime.get("sensorium_privacy_zones") if runtime else None
    if zones is None and data_dir is not None and vault is not None:
        zones = PrivacyZoneStore(data_dir / "sensorium-privacy-zones.sqlite3", vault=vault, events=events)
        runtime["sensorium_privacy_zones"] = zones

    spatial = runtime.get("sensorium_spatial") if runtime else None
    if spatial is None:
        spatial = SpatialWorld(events=events)
        runtime["sensorium_spatial"] = spatial

    episodic = runtime.get("sensorium_episodic_memory") if runtime else None
    if episodic is None:
        episodic = EpisodicMemoryManager(memory, data_dir=data_dir, vault=vault, events=events)
        runtime["sensorium_episodic_memory"] = episodic

    iot = runtime.get("sensorium_iot") if runtime else None
    if iot is None and data_dir is not None:
        iot = IoTSensorRegistry(data_dir / "sensorium-iot.sqlite3", events=events)
        runtime["sensorium_iot"] = iot

    wearables = runtime.get("sensorium_wearables") if runtime else None
    if wearables is None:
        wearables = WearableSensorium(events=events)
        runtime["sensorium_wearables"] = wearables

    proactive = runtime.get("sensorium_proactive") if runtime else None
    if proactive is None:
        proactive = ProactivePhysicalAssistant(events=events)
        runtime["sensorium_proactive"] = proactive

    l4 = runtime.get("sensorium_l4") if runtime else None
    if l4 is None and data_dir is not None:
        l4 = PhysicalDeviceQualification(data_dir, events=events)
        runtime["sensorium_l4"] = l4

    mobile = runtime.get("sensorium_context_mobile") if runtime else None
    if mobile is None and gateway is not None and permissions is not None:
        mobile = MobileContextService(
            registry,
            gateway,
            permissions=permissions,
            health=health,
            world=world,
            privacy_zones=zones,
            models=models,
            spatial=spatial,
            events=events,
        )
        runtime["sensorium_context_mobile"] = mobile

    def auth(authorization: str | None, device_id: str | None, *scopes: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in scopes:
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def require_component(value, name: str):
        if value is None:
            raise HTTPException(503, f"{name} is unavailable in this runtime")
        return value

    def translate(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc)[:300] or "Sensorium operation is not permitted")
        if isinstance(exc, KeyError):
            return HTTPException(404, str(exc)[:300] or "Sensorium resource not found")
        if isinstance(exc, TimeoutError):
            return HTTPException(504, str(exc)[:300] or "Sensorium operation timed out")
        if isinstance(exc, ValueError):
            return HTTPException(422, str(exc))
        return HTTPException(409, str(exc)[:300] or "Sensorium operation is unavailable")

    @router.get("/permissions")
    def list_permissions(
        sensor: str | None = Query(default=None, max_length=40),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        try:
            return {"permissions": store.list_device(device_id, sensor=sensor)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/permissions/policy")
    def set_permission_policy(
        body: PermissionPolicyBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        scope = SENSOR_SCOPES.get(body.sensor.strip().lower())
        if scope and not registry.authorize(device_id, scope):
            raise HTTPException(403, f"Device is not permitted to use {scope}")
        try:
            return store.set_policy(device_id, body.sensor, body.mode, body.resource_id, reason=body.reason)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/permissions/session/grant")
    def grant_permission_session(
        body: PermissionSessionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        if not body.explicit_consent:
            raise HTTPException(400, "explicit local sensor consent is required")
        store = require_component(permissions, "sensor permission authority")
        scope = SENSOR_SCOPES.get(body.sensor.strip().lower())
        if scope and not registry.authorize(device_id, scope):
            raise HTTPException(403, f"Device is not permitted to use {scope}")
        try:
            return store.grant_session(
                device_id,
                body.sensor,
                body.resource_id,
                ttl_seconds=body.ttl_seconds,
                session_id=body.session_id,
                reason=body.reason,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/permissions/session/revoke")
    def revoke_permission_session(
        body: PermissionSessionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        try:
            return store.revoke_session(device_id, body.sensor, body.resource_id, reason=body.reason)
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/permissions/audit")
    def permission_audit(
        limit: int = Query(default=200, ge=1, le=1000),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        return {"audit": store.audit(device_id, limit=limit)}

    @router.post("/stop-all")
    async def stop_all_sensing(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        hardware_stopped = False
        if gateway is not None:
            try:
                response = await gateway.request(
                    device_id,
                    DeviceCommand(action="sensor_stop_all", parameters={}, request_id=str(uuid.uuid4())),
                    timeout=10.0,
                )
                hardware_stopped = bool(isinstance(response, dict) and response.get("ok") is True)
            except Exception:
                hardware_stopped = False
        revoked = store.revoke_all(device_id, reason="owner pressed Stop all sensing")
        if events is not None:
            events.emit(
                "sensorium.stop_all",
                device_id=device_id,
                sessions_revoked=revoked,
                hardware_stop_acknowledged=hardware_stopped,
            )
        return {"stopped": True, "sessions_revoked": revoked, "hardware_stop_acknowledged": hardware_stopped}

    @router.get("/privacy-dashboard")
    def privacy_dashboard(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        store = require_component(permissions, "sensor permission authority")
        rows = store.list_device(device_id)
        return {
            "device_id": device_id,
            "sensors": rows,
            "active_sessions": [row for row in rows if row["mode"] == "session"],
            "recent_audit": store.audit(device_id, limit=50),
            "privacy_zones": zones.list() if zones is not None else [],
            "l4": l4.all_status() if l4 is not None else None,
            "stop_all_available": True,
        }

    @router.post("/attention/plan")
    def attention_plan(
        body: AttentionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return attention.plan(
            body.purpose,
            permitted=body.permitted,
            privacy_denied=body.privacy_denied,
            battery_percent=body.battery_percent,
            max_active_sensors=body.max_active_sensors,
        ).public()

    @router.get("/mobile/{target_device_id}/inventory")
    async def mobile_inventory(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.inventory(device_id, target_device_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/session/request")
    async def mobile_session_request(
        target_device_id: str,
        body: MobileSessionRequestBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.request_session(
                device_id,
                target_device_id,
                sensor=body.sensor,
                resource_id=body.resource_id,
                reason=body.reason,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/snapshot")
    async def mobile_snapshot(
        target_device_id: str,
        body: MobileSnapshotBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.snapshot(
                device_id,
                target_device_id,
                sensors=body.sensors,
                context_tags=body.context_tags,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/screen")
    async def mobile_screen(
        target_device_id: str,
        body: ScreenSnapshotBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.screen_snapshot(device_id, target_device_id, question=body.question)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/audio")
    async def mobile_audio(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.audio_sample(device_id, target_device_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/document")
    async def mobile_document(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.document_extract(device_id, target_device_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/spatial")
    async def mobile_spatial(
        target_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        service = require_component(mobile, "mobile Sensorium")
        try:
            return await service.spatial_snapshot(device_id, target_device_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/world/observe")
    def world_observe(
        body: WorldObserveBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        model = require_component(world, "temporal world model")
        try:
            return model.observe(
                body.entity_id,
                kind=body.kind,
                label=body.label,
                attribute=body.attribute,
                value=body.value,
                source=body.source,
                modality=body.modality,
                confidence=body.confidence,
                freshness_seconds=body.freshness_seconds,
                captured_at=body.captured_at,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/world/relation")
    def world_relation(
        body: WorldRelationBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        model = require_component(world, "temporal world model")
        try:
            return model.relate(
                body.subject_id,
                body.predicate,
                body.object_id,
                source=body.source,
                confidence=body.confidence,
                captured_at=body.captured_at,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/world")
    def world_snapshot(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        return require_component(world, "temporal world model").snapshot(limit=limit)

    @router.get("/world/contradictions")
    def world_contradictions(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        return {"contradictions": require_component(world, "temporal world model").contradictions(limit=limit)}

    @router.get("/world/{entity_id}")
    def world_entity(
        entity_id: str,
        include_history: bool = Query(default=False),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        try:
            return require_component(world, "temporal world model").entity(entity_id, include_history=include_history)
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/privacy-zones")
    def list_privacy_zones(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "memory:sensitive")
        return {"zones": require_component(zones, "privacy zones").list()}

    @router.post("/privacy-zones")
    def put_privacy_zone(
        body: PrivacyZoneBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "memory:sensitive")
        zone_store = require_component(zones, "privacy zones")
        rule = body.model_dump(exclude={"zone_id", "label", "enabled"})
        try:
            return zone_store.put(label=body.label, rule=rule, zone_id=body.zone_id, enabled=body.enabled)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/privacy-zones/evaluate")
    def evaluate_privacy_zones(
        body: PrivacyEvaluateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        zone_store = require_component(zones, "privacy zones")
        return zone_store.evaluate(body.model_dump())

    @router.delete("/privacy-zones/{zone_id}")
    def delete_privacy_zone(
        zone_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "memory:sensitive")
        try:
            return {"deleted": require_component(zones, "privacy zones").delete(zone_id)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/episodes")
    def remember_episode(
        body: EpisodeBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "memory:write", "memory:sensitive")
        try:
            return episodic.remember(
                mode=body.mode,
                summary=body.summary,
                device_id=device_id,
                modalities=body.modalities,
                event=body.event,
                confidence=body.confidence,
                privacy_forbid_media=body.privacy_forbid_media,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/iot")
    def list_iot(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "sensor:iot")
        return {"sources": require_component(iot, "IoT Sensorium").list()}

    @router.post("/iot/register")
    def register_iot(
        body: IoTRegisterBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "sensor:iot")
        try:
            return require_component(iot, "IoT Sensorium").register(
                source_id=body.source_id,
                label=body.label,
                kind=body.kind,
                observe_capabilities=body.observe_capabilities,
                action_capabilities=body.action_capabilities,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/iot/{source_id}/observe")
    def observe_iot(
        source_id: str,
        body: IoTObserveBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "sensor:iot")
        try:
            return require_component(iot, "IoT Sensorium").observe(
                source_id,
                capability=body.capability,
                payload=body.payload,
                confidence=body.confidence,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/iot/{source_id}/propose-action")
    def propose_iot_action(
        source_id: str,
        body: IoTActionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "sensor:iot")
        try:
            return require_component(iot, "IoT Sensorium").propose_action(
                source_id,
                capability=body.capability,
                parameters=body.parameters,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/wearables/register")
    def register_wearable(
        body: WearableRegisterBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "sensor:wearable")
        try:
            return wearables.register(
                body.device_id,
                wearable_type=body.wearable_type,
                label=body.label,
                capabilities=body.capabilities,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/wearables/{wearable_device_id}/ingest")
    def ingest_wearable(
        wearable_device_id: str,
        body: WearableIngestBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "sensor:wearable")
        try:
            return wearables.ingest(
                wearable_device_id,
                source=body.source,
                payload=body.payload,
                confidence=body.confidence,
                captured_at=body.captured_at,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/proactive/start")
    def proactive_start(
        body: ProactiveStartBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        for sensor in body.allowed_sensors:
            scope = SENSOR_SCOPES.get(sensor.strip().lower())
            if scope and not registry.authorize(device_id, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        try:
            return proactive.start(
                device_id,
                purpose=body.purpose,
                allowed_sensors=body.allowed_sensors,
                duration_seconds=body.duration_seconds,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/proactive/{session_id}/evaluate")
    def proactive_evaluate(
        session_id: str,
        body: ProactiveEvaluateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return proactive.evaluate(
                session_id,
                sensor=body.sensor,
                observation=body.observation,
                significance=body.significance,
                message=body.message,
                confidence=body.confidence,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/proactive/{session_id}/stop")
    def proactive_stop(
        session_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return proactive.stop(session_id)

    @router.get("/qualification/l4")
    def l4_status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "qualification:read")
        return require_component(l4, "L4 physical-device qualification").all_status()

    @router.post("/qualification/l4/{platform}")
    def record_l4(
        platform: str,
        body: L4EvidenceBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "qualification:record")
        try:
            return require_component(l4, "L4 physical-device qualification").record(platform, body.model_dump())
        except Exception as exc:
            raise translate(exc) from exc

    return router
