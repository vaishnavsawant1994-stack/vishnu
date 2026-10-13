from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from future_intelligence.capability_forge.models import GapStatus
from future_intelligence.capability_forge.package import PackagedCapability
from integrations.discovery.generated_catalog import generated_capabilities
from integrations.discovery.generated_runtime import load_generated_manifest, resolve_generated_package
from security.request_context import current_trusted_request


class ForgeProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["conversation", "project", "workflow", "proactive", "system"] = "conversation"
    capability_name: str = Field(min_length=1, max_length=240)
    requested_outcome: str = Field(min_length=1, max_length=1000)
    required_operations: list[str] = Field(default_factory=list, max_length=50)
    network_hosts: list[str] = Field(default_factory=list, max_length=50)
    filesystem_read: list[str] = Field(default_factory=list, max_length=50)
    filesystem_write: list[str] = Field(default_factory=list, max_length=50)
    secret_names: list[str] = Field(default_factory=list, max_length=50)
    connector_ids: list[str] = Field(default_factory=list, max_length=50)
    side_effects: list[str] = Field(default_factory=list, max_length=50)
    ui_required: bool = False
    background_allowed: bool = False
    external_api: bool = False
    mcp: bool = False
    requires_core_change: bool = False
    preferred_route: str | None = Field(default=None, max_length=80)
    requirements: dict[str, Any] = Field(default_factory=dict)


class ForgeWorkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_id: str = Field(min_length=1, max_length=160)
    plan_id: str = Field(min_length=1, max_length=160)
    repository: str = Field(min_length=1, max_length=300)
    allowed_paths: list[str] = Field(min_length=1, max_length=30)
    project_id: str | None = Field(default=None, max_length=160)
    priority: int = Field(default=50, ge=0, le=100)
    max_runtime_seconds: int = Field(default=1800, ge=60, le=14400)
    max_attempts: int = Field(default=3, ge=1, le=5)
    prohibited_paths: list[str] = Field(default_factory=list, max_length=30)


class ForgeBuildBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="1.0.0", min_length=5, max_length=80)
    source_root: str = Field(min_length=1, max_length=500)


class ForgeActivationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    build_id: str = Field(min_length=1, max_length=240)
    ticket_id: str | None = Field(default=None, max_length=240)


class ForgeTicketBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=240)


class ForgeRollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: str = Field(min_length=1, max_length=240)
    target_activation_id: str = Field(min_length=1, max_length=400)


def capability_forge_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/owner/forge", tags=["capability-forge"])
    registry = runtime["device_registry"]
    events = runtime.get("events")

    def authenticate(device_id: str | None, token: str | None) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "device:admin"):
            raise HTTPException(403, "This device is not permitted to manage Capability Forge")
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
            raise HTTPException(401, {
                "code": "reauthentication_required",
                "message": "Fresh owner verification is required for Capability Forge mutations.",
            })

    def forge():
        value = runtime.get("capability_forge")
        if value is None:
            raise HTTPException(503, "Capability Forge intelligence is unavailable on this host")
        return value

    def store():
        value = runtime.get("capability_forge_store")
        if value is None:
            raise HTTPException(503, "Capability Forge store is unavailable on this host")
        return value

    def lifecycle():
        value = runtime.get("capability_forge_lifecycle")
        if value is None:
            raise HTTPException(503, "Capability Forge lifecycle is unavailable on this host")
        return value

    def work_bridge():
        value = runtime.get("capability_forge_work")
        if value is None:
            raise HTTPException(503, "Capability Forge Canonical Work bridge is unavailable on this host")
        return value

    def activation():
        value = runtime.get("capability_forge_activation")
        if value is None:
            raise HTTPException(503, "Capability Forge activation is unavailable on this host")
        return value

    def build_service():
        factory = runtime.get("capability_forge_build_factory")
        value = factory() if callable(factory) else None
        if value is None:
            raise HTTPException(503, "Capability Forge engineering build service is unavailable on this host")
        return value

    def emit(name: str, **payload: Any) -> None:
        if events is not None:
            events.emit(name, **payload)

    def latest_build_for_work(work_order_id: str) -> dict[str, Any] | None:
        life = lifecycle()
        with life._con() as con:
            row = con.execute(
                "SELECT id FROM forge_builds WHERE work_order_id=? ORDER BY updated_at DESC,id DESC LIMIT 1",
                (str(work_order_id),),
            ).fetchone()
        return life.get_build(str(row["id"])) if row else None

    def packaged_from_build(build_id: str) -> PackagedCapability:
        build = lifecycle().get_build(str(build_id))
        if not build or build.get("status") != "packaged":
            raise HTTPException(409, "Forge build is not a packaged qualified candidate")
        payload = dict(build.get("payload") or {})
        package_ref = str(payload.get("package_ref") or "")
        expected_digest = str(payload.get("manifest_digest") or "")
        if not package_ref or not expected_digest:
            raise HTTPException(409, "Forge packaged build is missing immutable package lineage")
        data_root = Path(runtime["settings"].data_dir).resolve()
        try:
            package_path = resolve_generated_package(data_root, package_ref)
            manifest = load_generated_manifest(package_path, expected_digest=expected_digest)
        except Exception as exc:
            raise HTTPException(409, f"Forge package validation failed: {type(exc).__name__}") from exc
        digest = hashlib.sha256((package_path / "manifest.json").read_bytes()).hexdigest()
        if digest != expected_digest:
            raise HTTPException(409, "Forge package digest changed after qualification")
        return PackagedCapability(
            capability_id=str(manifest["id"]),
            version=str(manifest["version"]),
            package_path=package_path,
            manifest_path=package_path / "manifest.json",
            manifest=manifest,
            manifest_digest=digest,
            build_id=str(build["id"]),
        )

    @router.get("/summary")
    def summary(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        gaps = store().list_gaps(limit=100)
        catalog = runtime.get("capability_catalog")
        generated = generated_capabilities(catalog) if catalog is not None else []
        return {
            "available": True,
            "gaps": len(gaps),
            "open_gaps": sum(1 for item in gaps if item.status not in {GapStatus.REJECTED, GapStatus.ACTIVE}),
            "generated_capabilities": len(generated),
            "active_generated_capabilities": sum(1 for item in generated if item.get("state") == "active"),
            "engineering_available": build_service is not None and callable(runtime.get("capability_forge_build_factory")),
            "activation_available": runtime.get("capability_forge_activation") is not None,
            "authorities": {
                "queue_draft_work": False,
                "self_approve_activation": False,
                "remote_push": False,
                "merge": False,
                "deploy": False,
                "production_activation": False,
            },
        }

    @router.get("/gaps")
    def gaps(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {"items": [item.to_dict() for item in store().list_gaps(limit=200)]}

    @router.get("/gaps/{gap_id}")
    def gap_detail(gap_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        item = store().get_gap(str(gap_id))
        if item is None:
            raise HTTPException(404, "Capability gap not found")
        return item.to_dict()

    @router.post("/proposals")
    def propose(body: ForgeProposalBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        payload = {
            "capability_gap": True,
            "capability_name": body.capability_name,
            "requested_outcome": body.requested_outcome,
            "required_operations": body.required_operations,
            "network_hosts": body.network_hosts,
            "filesystem_read": body.filesystem_read,
            "filesystem_write": body.filesystem_write,
            "secret_names": body.secret_names,
            "connector_ids": body.connector_ids,
            "side_effects": body.side_effects,
            "ui_required": body.ui_required,
            "background_allowed": body.background_allowed,
            "external_api": body.external_api,
            "mcp": body.mcp,
            "requires_core_change": body.requires_core_change,
            "preferred_route": body.preferred_route,
        }
        result = forge().propose(body.source, payload, requirements=body.requirements)
        if result is None:
            raise HTTPException(422, "Request did not produce a valid capability-gap signal")
        gap, spec, plan = result
        emit("owner.capability_forge.proposal_created", device_id=device_id, gap_id=gap.id, spec_id=spec.id, plan_id=plan.id)
        return {"gap": gap.to_dict(), "spec": spec.to_dict(), "plan": plan.to_dict()}

    @router.post("/work")
    def create_draft_work(body: ForgeWorkBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        spec = store().get_spec(body.spec_id)
        plan = store().get_plan(body.plan_id)
        if spec is None or plan is None:
            raise HTTPException(404, "Forge specification or plan not found")
        try:
            projection = work_bridge().prepare_draft_work(
                spec,
                plan,
                repository=body.repository,
                allowed_paths=body.allowed_paths,
                project_id=body.project_id,
                priority=body.priority,
                max_runtime_seconds=body.max_runtime_seconds,
                max_attempts=body.max_attempts,
                prohibited_paths=body.prohibited_paths,
                metadata={"owner_device_id": device_id},
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.capability_forge.draft_work_created", device_id=device_id, work_order_id=projection.work_order.id)
        return {
            "goal": projection.goal.to_dict(),
            "work_plan": projection.work_plan.to_dict(),
            "work_order": projection.work_order.to_dict(),
            "queued": False,
            "execution_started": False,
        }

    def run_build(work_order_id: str, version: str, source_root: str, device_id: str) -> None:
        work = work_bridge().work_store.get_order(str(work_order_id))
        if work is None:
            emit("owner.capability_forge.build_failed", work_order_id=work_order_id, device_id=device_id, error_type="KeyError")
            return
        lineage = dict(work.resource_scope.metadata or {})
        spec = store().get_spec(str(lineage.get("forge_spec_id") or ""))
        plan = store().get_plan(str(lineage.get("forge_plan_id") or ""))
        if spec is None or plan is None:
            emit("owner.capability_forge.build_failed", work_order_id=work_order_id, device_id=device_id, error_type="LineageError")
            return
        try:
            candidate, package = build_service().execute_and_package(
                spec,
                plan,
                work_order_id=str(work_order_id),
                runtime_epoch=int(runtime.get("code_worker_epoch", 0)),
                source_root=source_root,
                version=version,
            )
            emit(
                "owner.capability_forge.build_finished",
                work_order_id=str(work_order_id),
                device_id=device_id,
                status=candidate.status,
                qualified=candidate.qualified,
                build_id=package.build_id if package else f"build:{candidate.attempt_id}",
                capability_id=package.capability_id if package else None,
                version=package.version if package else None,
            )
        except Exception as exc:
            emit("owner.capability_forge.build_failed", work_order_id=str(work_order_id), device_id=device_id, error_type=type(exc).__name__)

    @router.post("/work/{work_order_id}/build")
    def build_candidate(work_order_id: str, body: ForgeBuildBody, background: BackgroundTasks, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        eng = runtime.get("engineering")
        if eng is None:
            raise HTTPException(503, "governed engineering runtime is unavailable on this host")
        if not eng.owner_policy.snapshot().allows_autonomous_execution():
            raise HTTPException(409, "Engineering Autonomy must be Auto-Fix or Review Candidate before Forge can build")
        order = work_bridge().work_store.get_order(str(work_order_id))
        if order is None:
            raise HTTPException(404, "Canonical WorkOrder not found")
        if order.status.value not in {"queued", "retrying"}:
            raise HTTPException(409, "Existing Canonical Work governance must queue the Forge WorkOrder before build execution")
        background.add_task(run_build, str(work_order_id), body.version, body.source_root, device_id)
        emit("owner.capability_forge.build_requested", device_id=device_id, work_order_id=str(work_order_id), version=body.version)
        return {"ok": True, "scheduled": True, "work_order_id": str(work_order_id), "activation": False}

    @router.get("/work/{work_order_id}/build")
    def build_status(work_order_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        build = latest_build_for_work(str(work_order_id))
        if build is None:
            return {"work_order_id": str(work_order_id), "build": None}
        return {"work_order_id": str(work_order_id), "build": build}

    @router.get("/capabilities")
    def capabilities(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        catalog = runtime.get("capability_catalog")
        items = generated_capabilities(catalog) if catalog is not None else []
        return {
            "items": [
                {**item, "metrics": lifecycle().metrics(str(item.get("id") or ""))}
                for item in items
            ]
        }

    @router.post("/activation/request")
    def request_activation(body: ForgeActivationBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        package = packaged_from_build(body.build_id)
        try:
            decision = activation().request_activation(package, owner_id="owner", device_id=device_id)
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.capability_forge.activation_requested", device_id=device_id, capability_id=package.capability_id, version=package.version, approval_id=decision.ticket_id)
        return {"approval_required": True, **decision.__dict__}

    @router.post("/activation/commit")
    def commit_activation(body: ForgeActivationBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        if not body.ticket_id:
            raise HTTPException(422, "ticket_id is required after owner approval")
        package = packaged_from_build(body.build_id)
        try:
            return activation().activate(package, ticket_id=body.ticket_id, owner_id="owner", device_id=device_id)
        except (ValueError, PermissionError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/capabilities/{capability_id}/disable/request")
    def request_disable(capability_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            ticket_id = activation().request_disable(capability_id, owner_id="owner", device_id=device_id)
        except (ValueError, PermissionError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"approval_required": True, "ticket_id": ticket_id, "capability_id": capability_id}

    @router.post("/capabilities/{capability_id}/disable/commit")
    def commit_disable(capability_id: str, body: ForgeTicketBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            return activation().disable(capability_id, ticket_id=body.ticket_id, owner_id="owner", device_id=device_id)
        except (ValueError, PermissionError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/capabilities/{capability_id}/rollback/request")
    def request_rollback(capability_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            ticket_id, target = activation().request_rollback(capability_id, owner_id="owner", device_id=device_id)
        except (ValueError, PermissionError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"approval_required": True, "ticket_id": ticket_id, "target_activation_id": target["id"], "target_version": target["version"]}

    @router.post("/capabilities/{capability_id}/rollback/commit")
    def commit_rollback(capability_id: str, body: ForgeRollbackBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            return activation().rollback(
                capability_id,
                ticket_id=body.ticket_id,
                target_activation_id=body.target_activation_id,
                owner_id="owner",
                device_id=device_id,
            )
        except (ValueError, PermissionError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
