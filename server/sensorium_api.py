from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium import (
    DataClassification,
    DeviceState,
    NetworkType,
    PermissionState,
    SensorKind,
    SensoriumService,
    VirtualDevice,
    VirtualDeviceFleet,
    VirtualDeviceLab,
    VirtualFault,
    VirtualPlatform,
)
from sensorium.live_work import SensoriumLiveWorkProjection


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


class VirtualFleetProvisionBody(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=80)


class VirtualBatteryBody(BaseModel):
    percent: int = Field(ge=0, le=100)
    charging: bool = False


class VirtualNetworkBody(BaseModel):
    network_type: str = Field(default=NetworkType.WIFI.value, max_length=32)
    online: bool | None = None
    airplane_mode: bool = False
    signal_percent: int = Field(default=100, ge=0, le=100)


class VirtualPermissionBody(BaseModel):
    state: str = Field(min_length=1, max_length=32)


class VirtualLocationBody(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float = Field(default=10.0, ge=0, le=100_000)


class VirtualForegroundBody(BaseModel):
    app_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)


class VirtualLockBody(BaseModel):
    locked: bool


class VirtualNotificationBody(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=4096)
    app_id: str = Field(default="fixture.app", min_length=1, max_length=200)


class VirtualCameraFixtureBody(BaseModel):
    fixture_ref: str = Field(min_length=1, max_length=1000)
    analysis: str = Field(default="", max_length=20_000)
    width: int = Field(default=1280, ge=1, le=32768)
    height: int = Field(default=720, ge=1, le=32768)


class VirtualMicrophoneFixtureBody(BaseModel):
    fixture_ref: str = Field(min_length=1, max_length=1000)
    transcript: str = Field(default="", max_length=20_000)
    duration_ms: int = Field(default=1000, ge=0, le=600_000)


class VirtualFaultBody(BaseModel):
    fault: str = Field(min_length=1, max_length=64)
    permission: str = Field(default="camera", min_length=1, max_length=64)


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
    """Authenticated Sensorium API for virtual simulation and safe context.

    This router deliberately exposes no physical camera, microphone, screen
    capture, keyboard, mouse, or desktop-control dispatch authority. Virtual
    fleet mutations affect simulation state only. Sensorium context is
    untrusted input and never grants execution authority.
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

    fleet = runtime.get("sensorium_virtual_fleet") if runtime else None
    if fleet is None:
        fleet = VirtualDeviceFleet(lab)
        runtime["sensorium_virtual_fleet"] = fleet

    live_work = runtime.get("sensorium_live_work") if runtime else None
    if live_work is None and events is not None:
        live_work = SensoriumLiveWorkProjection(events)
        runtime["sensorium_live_work"] = live_work

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

    def require_sensitive(authorization: str | None, device_id: str | None) -> None:
        controller(authorization, device_id, "memory:sensitive")

    def service(virtual_device_id: str, controller_device_id: str) -> SensoriumService:
        return SensoriumService(
            lab,
            virtual_device_id=virtual_device_id,
            controller_device_id=controller_device_id,
            event_bus=events,
        )

    def fleet_http_error(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(404, str(exc))
        if isinstance(exc, PermissionError):
            return HTTPException(409, str(exc))
        if isinstance(exc, RuntimeError):
            return HTTPException(409, str(exc))
        return HTTPException(422, str(exc))

    @router.get("/live-work")
    def live_work_snapshot(
        limit: int = Query(default=50, ge=1, le=200),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, "device:read")
        if live_work is None:
            raise HTTPException(503, "Sensorium Live Work projection unavailable")
        return live_work.snapshot(limit=limit)

    @router.get("/virtual-fleet/profiles")
    def virtual_fleet_profiles(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, "device:read")
        return {"profiles": fleet.profiles(), "execution_authority": False}

    @router.get("/virtual-fleet")
    def list_virtual_fleet(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        return {"devices": fleet.list(controller_device_id=device_id), "execution_authority": False}

    @router.post("/virtual-fleet/{virtual_device_id}")
    def provision_virtual_fleet_device(
        virtual_device_id: str,
        body: VirtualFleetProvisionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.provision(
                device_id=virtual_device_id,
                platform=VirtualPlatform(body.platform),
                name=body.name,
                os_version=body.os_version,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.get("/virtual-fleet/{virtual_device_id}")
    def virtual_fleet_snapshot(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:read")
        try:
            return fleet.snapshot(virtual_device_id, controller_device_id=device_id)
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.delete("/virtual-fleet/{virtual_device_id}")
    def remove_virtual_fleet_device(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            fleet.remove(virtual_device_id, controller_device_id=device_id)
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc
        return {"removed": True, "virtual_device_id": virtual_device_id}

    @router.post("/virtual-fleet/{virtual_device_id}/battery")
    def update_virtual_battery(
        virtual_device_id: str,
        body: VirtualBatteryBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.set_battery(
                virtual_device_id,
                body.percent,
                charging=body.charging,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/network")
    def update_virtual_network(
        virtual_device_id: str,
        body: VirtualNetworkBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.set_network(
                virtual_device_id,
                NetworkType(body.network_type),
                online=body.online,
                airplane_mode=body.airplane_mode,
                signal_percent=body.signal_percent,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/permissions/{permission}")
    def update_virtual_permission(
        virtual_device_id: str,
        permission: str,
        body: VirtualPermissionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.set_permission(
                virtual_device_id,
                permission,
                PermissionState(body.state),
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/location")
    def update_virtual_location(
        virtual_device_id: str,
        body: VirtualLocationBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        require_sensitive(authorization, x_device_id)
        try:
            return fleet.set_location(
                virtual_device_id,
                body.latitude,
                body.longitude,
                accuracy_meters=body.accuracy_meters,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/foreground-app")
    def update_virtual_foreground_app(
        virtual_device_id: str,
        body: VirtualForegroundBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        require_sensitive(authorization, x_device_id)
        try:
            return fleet.set_foreground_app(
                virtual_device_id,
                body.app_id,
                title=body.title,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/lock")
    def update_virtual_lock(
        virtual_device_id: str,
        body: VirtualLockBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.set_locked(
                virtual_device_id,
                body.locked,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/notification")
    def publish_virtual_notification(
        virtual_device_id: str,
        body: VirtualNotificationBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        require_sensitive(authorization, x_device_id)
        try:
            result = fleet.push_notification(
                virtual_device_id,
                title=body.title,
                body=body.body,
                app_id=body.app_id,
                controller_device_id=device_id,
            )
            return {"event": _event_receipt(result["event"]), "runtime": result["runtime"]}
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/camera-fixture")
    def publish_virtual_camera_fixture(
        virtual_device_id: str,
        body: VirtualCameraFixtureBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        require_sensitive(authorization, x_device_id)
        try:
            event = fleet.publish_camera_fixture(
                virtual_device_id,
                fixture_ref=body.fixture_ref,
                analysis=body.analysis,
                width=body.width,
                height=body.height,
                controller_device_id=device_id,
            )
            return {"event": _event_receipt(event)}
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/microphone-fixture")
    def publish_virtual_microphone_fixture(
        virtual_device_id: str,
        body: VirtualMicrophoneFixtureBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        require_sensitive(authorization, x_device_id)
        try:
            event = fleet.publish_microphone_fixture(
                virtual_device_id,
                fixture_ref=body.fixture_ref,
                transcript=body.transcript,
                duration_ms=body.duration_ms,
                controller_device_id=device_id,
            )
            return {"event": _event_receipt(event)}
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/disconnect")
    def disconnect_virtual_fleet_device(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        try:
            return fleet.disconnect(virtual_device_id, controller_device_id=device_id)
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/reconnect")
    def reconnect_virtual_fleet_device(
        virtual_device_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.reconnect(virtual_device_id, controller_device_id=device_id)
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

    @router.post("/virtual-fleet/{virtual_device_id}/fault")
    def simulate_virtual_fleet_fault(
        virtual_device_id: str,
        body: VirtualFaultBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = controller(authorization, x_device_id, "device:admin")
        controller(authorization, x_device_id, "device:read")
        try:
            return fleet.simulate_fault(
                virtual_device_id,
                VirtualFault(body.fault),
                permission=body.permission,
                controller_device_id=device_id,
            )
        except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            raise fleet_http_error(exc) from exc

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
