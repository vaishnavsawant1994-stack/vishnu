from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium import NativeDeviceEvidence, NativeDeviceLab, NativeProvider


class NativeEvidenceBody(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    provider: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)
    target_id: str = Field(min_length=1, max_length=192)
    status: str = Field(min_length=1, max_length=32)
    os_version: str = Field(min_length=1, max_length=120)
    architecture: str = Field(min_length=1, max_length=80)
    capabilities: list[str] = Field(default_factory=list, max_length=64)
    metadata: dict = Field(default_factory=dict)
    observed_at: str = Field(min_length=1, max_length=80)
    source: str = Field(default="native-device-lab", min_length=1, max_length=192)
    physical_device: bool = False
    execution_authority: bool = False


def sensorium_native_router(runtime) -> APIRouter:
    """Native emulator/simulator/VM qualification evidence surface.

    The API stores and reports read-only evidence. It intentionally exposes no
    adb, simctl, shell, VM-control, keyboard/mouse, app-launch or other command
    execution endpoint.
    """

    router = APIRouter(prefix="/sensorium/native", tags=["sensorium-native"])
    registry = runtime.get("device_registry") if runtime else None
    lab = runtime.get("sensorium_native_lab") if runtime else None
    if registry is None:
        raise RuntimeError("device_registry is required for native Sensorium")
    if lab is None or not isinstance(lab, NativeDeviceLab):
        raise RuntimeError("sensorium_native_lab is required for native Sensorium")

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

    @router.get("/providers")
    def providers(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, "device:read")
        return {
            "providers": lab.profiles(),
            "physical_device": False,
            "execution_authority": False,
        }

    @router.get("/evidence")
    def evidence(
        provider: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, "device:read")
        try:
            normalized = NativeProvider(provider) if provider else None
            return {
                "evidence": lab.list(limit=limit, provider=normalized),
                "physical_device": False,
                "execution_authority": False,
            }
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/evidence")
    def record_evidence(
        body: NativeEvidenceBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        controller(authorization, x_device_id, "device:admin")
        try:
            item = NativeDeviceEvidence.from_dict(body.model_dump())
            return {"evidence": lab.record(item)}
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
