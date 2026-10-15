from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from sensorium.physical import DesktopPhysicalSensorAdapter, MobilePhysicalSensorAdapter
from server.sensorium_camera_api import sensorium_camera_router
from server.sensorium_fusion_api import sensorium_fusion_router
from server.sensorium_native_api import sensorium_native_router


def sensorium_physical_router(runtime) -> APIRouter:
    """Physical Sensorium plus governed native-device and multimodal surfaces.

    Sensor observations are evidence only. Camera/context routes never inherit
    Computer Control, ToolRegistry, Device Control, approval or execution
    authority; those remain separate governed systems.
    """

    root = APIRouter()
    router = APIRouter(prefix="/sensorium/physical", tags=["sensorium"])
    registry = runtime.get("device_registry") if runtime else None
    gateway = runtime.get("device_gateway") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None:
        raise RuntimeError("device_registry is required for physical Sensorium")

    desktop = runtime.get("sensorium_desktop") if runtime else None
    if desktop is None:
        desktop = DesktopPhysicalSensorAdapter(
            registry,
            computer=runtime.get("computer") if runtime else None,
            event_bus=events,
        )
        runtime["sensorium_desktop"] = desktop

    mobile = runtime.get("sensorium_mobile") if runtime else None
    if mobile is None and gateway is not None:
        mobile = MobilePhysicalSensorAdapter(registry, gateway, event_bus=events)
        runtime["sensorium_mobile"] = mobile

    def controller(authorization: str | None, device_id: str | None, scope: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token:
            raise HTTPException(401, "Device authentication required")
        if not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication failed")
        if not registry.authorize(resolved, scope):
            raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    @router.get("/desktop/context")
    def desktop_context(
        include_clipboard_content: bool = Query(default=False),
        include_screen_analysis: bool = Query(default=False),
        monitor: int = Query(default=1, ge=1, le=32),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        if include_clipboard_content or include_screen_analysis:
            controller(authorization, x_device_id, "memory:sensitive")
        try:
            return desktop.context_snapshot(
                device_id,
                include_clipboard_content=include_clipboard_content,
                include_screen_analysis=include_screen_analysis,
                monitor=monitor,
            )
        except PermissionError as exc:
            raise HTTPException(403, "Physical desktop observation is not permitted") from exc
        except RuntimeError as exc:
            raise HTTPException(409, "Physical desktop observation is unavailable") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/mobile/{target_device_id}/context")
    async def mobile_context(
        target_device_id: str,
        timeout: float = Query(default=15.0, ge=1.0, le=30.0),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        if mobile is None:
            raise HTTPException(503, "Mobile Sensorium gateway unavailable")
        try:
            return await mobile.observe(device_id, target_device_id, timeout=timeout)
        except PermissionError as exc:
            raise HTTPException(403, "Physical mobile observation is not permitted") from exc
        except TimeoutError as exc:
            raise HTTPException(504, "Physical mobile observation timed out") from exc
        except RuntimeError as exc:
            raise HTTPException(409, "Physical mobile observation is unavailable") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    root.include_router(router)
    # Model-less qualification runtimes intentionally retain only physical/native
    # evidence surfaces. Camera and fusion reasoning mount only in full runtimes.
    if runtime.get("models") is not None:
        root.include_router(sensorium_camera_router(runtime))
        root.include_router(sensorium_fusion_router(runtime))
    settings = runtime.get("settings") if runtime else None
    native_lab = runtime.get("sensorium_native_lab") if runtime else None
    if native_lab is not None or getattr(settings, "data_dir", None) is not None:
        root.include_router(sensorium_native_router(runtime))
    return root
