from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium.vision_voice import VisionVoiceCoordinator


class VisionVoiceBrowserBody(BaseModel):
    transcript: str = Field(min_length=1, max_length=2_000)
    data_url: str = Field(min_length=32, max_length=2_100_000)
    resource_id: str = Field(min_length=1, max_length=240)
    sensor_session_id: str = Field(min_length=8, max_length=200)
    task_mode: str = Field(default="general", max_length=40)
    memory_mode: str = Field(default="none", max_length=40)
    speak: bool = True
    privacy: dict = Field(default_factory=dict)


class VisionVoiceMobileBody(BaseModel):
    transcript: str = Field(min_length=1, max_length=2_000)
    camera_id: str | None = Field(default=None, max_length=240)
    facing: str = Field(default="front", max_length=20)
    task_mode: str = Field(default="general", max_length=40)
    memory_mode: str = Field(default="none", max_length=40)
    speak: bool = True
    privacy: dict = Field(default_factory=dict)


def vision_voice_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/vision-voice", tags=["sensorium", "vision", "voice"])
    registry = runtime.get("device_registry") if runtime else None
    camera = runtime.get("sensorium_camera") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None or camera is None:
        raise RuntimeError("Vision + Voice requires the governed camera service")
    coordinator = runtime.get("sensorium_vision_voice") if runtime else None
    if coordinator is None:
        coordinator = VisionVoiceCoordinator(camera, events=events)
        runtime["sensorium_vision_voice"] = coordinator

    def controller(authorization: str | None, device_id: str | None, *, remote: bool) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in ("device:read", "sensor:camera"):
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        if remote and not registry.authorize(resolved, "memory:sensitive"):
            raise HTTPException(403, "Sensitive context permission is required")
        return resolved

    def translate(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError): return HTTPException(403, str(exc)[:240])
        if isinstance(exc, TimeoutError): return HTTPException(504, str(exc)[:240])
        if isinstance(exc, ValueError): return HTTPException(422, str(exc))
        return HTTPException(409, str(exc)[:240] or "Vision + Voice unavailable")

    @router.post("/browser")
    def browser(
        body: VisionVoiceBrowserBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, remote=False)
        try:
            return coordinator.browser(
                device_id,
                transcript=body.transcript,
                data_url=body.data_url,
                resource_id=body.resource_id,
                sensor_session_id=body.sensor_session_id,
                privacy=body.privacy,
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}")
    async def mobile(
        target_device_id: str,
        body: VisionVoiceMobileBody,
        timeout: float = Query(default=25.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, remote=True)
        try:
            return await coordinator.mobile(
                device_id,
                target_device_id,
                transcript=body.transcript,
                camera_id=body.camera_id,
                facing=body.facing,
                privacy=body.privacy,
                task_mode=body.task_mode,
                memory_mode=body.memory_mode,
                speak=body.speak,
                timeout=timeout,
            )
        except Exception as exc:
            raise translate(exc) from exc

    return router
