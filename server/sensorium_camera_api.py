from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium.biometrics import BiometricIdentityStore
from sensorium.camera import CameraVisionService
from sensorium.desktop_camera import DesktopCameraAdapter
from sensorium.external_camera import ExternalCameraRegistry
from sensorium.live_vision import LiveVisionManager
from sensorium.sensor_permissions import SensorPermissionStore
from sensorium.visual_memory import VisualMemoryManager


class PrivacyBody(BaseModel):
    max_edge: int = Field(default=1024, ge=64, le=1280)
    crop: dict | None = None
    redact_regions: list[dict] = Field(default_factory=list, max_length=64)
    faces_processed: bool = False
    require_face_redaction: bool = False


class BrowserCameraSnapshot(BaseModel):
    data_url: str = Field(min_length=32, max_length=2_100_000)
    question: str = Field(default="Describe what the camera can currently see.", min_length=1, max_length=2_000)
    resource_id: str = Field(default="browser:default", min_length=1, max_length=240)
    sensor_session_id: str = Field(min_length=8, max_length=200)
    task_mode: str = Field(default="general", max_length=40)
    memory_mode: str = Field(default="none", max_length=40)
    speak: bool = False
    privacy: PrivacyBody = Field(default_factory=PrivacyBody)


class SensorPolicyBody(BaseModel):
    resource_id: str = Field(default="*", min_length=1, max_length=240)
    mode: str = Field(min_length=3, max_length=16)


class SensorSessionBody(BaseModel):
    resource_id: str = Field(default="*", min_length=1, max_length=240)
    ttl_seconds: float = Field(default=300, ge=30, le=600)
    session_id: str | None = Field(default=None, min_length=8, max_length=200)
    explicit_consent: bool = False


class CameraSnapshotOptions(BaseModel):
    question: str = Field(default="Describe what the camera can currently see.", min_length=1, max_length=2_000)
    camera_id: str | None = Field(default=None, max_length=240)
    facing: str = Field(default="front", max_length=20)
    sensor_session_id: str | None = Field(default=None, min_length=8, max_length=200)
    task_mode: str = Field(default="general", max_length=40)
    memory_mode: str = Field(default="none", max_length=40)
    speak: bool = False
    privacy: PrivacyBody = Field(default_factory=PrivacyBody)


class LiveStartBody(BaseModel):
    target_device_id: str | None = Field(default=None, max_length=200)
    resource_id: str = Field(min_length=1, max_length=240)
    question: str = Field(default="Watch for meaningful changes and tell me what I should know.", min_length=1, max_length=2_000)
    task_mode: str = Field(default="general", max_length=40)
    memory_mode: str = Field(default="none", max_length=40)
    sample_fps: float = Field(default=0.5, ge=0.2, le=1.0)
    duration_seconds: float = Field(default=300, ge=30, le=600)
    scene_threshold: float = Field(default=0.035, ge=0, le=1)
    max_frames: int = Field(default=150, ge=1, le=600)
    max_bytes: int = Field(default=40 * 1024 * 1024, ge=1_000_000, le=120 * 1024 * 1024)
    max_model_calls: int = Field(default=90, ge=1, le=300)


class BrowserLiveTickBody(BaseModel):
    data_url: str = Field(min_length=32, max_length=2_100_000)
    sensor_session_id: str = Field(min_length=8, max_length=200)
    speak: bool = False
    privacy: PrivacyBody = Field(default_factory=PrivacyBody)


class MobileLiveTickBody(BaseModel):
    speak: bool = False
    privacy: PrivacyBody = Field(default_factory=PrivacyBody)


class ExternalCameraBody(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    snapshot_url: str = Field(min_length=8, max_length=2_000)
    auth_kind: str = Field(default="none", max_length=20)
    credential: str | None = Field(default=None, max_length=4_096)


class BiometricEnableBody(BaseModel):
    enabled: bool
    explicit_consent: bool = False


class BiometricEnrollBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    template: list[float] = Field(min_length=16, max_length=4096)
    explicit_consent: bool = False


class BiometricMatchBody(BaseModel):
    template: list[float] = Field(min_length=16, max_length=4096)
    sensor_session_id: str = Field(min_length=8, max_length=200)
    threshold: float = Field(default=0.82, ge=0, le=1)


def sensorium_camera_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/camera", tags=["sensorium", "camera"])
    registry = runtime.get("device_registry") if runtime else None
    gateway = runtime.get("device_gateway") if runtime else None
    models = runtime.get("models") if runtime else None
    events = runtime.get("events") if runtime else None
    settings = runtime.get("settings") if runtime else None
    if registry is None or models is None:
        raise RuntimeError("camera Sensorium requires device registry and model router")

    data_dir = getattr(settings, "data_dir", None)
    vault = runtime.get("vault") if runtime else None
    if vault is None:
        vault = getattr(models, "vault", None)
    memory = runtime.get("memory") if runtime else None
    voice = runtime.get("voice") if runtime else None

    permissions = runtime.get("sensor_permissions") if runtime else None
    if permissions is None and data_dir is not None:
        permissions = SensorPermissionStore(data_dir / "sensor-permissions.sqlite3", events=events)
        runtime["sensor_permissions"] = permissions

    live = runtime.get("sensorium_live_vision") if runtime else None
    if live is None:
        live = LiveVisionManager(events=events)
        runtime["sensorium_live_vision"] = live

    visual_memory = runtime.get("sensorium_visual_memory") if runtime else None
    if visual_memory is None:
        visual_memory = VisualMemoryManager(memory, data_dir=data_dir, vault=vault, events=events)
        runtime["sensorium_visual_memory"] = visual_memory

    desktop = runtime.get("sensorium_desktop_camera") if runtime else None
    if desktop is None:
        desktop = DesktopCameraAdapter(events=events)
        runtime["sensorium_desktop_camera"] = desktop

    external = runtime.get("sensorium_external_cameras") if runtime else None
    if external is None and data_dir is not None and vault is not None:
        external = ExternalCameraRegistry(data_dir / "external-cameras.sqlite3", vault=vault, events=events)
        runtime["sensorium_external_cameras"] = external

    biometric = runtime.get("sensorium_biometrics") if runtime else None
    if biometric is None and data_dir is not None and vault is not None:
        biometric = BiometricIdentityStore(data_dir / "biometrics.sqlite3", vault=vault, events=events)
        runtime["sensorium_biometrics"] = biometric

    service = runtime.get("sensorium_camera") if runtime else None
    if service is None:
        service = CameraVisionService(
            registry,
            gateway,
            models,
            event_bus=events,
            sensor_permissions=permissions,
            live_manager=live,
            visual_memory=visual_memory,
            desktop_camera=desktop,
            external_cameras=external,
            voice_runtime=voice,
        )
        runtime["sensorium_camera"] = service

    def controller(
        authorization: str | None,
        device_id: str | None,
        *,
        sensitive: bool = True,
        admin: bool = False,
        scope: str = "sensor:camera",
    ) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token:
            raise HTTPException(401, "Device authentication required")
        if not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication failed")
        if not registry.authorize(resolved, "device:read"):
            raise HTTPException(403, "Device is not permitted to read device context")
        if not registry.authorize(resolved, scope):
            raise HTTPException(403, f"Device is not permitted to use {scope}")
        if sensitive and not registry.authorize(resolved, "memory:sensitive"):
            raise HTTPException(403, "Camera observation requires sensitive-context permission")
        if admin and not registry.authorize(resolved, "device:admin"):
            raise HTTPException(403, "Camera administration requires device:admin")
        return resolved

    def translate(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc)[:240] or "Camera observation is not permitted")
        if isinstance(exc, KeyError):
            return HTTPException(404, str(exc)[:240] or "Camera resource was not found")
        if isinstance(exc, TimeoutError):
            return HTTPException(504, str(exc)[:240] or "Camera observation timed out")
        if isinstance(exc, ValueError):
            return HTTPException(422, str(exc))
        if isinstance(exc, RuntimeError) and "interval has not elapsed" in str(exc):
            return HTTPException(429, "Live Vision sample interval has not elapsed")
        return HTTPException(409, str(exc)[:240] or "Camera observation is unavailable")

    def privacy_dict(body: PrivacyBody) -> dict:
        return body.model_dump()

    @router.get("/permission")
    def camera_permission(
        resource_id: str = Query(default="*", min_length=1, max_length=240),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.permission(device_id, resource_id=resource_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/permission")
    def set_camera_permission(
        body: SensorPolicyBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.set_permission_policy(device_id, resource_id=body.resource_id, mode=body.mode)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/session/grant")
    def grant_camera_session(
        body: SensorSessionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        if not body.explicit_consent:
            raise HTTPException(400, "explicit local camera consent is required")
        try:
            return service.grant_local_session(
                device_id,
                resource_id=body.resource_id,
                ttl_seconds=body.ttl_seconds,
                session_id=body.session_id,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/session/revoke")
    def revoke_camera_session(
        body: SensorSessionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.revoke_local_session(device_id, resource_id=body.resource_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/browser/snapshot")
    def browser_snapshot(
        body: BrowserCameraSnapshot,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.analyze_browser_snapshot(
                device_id,
                data_url=body.data_url,
                question=body.question,
                resource_id=body.resource_id,
                sensor_session_id=body.sensor_session_id,
                privacy=privacy_dict(body.privacy),
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/mobile/{target_device_id}/sources")
    async def mobile_camera_sources(
        target_device_id: str,
        timeout: float = Query(default=10.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return {"cameras": await service.mobile_sources(device_id, target_device_id, timeout=timeout)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/mobile/{target_device_id}/status")
    async def mobile_camera_status(
        target_device_id: str,
        timeout: float = Query(default=10.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.status(device_id, target_device_id, timeout=timeout)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/start")
    async def mobile_camera_start(
        target_device_id: str,
        facing: str = Query(default="front"),
        camera_id: str | None = Query(default=None, max_length=240),
        timeout: float = Query(default=15.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.start(
                device_id, target_device_id, facing=facing, camera_id=camera_id, timeout=timeout
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/snapshot")
    async def mobile_camera_snapshot(
        target_device_id: str,
        body: CameraSnapshotOptions,
        timeout: float = Query(default=25.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.snapshot(
                device_id,
                target_device_id,
                question=body.question,
                facing=body.facing,
                camera_id=body.camera_id,
                timeout=timeout,
                privacy=privacy_dict(body.privacy),
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/stop")
    async def mobile_camera_stop(
        target_device_id: str,
        camera_id: str | None = Query(default=None, max_length=240),
        timeout: float = Query(default=10.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.stop(device_id, target_device_id, camera_id=camera_id, timeout=timeout)
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/desktop/sources")
    def desktop_camera_sources(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, admin=True)
        try:
            return {"cameras": service.desktop_sources(device_id)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/desktop/snapshot")
    def desktop_camera_snapshot(
        body: CameraSnapshotOptions,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, admin=True)
        try:
            return service.desktop_snapshot(
                device_id,
                camera_id=body.camera_id or "auto",
                sensor_session_id=body.sensor_session_id,
                question=body.question,
                privacy=privacy_dict(body.privacy),
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/external")
    def external_camera_sources(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, admin=True)
        try:
            return {"cameras": service.external_sources(device_id)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/external")
    def register_external_camera(
        body: ExternalCameraBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, admin=True)
        if external is None:
            raise HTTPException(503, "external camera registry unavailable")
        try:
            camera = external.register(
                label=body.label,
                snapshot_url=body.snapshot_url,
                auth_kind=body.auth_kind,
                credential=body.credential,
            )
            camera["snapshot_url"] = None
            return camera
        except Exception as exc:
            raise translate(exc) from exc

    @router.delete("/external/{camera_id}")
    def revoke_external_camera(
        camera_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, admin=True)
        if external is None:
            raise HTTPException(503, "external camera registry unavailable")
        try:
            return {"camera_id": camera_id, "revoked": external.revoke(camera_id)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/external/{camera_id}/snapshot")
    def external_camera_snapshot(
        camera_id: str,
        body: CameraSnapshotOptions,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, admin=True)
        try:
            return service.external_snapshot(
                device_id,
                camera_id=camera_id,
                sensor_session_id=body.sensor_session_id,
                question=body.question,
                privacy=privacy_dict(body.privacy),
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/live/start")
    def live_start(
        body: LiveStartBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        target = body.target_device_id or device_id
        try:
            return service.start_live(
                device_id,
                target,
                resource_id=body.resource_id,
                question=body.question,
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                sample_fps=body.sample_fps,
                duration_seconds=body.duration_seconds,
                scene_threshold=body.scene_threshold,
                max_frames=body.max_frames,
                max_bytes=body.max_bytes,
                max_model_calls=body.max_model_calls,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/live/{session_id}/browser/tick")
    def browser_live_tick(
        session_id: str,
        body: BrowserLiveTickBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.live_browser_tick(
                device_id,
                session_id,
                data_url=body.data_url,
                sensor_session_id=body.sensor_session_id,
                privacy=privacy_dict(body.privacy),
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/live/{session_id}/mobile/tick")
    async def mobile_live_tick(
        session_id: str,
        body: MobileLiveTickBody,
        timeout: float = Query(default=25.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.live_mobile_tick(
                device_id,
                session_id,
                privacy=privacy_dict(body.privacy),
                speak=body.speak,
                timeout=timeout,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/live/{session_id}/stop")
    def live_stop(
        session_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.stop_live(device_id, session_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/biometric")
    def biometric_status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(
            authorization, x_device_id, admin=True, scope="sensor:biometric"
        )
        if biometric is None or permissions is None:
            raise HTTPException(503, "biometric identity unavailable")
        return {
            "enabled": biometric.enabled(),
            "profiles": biometric.list_profiles(),
            "permission": permissions.permission(device_id, "biometric", "*"),
            "camera_vision_integration": False,
        }

    @router.post("/biometric/enable")
    def biometric_enable(
        body: BiometricEnableBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, admin=True, scope="sensor:biometric")
        if biometric is None:
            raise HTTPException(503, "biometric identity unavailable")
        try:
            return {"enabled": biometric.set_enabled(body.enabled, explicit_consent=body.explicit_consent)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/biometric/session")
    def biometric_session(
        body: SensorSessionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(
            authorization, x_device_id, admin=True, scope="sensor:biometric"
        )
        if permissions is None:
            raise HTTPException(503, "sensor permission authority unavailable")
        if not body.explicit_consent:
            raise HTTPException(400, "explicit biometric consent is required")
        try:
            # Biometric default is never. Explicit owner consent for this session
            # temporarily changes the wildcard resource to ask before granting;
            # there is still no durable always-allow mode.
            current = permissions.permission(device_id, "biometric", "*")
            if current["mode"] == "never":
                permissions.set_policy(device_id, "biometric", "ask", "*")
            return permissions.grant_session(
                device_id,
                "biometric",
                "*",
                ttl_seconds=body.ttl_seconds,
                session_id=body.session_id,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/biometric/enroll")
    def biometric_enroll(
        body: BiometricEnrollBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, admin=True, scope="sensor:biometric")
        if biometric is None:
            raise HTTPException(503, "biometric identity unavailable")
        try:
            return biometric.enroll(body.label, body.template, explicit_consent=body.explicit_consent)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/biometric/match")
    def biometric_match(
        body: BiometricMatchBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(
            authorization, x_device_id, admin=True, scope="sensor:biometric"
        )
        if biometric is None or permissions is None:
            raise HTTPException(503, "biometric identity unavailable")
        if not permissions.allows(device_id, "biometric", "*", session_id=body.sensor_session_id):
            raise HTTPException(403, "biometric identity requires an explicit active session")
        try:
            return {"match": biometric.match(body.template, threshold=body.threshold)}
        except Exception as exc:
            raise translate(exc) from exc

    @router.delete("/biometric/{profile_id}")
    def biometric_delete(
        profile_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, admin=True, scope="sensor:biometric")
        if biometric is None:
            raise HTTPException(503, "biometric identity unavailable")
        try:
            return {"profile_id": profile_id, "deleted": biometric.delete(profile_id)}
        except Exception as exc:
            raise translate(exc) from exc

    return router
