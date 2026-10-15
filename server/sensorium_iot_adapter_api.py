from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from sensorium.iot_adapters import HomeAssistantObservationAdapter


class HomeAssistantRegisterBody(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    base_url: str = Field(min_length=8, max_length=2048)
    bearer_token: str = Field(min_length=12, max_length=8192)
    allow_private_http: bool = False
    verify_tls: bool = True


class HomeAssistantObserveBody(BaseModel):
    entity_id: str = Field(min_length=3, max_length=200)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=10.0)


def sensorium_iot_adapter_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/v2/iot-adapters", tags=["sensorium", "iot"])
    registry = runtime.get("device_registry") if runtime else None
    settings = runtime.get("settings") if runtime else None
    events = runtime.get("events") if runtime else None
    models = runtime.get("models") if runtime else None
    vault = runtime.get("vault") if runtime else None
    if vault is None and models is not None:
        vault = getattr(models, "vault", None)
    if registry is None:
        raise RuntimeError("Sensorium IoT adapters require device registry")

    data_dir_value = getattr(settings, "data_dir", None)
    data_dir = Path(data_dir_value) if data_dir_value is not None else None
    adapters = runtime.get("sensorium_iot_adapters") if runtime else None
    if adapters is None and data_dir is not None and vault is not None:
        adapters = HomeAssistantObservationAdapter(
            data_dir / "sensorium-iot-adapters.sqlite3",
            vault=vault,
            events=events,
        )
        runtime["sensorium_iot_adapters"] = adapters

    def auth(authorization: str | None, device_id: str | None, *scopes: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in scopes:
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def require_adapter():
        if adapters is None:
            raise HTTPException(503, "Smart-home observation adapter is unavailable in this runtime")
        return adapters

    @router.get("")
    def list_adapters(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "sensor:iot")
        return {"adapters": require_adapter().list(), "execution_authority": False}

    @router.post("/home-assistant")
    def register_home_assistant(
        body: HomeAssistantRegisterBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "sensor:iot", "memory:sensitive")
        try:
            return require_adapter().register(
                label=body.label,
                base_url=body.base_url,
                bearer_token=body.bearer_token,
                allow_private_http=body.allow_private_http,
                verify_tls=body.verify_tls,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc

    @router.post("/{adapter_id}/observe")
    def observe_home_assistant(
        adapter_id: str,
        body: HomeAssistantObserveBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "sensor:iot", "memory:sensitive")
        try:
            return require_adapter().observe_state(
                adapter_id,
                entity_id=body.entity_id,
                timeout_seconds=body.timeout_seconds,
            )
        except KeyError as exc:
            raise HTTPException(404, "IoT adapter not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (RuntimeError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.delete("/{adapter_id}")
    def revoke_adapter(
        adapter_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "sensor:iot")
        try:
            return {"revoked": require_adapter().revoke(adapter_id), "execution_authority": False}
        except KeyError as exc:
            raise HTTPException(404, "IoT adapter not found") from exc

    return router
