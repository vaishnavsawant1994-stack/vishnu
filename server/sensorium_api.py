from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium import (
    DataClassification,
    DeviceState,
    SensorKind,
    SensoriumService,
    VirtualDevice,
    VirtualDeviceLab,
)


class VirtualDeviceCreateBody(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=80)
    capabilities: list[str] = Field(min_length=1, max_length=64)
    metadata: dict = Field(default_factory=dict)


class VirtualDeviceStateBody(BaseModel):
    state: str = Field(min_length=1, max_length=32)


class VirtualScreenBody(BaseModel):
    analysis: str = Field(default="", max_length=20_000)
    width: int | None = Field(default=None, ge=1, le=32768)
    height: int | None = Field(default=None, ge=1, le=32768)
    elements: list[dict] = Field(default_factory=list, max_length=256)
    frame_ref: str | None = Field(default=None, max_length=1000)
    screen_fingerprint: str | None = Field(default=None, max_length=256)
    data_classification: str = Field(default=DataClassification.INTERNAL.value, max_length=32)
    correlation_id: str | None = Field(default=None, max_length=128)


class VirtualClipboardBody(BaseModel):
    text: str = Field(max_length=16_384)
    mime_type: str = Field(default="text/plain", max_length=120)
    data_classification: str = Field(default=DataClassification.SENSITIVE.value, max_length=32)
    correlation_id: str | None = Field(default=None, max_length=128)


class VirtualSystemBody(BaseModel):
    metrics: dict = Field(default_factory=dict)
    data_classification: str = Field(default=DataClassification.INTERNAL.value, max_length=32)
    correlation_id: str | None = Field(default=None, max_length=128)


def _event_receipt(event: dict) -> dict:
    return {
        key: event.get(key)
        for key in (
            "event_id",
            "device_id",
            "kind",
            "timestamp",
            "data_classification",
            "source",
            "correlation_id",
        )
    }


def sensorium_router(runtime) -> APIRouter:
    """Authenticated, virtual-only Sensorium API.

    This router deliberately exposes no physical camera, microphone, screen
    capture, keyboard, mouse, or desktop-control dispatch authority. Sensorium
    context is untrusted input and never grants execution authority.
    """

    router = APIRouter(prefix="/sensorium", tags=["sensorium"])
    registry = runtime.get("device_registry") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None:
        raise RuntimeError("device_registry is required for Sensorium")

    lab = runtime.get("sensorium_lab") if runtime else None
    if lab is None:
        lab = VirtualDeviceLab.from_device_registry(registry, event_bus=events)
        runtime["sensorium_lab"] = lab

    def controller(
        authorization: str | None,
        device_id: str | None,
        scope: str,
    ) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token:
            raise HTTPException(401, "Device authentication required")
        if not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication failed")
        if not registry.authorize(resolved, scope):
            raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def service(virtual_device_id: str, controller_device_id: str) -> SensoriumService:
        return SensoriumService(
            lab,
            virtual_device_id=virtual_device_id,
            controller_device_id=controller_device_id,
            event_bus=events,
        )

    @router.get("/virtual-devices")
    def list_virtual_devices(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        return {"devices": lab.list_devices(controller_device_id=device_id)}

    @router.post("/virtual-devices")
    def create_virtual_device(
        body: VirtualDeviceCreateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            virtual = VirtualDevice(
                device_id=body.device_id,
                name=body.name,
                platform=body.platform,
                capabilities=frozenset(SensorKind(value) for value in body.capabilities),
                metadata=dict(body.metadata),
            )
            return {"device": lab.register_device(virtual, controller_device_id=device_id)}
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/virtual-devices/{virtual_device_id}/state")
    def set_virtual_device_state(
        virtual_device_id: str,
        body: VirtualDeviceStateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            return {
                "device": lab.set_state(
                    virtual_device_id,
                    DeviceState(body.state),
                    controller_device_id=device_id,
                )
            }
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.delete("/virtual-devices/{virtual_device_id}")
    def delete_virtual_device(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            lab.remove_device(virtual_device_id, controller_device_id=device_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"removed": True, "virtual_device_id": virtual_device_id}

    @router.post("/virtual-devices/{virtual_device_id}/screen")
    def publish_virtual_screen(
        virtual_device_id: str,
        body: VirtualScreenBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            published = service(virtual_device_id, device_id).screen.publish(
                analysis=body.analysis,
                width=body.width,
                height=body.height,
                elements=body.elements,
                frame_ref=body.frame_ref,
                screen_fingerprint=body.screen_fingerprint,
                data_classification=DataClassification(body.data_classification),
                correlation_id=body.correlation_id,
            )
            return {"event": _event_receipt(published)}
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (PermissionError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/virtual-devices/{virtual_device_id}/clipboard")
    def publish_virtual_clipboard(
        virtual_device_id: str,
        body: VirtualClipboardBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            published = service(virtual_device_id, device_id).clipboard.publish(
                body.text,
                mime_type=body.mime_type,
                data_classification=DataClassification(body.data_classification),
                correlation_id=body.correlation_id,
            )
            return {"event": _event_receipt(published)}
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (PermissionError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/virtual-devices/{virtual_device_id}/system")
    def publish_virtual_system(
        virtual_device_id: str,
        body: VirtualSystemBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            published = service(virtual_device_id, device_id).system.publish(
                body.metrics,
                data_classification=DataClassification(body.data_classification),
                correlation_id=body.correlation_id,
            )
            return {"event": _event_receipt(published)}
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (PermissionError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/virtual-devices/{virtual_device_id}/context")
    def virtual_context(
        virtual_device_id: str,
        include_clipboard_content: bool = Query(default=False),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        if include_clipboard_content:
            controller(authorization, x_device_id, "memory:sensitive")
        try:
            return service(virtual_device_id, device_id).context_snapshot(
                include_clipboard_content=include_clipboard_content
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/virtual-devices/{virtual_device_id}/planner-observation")
    def planner_observation(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        try:
            return service(virtual_device_id, device_id).planner_observation()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
