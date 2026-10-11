from __future__ import annotations

import json
import os
import time
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from future_intelligence.engineering.verification import observation_to_dict
from future_intelligence.engineering.workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    GitHubWorkflowEvidenceConfig,
    PhysicalDeviceWorkflowRun,
    WorkflowEvidenceError,
)
from future_intelligence.engineering.workflow_orchestration import (
    GitHubPhysicalDeviceOrchestrationConfig,
    GitHubPhysicalDeviceWorkflowOrchestrator,
)
from security.request_context import current_trusted_request


class EngineeringPolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["off", "analyze", "workspace", "auto_fix", "review_candidate"] | None = None
    max_files: int | None = Field(default=None, ge=1, le=200)
    max_file_bytes: int | None = Field(default=None, ge=1_000, le=5_000_000)
    max_total_bytes: int | None = Field(default=None, ge=1_000, le=20_000_000)
    max_repair_cycles: int | None = Field(default=None, ge=0, le=10)
    browser_depth: Literal["critical", "full", "release"] | None = None
    visual_level: Literal["off", "diff", "semantic"] | None = None
    preview_enabled: bool | None = None
    security_level: Literal["ordinary", "sensitive", "authority"] | None = None
    evidence_retention_days: int | None = Field(default=None, ge=1, le=3650)
    max_model_cost_per_work: float | None = Field(default=None, gt=0, le=100_000)
    physical_device_required: bool | None = None
    physical_device_auto_dispatch: bool | None = None
    performance_required: bool | None = None
    localization_required: bool | None = None
    three_d_required: bool | None = None


class PhysicalDeviceRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["ios", "android"]
    run_id: int = Field(gt=0)


class PhysicalDeviceEvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runs: list[PhysicalDeviceRunBody] = Field(min_length=1, max_length=2)


def owner_engineering_router(runtime) -> APIRouter:
    """Trusted-owner Engineering Autonomy controls and read-only work visibility.

    This surface may configure local engineering limits, request execution of an
    already-created Canonical WorkOrder, independently verify supplied GitHub
    physical-device workflow run IDs, and—when explicitly enabled by owner policy
    and a separate dispatch credential—start only the allowlisted physical-device
    workflows for an exact candidate that is already published remotely. It cannot
    create repository scope, claim a qualification gate passed, push, merge,
    deploy, roll back, approve security authority, or activate a Body revision.
    """

    router = APIRouter(prefix="/iphone/api/owner/engineering", tags=["owner-engineering"])
    registry = runtime["device_registry"]
    events = runtime.get("events")

    def authenticate(device_id: str | None, token: str | None) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "device:admin"):
            raise HTTPException(403, "This device is not permitted to manage Engineering Autonomy")
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
                "message": "Fresh owner verification is required to change Engineering Autonomy or submit qualification evidence.",
            })

    def engineering():
        value = runtime.get("engineering")
        if value is None:
            raise HTTPException(503, "governed engineering runtime is unavailable on this host")
        return value

    def executor():
        value = runtime.get("engineering_executor")
        if value is None:
            raise HTTPException(503, "governed engineering executor is unavailable on this host")
        return value

    def finalizer():
        value = runtime.get("engineering_finalizer")
        if value is None:
            raise HTTPException(503, "engineering final qualification is unavailable on this host")
        if not hasattr(value, "verify_and_record_physical_device_evidence"):
            raise HTTPException(503, "trusted physical-device evidence verification is unavailable on this host")
        if getattr(value, "physical_device_verifier", None) is None:
            repository = str(engineering().repository_provider.repository or "").strip().strip("/")
            token = str(
                os.environ.get("VISHNU_ENGINEERING_GITHUB_EVIDENCE_TOKEN")
                or os.environ.get("VISHNU_ENGINEERING_GITHUB_TOKEN")
                or ""
            ).strip()
            try:
                value.physical_device_verifier = GitHubPhysicalDeviceEvidenceVerifier(
                    GitHubWorkflowEvidenceConfig(repository=repository, token=token)
                )
            except ValueError as exc:
                raise HTTPException(503, "trusted GitHub physical-device evidence verifier is not configured") from exc
        return value

    def physical_orchestrator() -> GitHubPhysicalDeviceWorkflowOrchestrator:
        existing = runtime.get("engineering_physical_device_orchestrator")
        if existing is not None:
            return existing
        repository = str(engineering().repository_provider.repository or "").strip().strip("/")
        token = str(os.environ.get("VISHNU_ENGINEERING_GITHUB_DISPATCH_TOKEN") or "").strip()
        try:
            value = GitHubPhysicalDeviceWorkflowOrchestrator(
                GitHubPhysicalDeviceOrchestrationConfig(repository=repository, token=token)
            )
        except ValueError as exc:
            raise HTTPException(503, "trusted GitHub physical-device workflow dispatch is not configured") from exc
        runtime["engineering_physical_device_orchestrator"] = value
        return value

    def dispatch_and_record_physical_device_evidence(work_order_id: str, attempt_id: str):
        qualified_finalizer = finalizer()
        if not hasattr(qualified_finalizer, "_workspace_and_spec"):
            raise RuntimeError("engineering finalizer cannot resolve the exact candidate workspace")
        _attempt, workspace, spec, _session, candidate_revision, _changed = qualified_finalizer._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        metadata = dict(spec.metadata or {})
        if not (spec.ui_required and bool(metadata.get("physical_device_required", False))):
            raise PermissionError("EngineeringSpec does not require physical-device qualification")
        runs = physical_orchestrator().dispatch_required(
            spec=spec,
            candidate_revision=candidate_revision,
            preferred_ref=str(workspace.branch_ref or ""),
        )
        observation = qualified_finalizer.verify_and_record_physical_device_evidence(
            str(work_order_id), str(attempt_id), runs=runs
        )
        return observation, runs

    def emit(name: str, **payload: Any) -> None:
        if events is not None:
            events.emit(name, **payload)

    @staticmethod
    def _final_status(work_events, attempt_id: str | None, attempt_metadata: dict[str, Any]) -> tuple[Any, Any]:
        qualification_status = attempt_metadata.get("qualification_status")
        review_decision = attempt_metadata.get("review_decision")
        for event in reversed(work_events):
            if attempt_id is not None and event.attempt_id != attempt_id:
                continue
            if event.event_type == "engineering.candidate.qualified":
                return "qualified", event.payload.get("review_decision", "approved")
            if event.event_type == "engineering.candidate.review_rejected":
                return "review_rejected", event.payload.get("review_decision", "rejected")
            if event.event_type == "engineering.final_qualification_pending":
                return "pending_external_qualification", event.payload.get("review_decision", "pending")
        return qualification_status, review_decision

    def recent_work(limit: int = 30) -> list[dict[str, Any]]:
        eng = engineering()
        rows = eng.work_store.connection.execute(
            """
            SELECT w.id AS workspace_id, w.work_order_id, w.attempt_id,
                   w.repository, w.base_revision, w.working_revision, w.branch_ref,
                   w.state AS workspace_state, w.updated_at,
                   o.status AS work_status, o.payload_json AS work_payload,
                   a.status AS attempt_status, a.worker_id, a.started_at, a.finished_at,
                   a.metadata_json AS attempt_metadata
            FROM work_workspaces AS w
            LEFT JOIN work_orders AS o ON o.id = w.work_order_id
            LEFT JOIN work_attempts AS a ON a.id = w.attempt_id
            ORDER BY w.updated_at DESC, w.id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        output = []
        event_cache: dict[str, list[Any]] = {}
        for row in rows:
            try:
                work_payload = json.loads(row["work_payload"] or "{}")
            except (TypeError, json.JSONDecodeError):
                work_payload = {}
            try:
                attempt_metadata = json.loads(row["attempt_metadata"] or "{}")
            except (TypeError, json.JSONDecodeError):
                attempt_metadata = {}
            work_order_id = str(row["work_order_id"])
            if work_order_id not in event_cache:
                event_cache[work_order_id] = eng.work_store.list_work_events(work_order_id)
            qualification_status, review_decision = _final_status(
                event_cache[work_order_id], row["attempt_id"], attempt_metadata
            )
            output.append({
                "workspace_id": str(row["workspace_id"]),
                "work_order_id": work_order_id,
                "attempt_id": row["attempt_id"],
                "title": str(work_payload.get("title") or row["work_order_id"]),
                "objective": str(work_payload.get("objective") or "")[:2000],
                "repository": str(row["repository"]),
                "base_revision": str(row["base_revision"]),
                "candidate_revision": row["working_revision"],
                "branch_ref": row["branch_ref"],
                "workspace_state": str(row["workspace_state"]),
                "work_status": row["work_status"],
                "attempt_status": row["attempt_status"],
                "worker_id": row["worker_id"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "updated_at": row["updated_at"],
                "qualification_status": qualification_status,
                "review_decision": review_decision,
                "repair_cycles": attempt_metadata.get("repair_cycles"),
                "regression_proof": attempt_metadata.get("regression_proof"),
            })
        return output

    @router.get("/summary")
    def summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        eng = engineering()
        policy = eng.owner_policy.snapshot()
        finalizer_value = runtime.get("engineering_finalizer")
        repository = str(eng.repository_provider.repository or "").strip().strip("/")
        verifier_available = bool(
            finalizer_value is not None
            and hasattr(finalizer_value, "verify_and_record_physical_device_evidence")
            and (
                getattr(finalizer_value, "physical_device_verifier", None) is not None
                or len(repository.split("/")) == 2
            )
        )
        auto_dispatch_available = bool(
            runtime.get("engineering_physical_device_orchestrator") is not None
            or str(os.environ.get("VISHNU_ENGINEERING_GITHUB_DISPATCH_TOKEN") or "").strip()
        )
        return {
            "available": True,
            "repository": eng.repository_provider.repository,
            "final_qualification_available": finalizer_value is not None,
            "trusted_physical_device_evidence": {
                "accepted_input": "github_workflow_run_ids_only",
                "verified_server_side": True,
                "candidate_revision_bound": True,
                "verifier_available": verifier_available,
                "auto_dispatch_available": auto_dispatch_available,
                "auto_dispatch_enabled": bool(policy.physical_device_auto_dispatch),
                "remote_source_mutation": False,
            },
            "policy": policy.public(),
            "recent_work": recent_work(),
            "authorities": {
                "remote_push": False,
                "merge": False,
                "deploy": False,
                "body_activation": False,
                "client_qualification_claim": False,
            },
        }

    @router.patch("/policy")
    def update_policy(
        body: EngineeringPolicyBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        values = body.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(422, "At least one Engineering Autonomy setting is required")
        try:
            policy = engineering().owner_policy.update(**values)
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit(
            "owner.engineering.policy_updated",
            device_id=device_id,
            mode=policy.mode.value,
            security_level=policy.security_level.value,
        )
        return {"ok": True, "policy": policy.public()}

    def run_engineering(work_order_id: str, device_id: str) -> None:
        try:
            result = executor().execute(
                str(work_order_id),
                worker_id="vishnu-software-engineer",
                runtime_epoch=int(runtime.get("code_worker_epoch", 0)),
                base_revision="HEAD",
            )
            policy = engineering().owner_policy.snapshot()
            if result.status == "verifying" and policy.physical_device_auto_dispatch:
                try:
                    observation, runs = dispatch_and_record_physical_device_evidence(
                        str(work_order_id), str(result.attempt_id)
                    )
                    emit(
                        "owner.engineering.physical_evidence_auto_dispatched",
                        device_id=device_id,
                        work_order_id=str(work_order_id),
                        attempt_id=str(result.attempt_id),
                        platforms=list(dict(observation.metadata or {}).get("verified_platforms") or ()),
                        workflow_run_ids=[item.run_id for item in runs],
                    )
                except Exception as exc:
                    # External device infrastructure is a qualification gate, not
                    # permission to invalidate an otherwise verified local candidate.
                    # Keep the candidate in VERIFYING and expose the exact failure.
                    emit(
                        "owner.engineering.physical_evidence_auto_dispatch_failed",
                        device_id=device_id,
                        work_order_id=str(work_order_id),
                        attempt_id=str(result.attempt_id),
                        error_type=type(exc).__name__,
                    )
            emit(
                "owner.engineering.execution_finished",
                device_id=device_id,
                work_order_id=work_order_id,
                status=result.status,
                candidate_revision=result.candidate_revision,
            )
        except Exception as exc:
            emit(
                "owner.engineering.execution_failed",
                device_id=device_id,
                work_order_id=work_order_id,
                error_type=type(exc).__name__,
            )

    @router.post("/work/{work_order_id}/execute")
    def execute_work(
        work_order_id: str,
        background: BackgroundTasks,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        eng = engineering()
        policy = eng.owner_policy.snapshot()
        if not policy.allows_autonomous_execution():
            raise HTTPException(409, "Engineering Autonomy must be Auto-Fix or Review Candidate to execute a WorkOrder")
        order = eng.work_store.get_order(str(work_order_id))
        if order is None:
            raise HTTPException(404, "Canonical WorkOrder not found")
        if not order.resource_scope.allowed_repositories or not order.resource_scope.allowed_paths:
            raise HTTPException(409, "Canonical WorkOrder does not have explicit repository and path scope")
        background.add_task(run_engineering, str(work_order_id), device_id)
        emit("owner.engineering.execution_requested", device_id=device_id, work_order_id=str(work_order_id))
        return {
            "ok": True,
            "scheduled": True,
            "work_order_id": str(work_order_id),
            "mode": policy.mode.value,
            "remote_push": False,
            "merge": False,
            "deploy": False,
            "body_activation": False,
        }

    @router.post("/work/{work_order_id}/attempt/{attempt_id}/physical-evidence")
    def submit_physical_device_evidence(
        work_order_id: str,
        attempt_id: str,
        body: PhysicalDeviceEvidenceBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        if len({item.platform for item in body.runs}) != len(body.runs):
            raise HTTPException(422, "Only one workflow run may be supplied for each physical-device platform")
        try:
            observation = finalizer().verify_and_record_physical_device_evidence(
                str(work_order_id),
                str(attempt_id),
                runs=tuple(
                    PhysicalDeviceWorkflowRun(platform=item.platform, run_id=item.run_id)
                    for item in body.runs
                ),
            )
        except KeyError as exc:
            raise HTTPException(404, "Engineering Work/Attempt not found") from exc
        except WorkflowEvidenceError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit(
            "owner.engineering.physical_evidence_verified",
            device_id=device_id,
            work_order_id=str(work_order_id),
            attempt_id=str(attempt_id),
            platforms=list(dict(observation.metadata or {}).get("verified_platforms") or ()),
        )
        return {
            "ok": True,
            "work_order_id": str(work_order_id),
            "attempt_id": str(attempt_id),
            "observation": observation_to_dict(observation),
            "client_qualification_claim": False,
            "verified_server_side": True,
        }

    @router.post("/work/{work_order_id}/attempt/{attempt_id}/physical-evidence/dispatch")
    def dispatch_physical_device_evidence(
        work_order_id: str,
        attempt_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            observation, runs = dispatch_and_record_physical_device_evidence(
                str(work_order_id), str(attempt_id)
            )
        except KeyError as exc:
            raise HTTPException(404, "Engineering Work/Attempt not found") from exc
        except WorkflowEvidenceError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit(
            "owner.engineering.physical_evidence_dispatched",
            device_id=device_id,
            work_order_id=str(work_order_id),
            attempt_id=str(attempt_id),
            platforms=list(dict(observation.metadata or {}).get("verified_platforms") or ()),
            workflow_run_ids=[item.run_id for item in runs],
        )
        return {
            "ok": True,
            "work_order_id": str(work_order_id),
            "attempt_id": str(attempt_id),
            "observation": observation_to_dict(observation),
            "workflow_runs": [item.to_dict() for item in runs],
            "client_qualification_claim": False,
            "verified_server_side": True,
            "remote_push": False,
            "merge": False,
            "deploy": False,
        }

    @router.get("/work/{work_order_id}")
    def work_detail(
        work_order_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        eng = engineering()
        order = eng.work_store.get_order(str(work_order_id))
        if order is None:
            raise HTTPException(404, "Canonical WorkOrder not found")
        attempts = [item.__dict__ | {"status": item.status.value, "metadata": dict(item.metadata)} for item in eng.work_store.list_attempts(order.id)]
        events_out = [
            {
                "id": item.id,
                "attempt_id": item.attempt_id,
                "event_type": item.event_type,
                "payload": dict(item.payload),
                "created_at": item.created_at,
            }
            for item in eng.work_store.list_work_events(order.id)
        ]
        workspaces = [item for item in recent_work(100) if item["work_order_id"] == order.id]
        return {
            "work_order": order.to_dict(),
            "attempts": attempts,
            "events": events_out,
            "workspaces": workspaces,
            "authorities": {
                "remote_push": False,
                "merge": False,
                "deploy": False,
                "body_activation": False,
                "client_qualification_claim": False,
            },
        }

    return router