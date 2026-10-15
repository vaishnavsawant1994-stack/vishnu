from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium.camera import CameraVisionService


class BrowserCameraSnapshot(BaseModel):
    data_url: str = Field(min_length=32, max_length=2_100_000)
    question: str = Field(default="Describe what the camera can currently see.", min_length=1, max_length=2_000)


def sensorium_camera_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/camera", tags=["sensorium", "camera"])
    registry = runtime.get("device_registry") if runtime else None
    gateway = runtime.get("device_gateway") if runtime else None
    models = runtime.get("models") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None or models is None:
        raise RuntimeError("camera Sensorium requires device registry and model router")

    service = runtime.get("sensorium_camera") if runtime else None
    if service is None:
        service = CameraVisionService(registry, gateway, models, event_bus=events)
        runtime["sensorium_camera"] = service

    def controller(authorization: str | None, device_id: str | None, *, sensitive: bool = True) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token:
            raise HTTPException(401, "Device authentication required")
        if not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication failed")
        if not registry.authorize(resolved, "device:read"):
            raise HTTPException(403, "Device is not permitted to read device context")
        if sensitive and not registry.authorize(resolved, "memory:sensitive"):
            raise HTTPException(403, "Remote camera observation requires sensitive-context permission")
        return resolved

    def translate(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, "Camera observation is not permitted")
        if isinstance(exc, TimeoutError):
            return HTTPException(504, "Camera observation timed out")
        if isinstance(exc, ValueError):
            return HTTPException(422, str(exc))
        return HTTPException(409, "Camera observation is unavailable")

    @router.post("/browser/snapshot")
    def browser_snapshot(
        body: BrowserCameraSnapshot,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        # Browser camera permission and the explicit Analyze action happen on the
        # same paired device that submits this one frame. The frame is still
        # classified sensitive at the model-routing boundary. Remote mobile
        # camera reads remain gated by memory:sensitive + device:admin.
        device_id = controller(authorization, x_device_id, sensitive=False)
        try:
            return service.analyze_browser_snapshot(
                device_id,
                data_url=body.data_url,
                question=body.question,
            )
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
        timeout: float = Query(default=15.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.start(device_id, target_device_id, facing=facing, timeout=timeout)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/snapshot")
    async def mobile_camera_snapshot(
        target_device_id: str,
        question: str = Query(default="Describe what the camera can currently see.", min_length=1, max_length=2_000),
        facing: str = Query(default="front"),
        timeout: float = Query(default=25.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.snapshot(
                device_id,
                target_device_id,
                question=question,
                facing=facing,
                timeout=timeout,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/mobile/{target_device_id}/stop")
    async def mobile_camera_stop(
        target_device_id: str,
        timeout: float = Query(default=10.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id)
        try:
            return await service.stop(device_id, target_device_id, timeout=timeout)
        except Exception as exc:
            raise translate(exc) from exc

    return router
