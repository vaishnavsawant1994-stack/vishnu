from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from data_plane.runtime import ensure_data_plane_tools
from devices.gateway import DeviceCommand


class ActionRequest(BaseModel):
    tool: str
    parameters: dict = Field(default_factory=dict)


class DeviceActionRequest(BaseModel):
    action: str
    parameters: dict = Field(default_factory=dict)
    timeout: float = 15


class TransferAckRequest(BaseModel):
    sequence: int = Field(ge=0)


def dashboard_router(runtime, auth_device):
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])
    data_plane = ensure_data_plane_tools(runtime)
    trust_runtime = None
    if all(
        runtime.get(key) is not None
        for key in ("settings", "device_registry", "owner_access", "tools")
    ):
        from trust_continuity.integration import attach_trust_continuity_runtime

        trust_runtime = attach_trust_continuity_runtime(runtime)

    def auth(authorization, device_id, scope="ai:chat"):
        return auth_device(authorization, device_id, scope)

    def data_plane_projection():
        if data_plane is None:
            return {
                "available": False,
                "reason": "canonical data directory unavailable",
            }
        return {"available": True, **data_plane.settings()}

    def require_data_plane():
        if data_plane is None:
            raise HTTPException(
                503,
                "Vishnu data plane is unavailable in this reduced runtime",
            )
        return data_plane

    def require_transport():
        transport = runtime.get("data_plane_byte_transport")
        if transport is None:
            raise HTTPException(503, "Vishnu secure byte transport is unavailable")
        return transport

    def owned_session(session_id, device_id):
        transport = require_transport()
        try:
            status = transport.status(session_id)
        except KeyError as exc:
            raise HTTPException(404, "secure transfer session unavailable") from exc
        if status["requester_device_id"] != device_id:
            raise HTTPException(
                403,
                "secure transfer session belongs to another device",
            )
        return transport, status

    @router.get("/status")
    def status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        voice_thread = getattr(runtime.get("voice"), "thread", None)
        return {
            "automations": len(runtime["automations"].list()),
            "devices": len(runtime["device_registry"].list()),
            "online_devices": runtime["device_gateway"].online(),
            "integrations": (
                runtime["integrations"].list() if runtime.get("integrations") else []
            ),
            "memory_nodes": len(runtime["second_brain"].graph().get("nodes", [])),
            "voice_state": (
                "active" if voice_thread and voice_thread.is_alive() else "idle"
            ),
            "security": {
                "vault": "keychain-backed" if runtime.get("vault") else "unavailable",
                "autonomy": runtime["tools"].settings.autonomy_mode,
            },
            "data_plane": data_plane_projection(),
            "trust_continuity": (
                trust_runtime.status()
                if trust_runtime is not None
                else {"available": False}
            ),
        }

    @router.get("/devices")
    def devices(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return runtime["device_registry"].list()

    @router.get("/automations")
    def automations(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "workflow:read")
        return runtime["automations"].list()

    @router.get("/memory")
    def memory(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "memory:sensitive")
        return runtime["second_brain"].graph()

    @router.get("/data-plane")
    def data_plane_status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "data:read")
        return require_data_plane().diagnostics()

    @router.get("/data-plane/item/{global_id:path}")
    def data_plane_item(
        global_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "data:read")
        try:
            return require_data_plane().item(global_id)
        except KeyError as exc:
            raise HTTPException(404, "data item unavailable") from exc

    @router.get("/data-plane/transfer/{session_id}/next")
    async def transfer_next(
        session_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "data:read")
        transport, _ = owned_session(session_id, device_id)
        try:
            return await transport.request_remote_chunk(session_id)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (RuntimeError, ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/data-plane/transfer/{session_id}/ack")
    def transfer_ack(
        session_id: str,
        body: TransferAckRequest,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "data:read")
        transport, _ = owned_session(session_id, device_id)
        try:
            return transport.acknowledge_chunk(session_id, body.sequence)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (RuntimeError, ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/tool")
    def tool(
        req: ActionRequest,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "ai:chat")
        raise HTTPException(
            409,
            "Direct dashboard tool execution is disabled; use the canonical governed Vishnu runtime",
        )

    @router.post("/device/{device_id}/command")
    async def device_command(
        device_id: str,
        req: DeviceActionRequest,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        action = str(req.action or "").strip()
        if action not in {"device_info", "battery", "voice_status"}:
            raise HTTPException(
                409,
                "Consequential device commands require canonical governed execution",
            )
        command = DeviceCommand(
            action,
            dict(req.parameters or {}),
            str(uuid.uuid4()),
        )
        try:
            return await runtime["device_gateway"].request(
                device_id,
                command,
                max(1, min(req.timeout, 60)),
            )
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc

    if trust_runtime is not None:
        from server.trust_continuity_api import trust_continuity_router

        trust_routes = trust_continuity_router(trust_runtime, auth_device)
        router.routes.extend(trust_routes.routes)

    return router
