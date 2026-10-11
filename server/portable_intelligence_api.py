from __future__ import annotations

import os
import time
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from security.request_context import current_trusted_request
from training.contributions import ContributionMode


class ContributionSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["private", "aggregate", "training_contributor"] | None = None
    conversations: bool | None = None
    agent_outcomes: bool | None = None
    corrections: bool | None = None
    tool_metrics: bool | None = None
    documents: bool | None = None


class SpecialistBindingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialist_role: str = Field(min_length=1, max_length=80)
    task_domain: str = Field(default="general", min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=200)


class SpecialistUnbindBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialist_role: str = Field(min_length=1, max_length=80)
    task_domain: str = Field(default="general", min_length=1, max_length=120)


class ActivationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    online: bool = False


def portable_intelligence_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/owner/portable-intelligence", tags=["portable-intelligence"])
    registry = runtime["device_registry"]
    events = runtime.get("events")

    def authenticate(device_id: str | None, token: str | None, scope: str = "device:admin") -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, scope):
            raise HTTPException(403, f"This device is not permitted to use {scope}")
        return device_id

    def require_fresh_owner_verification(device_id: str) -> None:
        if runtime.get("pwa_sessions") is None:
            return
        context = current_trusted_request()
        ttl = int(getattr(runtime.get("agent_executor"), "reauth_ttl_seconds", 300) or 300)
        ttl = max(30, min(ttl, 900))
        stamp = getattr(context, "reauthenticated_at", None) if context is not None else None
        try:
            age = time.time() - float(stamp)
        except (TypeError, ValueError):
            age = ttl + 1
        if context is None or context.device_id != device_id or age < 0 or age > ttl:
            raise HTTPException(
                401,
                {
                    "code": "reauthentication_required",
                    "message": "Fresh owner verification is required for this portable-intelligence action.",
                },
            )

    def portable():
        service = runtime.get("portable_intelligence")
        if service is None:
            raise HTTPException(503, "portable intelligence runtime unavailable")
        return service

    def contributions():
        service = runtime.get("contribution_settings")
        if service is None:
            raise HTTPException(503, "shared-learning settings unavailable")
        return service

    def specialists():
        service = runtime.get("specialist_registry")
        if service is None:
            raise HTTPException(503, "specialist registry unavailable")
        return service

    def emit(name: str, **payload) -> None:
        if events is not None:
            events.emit(name, **payload)

    def core_version() -> str:
        return str(
            runtime.get("running_git_revision")
            or os.environ.get("VISHNU_TRUSTED_RELEASE_REVISION")
            or "unversioned"
        )

    @router.get("/summary")
    def summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        service = portable()
        try:
            value = service.status()
        except Exception as exc:
            raise HTTPException(503, f"portable intelligence status unavailable: {type(exc).__name__}") from exc
        coordinator = runtime.get("training_coordinator")
        backends = sorted(getattr(coordinator, "backends", {}).keys()) if coordinator is not None else []
        value["contributions"] = contributions().snapshot().public()
        value["training_backends"] = backends
        value["remote_gpu_backend_configured"] = any(item.startswith("remote_gpu:") for item in backends)
        value["remote_gpu_credentials_exposed"] = False
        value["restore_mutation_authority"] = "existing encrypted BackupService/disaster recovery"
        return value

    @router.post("/publish")
    def publish(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            package = portable().publish_current_restore_package(core_version=core_version())
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.portable_intelligence.published", device_id=device_id, package_id=package.package_id)
        return {"ok": True, "package": package.public()}

    @router.post("/offline-pack")
    def prepare_offline_pack(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            result = portable().prepare_offline_pack()
        except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.portable_intelligence.offline_pack_prepared", device_id=device_id, pack_id=result.manifest.pack_id)
        return {"ok": True, "offline_pack": result.public()}

    @router.post("/activation/preflight")
    def activation_preflight(
        body: ActivationBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        try:
            preflight = portable().activation_preflight(online=body.online)
        except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"preflight": preflight.public()}

    @router.post("/activation")
    def activate(
        body: ActivationBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            receipt = portable().activate(online=body.online)
        except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.portable_intelligence.activated", device_id=device_id, runtime_id=receipt.runtime_id)
        return {"ok": True, "receipt": receipt.public()}

    @router.get("/contributions")
    def contribution_settings(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        snapshot = contributions().snapshot()
        return {
            "settings": snapshot.public(),
            "private_by_default": True,
            "training_contribution_requires_existing_governance": True,
            "documents_default_off": True,
        }

    @router.patch("/contributions")
    def update_contribution_settings(
        body: ContributionSettingsBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        values = body.model_dump(exclude_unset=True)
        if "mode" in values:
            values["mode"] = ContributionMode(values["mode"])
        try:
            snapshot = contributions().update(**values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        emit("owner.learning.contribution_preferences_updated", device_id=device_id, **snapshot.public())
        return {"ok": True, "settings": snapshot.public()}

    @router.get("/specialists")
    def specialist_bindings(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        service = specialists()
        return {
            "active": [item.public() for item in service.active_bindings()],
            "history": [item.public() for item in service.history(limit=100)],
            "promotion_authority": False,
        }

    @router.post("/specialists")
    def bind_specialist(
        body: SpecialistBindingBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            binding = specialists().bind(
                owner_id="owner",
                specialist_role=body.specialist_role,
                task_domain=body.task_domain,
                model_id=body.model_id,
            )
        except KeyError as exc:
            raise HTTPException(404, "trained model not found") from exc
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.specialist_model.bound", device_id=device_id, binding_id=binding.binding_id)
        return {"ok": True, "binding": binding.public()}

    @router.delete("/specialists")
    def unbind_specialist(
        body: SpecialistUnbindBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        changed = specialists().unbind(
            owner_id="owner",
            specialist_role=body.specialist_role,
            task_domain=body.task_domain,
        )
        emit(
            "owner.specialist_model.unbound",
            device_id=device_id,
            specialist_role=body.specialist_role,
            task_domain=body.task_domain,
            changed=changed,
        )
        return {"ok": True, "changed": changed}

    return router
