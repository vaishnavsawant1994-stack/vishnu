from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field


class EmergencyBody(BaseModel):
    enabled: bool


class DeviceBody(BaseModel):
    device_id: str = Field(min_length=1, max_length=240)


class ProviderBody(BaseModel):
    connection_id: str = Field(min_length=1, max_length=240)


class MemoryImportBody(BaseModel):
    package: dict[str, Any]


def trust_continuity_router(
    trust_runtime,
    auth_device: Callable[..., str],
) -> APIRouter:
    """Owner/device-authenticated visibility and emergency controls."""

    router = APIRouter(
        prefix="/owner/trust",
        tags=["owner-trust", "continuity", "production-readiness"],
    )

    def auth(
        authorization: str | None,
        device_id: str | None,
        scope: str,
    ) -> str:
        try:
            return auth_device(authorization, device_id, scope)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(401, "Device authentication required") from exc

    @router.get("/status")
    def status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return trust_runtime.status()

    @router.get("/readiness")
    def readiness(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "qualification:read")
        return trust_runtime.readiness.readiness().as_dict()

    @router.get("/l4")
    def l4_status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "qualification:read")
        return trust_runtime.l4.platform_status()

    @router.get("/audit")
    def audit(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return {"entries": trust_runtime.store.audit_entries(limit=limit)}

    @router.get("/continuity")
    def continuity_tasks(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        rows = trust_runtime.store.list(
            "continuity_task",
            device_id=device_id,
            limit=limit,
        )
        return {"tasks": rows}

    @router.get("/work")
    def work_jobs(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "workflow:read")
        return {"jobs": trust_runtime.store.list("work_v2", limit=limit)}

    @router.get("/memory/timeline")
    def memory_timeline(
        project_id: str | None = Query(default=None, max_length=240),
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "memory:read")
        return {
            "facts": trust_runtime.memory.timeline(
                owner_id="owner",
                project_id=project_id,
                limit=limit,
            )
        }

    @router.get("/memory/export")
    def memory_export(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "memory:read")
        return trust_runtime.memory.export_owner("owner")

    @router.post("/memory/import")
    def memory_import(
        body: MemoryImportBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "memory:write")
        return trust_runtime.memory.import_owner(
            owner_id="owner",
            package=body.package,
        )

    @router.get("/evaluation")
    def evaluation(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "qualification:read")
        return {
            "scorecards": trust_runtime.store.list(
                "evaluation_scorecard",
                limit=limit,
            )
        }

    @router.get("/center")
    def center(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        return trust_runtime.trust_center.snapshot()

    @router.post("/center/stop-sensing")
    def stop_sensing(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:admin")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        trust_runtime.trust_center.stop_sensing(actor=device_id)
        return {"stopped": "sensing"}

    @router.post("/center/stop-actions")
    def stop_actions(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:admin")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        trust_runtime.trust_center.stop_actions(actor=device_id)
        return {"stopped": "actions"}

    @router.post("/center/revoke-device")
    def revoke_device(
        body: DeviceBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:admin")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        trust_runtime.trust_center.revoke_device(body.device_id, actor=device_id)
        return {"revoked": body.device_id}

    @router.post("/center/disconnect-provider")
    def disconnect_provider(
        body: ProviderBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:admin")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        trust_runtime.trust_center.disconnect_provider(
            body.connection_id,
            actor=device_id,
        )
        return {"disconnected": body.connection_id}

    @router.post("/center/emergency-stop")
    def emergency_stop(
        body: EmergencyBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:admin")
        if trust_runtime.trust_center is None:
            raise HTTPException(503, "Trust Center mutation authorities are unavailable")
        trust_runtime.trust_center.emergency_stop(body.enabled, actor=device_id)
        return {"enabled": body.enabled}

    return router
