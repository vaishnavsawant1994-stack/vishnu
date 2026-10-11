from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from future_intelligence.engineering.canary import CanaryMetrics
from future_intelligence.release_control.contracts import ReleaseRiskClass
from future_intelligence.release_control.policy import ReleaseAutonomyMode
from security.request_context import current_trusted_request


class ReleasePolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["off", "preview_only", "approval_required", "auto_low_risk"] | None = None
    allow_production: bool | None = None
    require_preview: bool | None = None
    require_exact_revision_evidence: bool | None = None
    require_production_smoke: bool | None = None
    require_canary: bool | None = None
    automatic_risk_ceiling: Literal["low", "medium", "high", "critical"] | None = None
    canary_min_requests: int | None = Field(default=None, ge=1, le=100_000)
    canary_max_error_rate_regression: float | None = Field(default=None, ge=0, le=1)
    canary_max_latency_ratio: float | None = Field(default=None, ge=1, le=100)
    allow_automatic_rollback: bool | None = None
    owner_approval_for_sensitive_surfaces: bool | None = None
    max_monitoring_observations: int | None = Field(default=None, ge=1, le=100_000)


class CanaryMetricsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_count: int = Field(ge=0, le=100_000_000)
    error_rate: float = Field(ge=0, le=1)
    p95_latency_ms: float = Field(ge=0, le=3_600_000)


class CanaryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: CanaryMetricsBody
    candidate: CanaryMetricsBody
    additional_checks: dict[str, bool] = Field(default_factory=dict)


class RegressionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: str = Field(min_length=1, max_length=4000)
    evidence: list[str] = Field(default_factory=list, max_length=50)
    severity: Literal["info", "warning", "high", "critical"] = "warning"


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True]


class CancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


def owner_release_router(runtime) -> APIRouter:
    """Trusted-owner controls for the separate release authority domain.

    Release plans cannot be created here from arbitrary SHA/repository input.
    They originate only from a trusted EngineeringCandidateFinalizer handoff.
    This surface configures policy and acts on those already-bound plans.
    """

    router = APIRouter(prefix="/iphone/api/owner/release", tags=["owner-release"])
    registry = runtime["device_registry"]
    events = runtime.get("events")

    def authenticate(device_id: str | None, token: str | None) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "device:admin"):
            raise HTTPException(403, "This device is not permitted to manage releases")
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
                "message": "Fresh owner verification is required for release authority changes or production actions.",
            })

    def release_runtime():
        value = runtime.get("release_control")
        if value is None:
            raise HTTPException(503, "governed release control is unavailable on this host")
        return value

    def emit(name: str, **payload: Any) -> None:
        if events is not None:
            events.emit(name, **payload)

    def plan_and_provider(release_id: str):
        control = release_runtime()
        try:
            plan = control.controller.require(release_id)
            provider = control.provider(plan.provider)
        except Exception as exc:
            if "unknown release" in str(exc):
                raise HTTPException(404, "Release not found") from exc
            raise HTTPException(409, str(exc)) from exc
        return control, plan, provider

    @router.get("/summary")
    def summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        control = release_runtime()
        payload = control.summary()
        policy = control.policy()
        return {
            "available": True,
            **payload,
            "active_release_ids": list(getattr(runtime.get("release_automation"), "active_release_ids", lambda: ())()),
            "authorities": {
                "release_plan_creation_from_api": False,
                "preview": bool(control.providers) and policy.mode is not ReleaseAutonomyMode.OFF,
                "production_promotion": bool(control.providers) and policy.allow_production,
                "automatic_production": policy.mode is ReleaseAutonomyMode.AUTO_LOW_RISK,
                "automatic_rollback": False,
                "rollback_execution": bool(control.providers) and policy.allow_automatic_rollback,
                "body_activation": False,
            },
        }

    @router.get("/{release_id}")
    def detail(
        release_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        try:
            plan = release_runtime().controller.require(release_id)
        except Exception as exc:
            raise HTTPException(404, "Release not found") from exc
        return plan.to_dict()

    @router.patch("/policy")
    def update_policy(
        body: ReleasePolicyBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        values = body.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(422, "At least one release setting is required")
        try:
            policy = release_runtime().update_policy(**values)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        emit("owner.release.policy_updated", device_id=device_id, mode=policy.mode.value)
        return {"ok": True, "policy": policy.to_dict()}

    @router.post("/{release_id}/approve")
    def approve(
        release_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            plan = release_runtime().controller.approve(release_id, owner_identity=f"device:{device_id}")
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.approved", device_id=device_id, release_id=release_id, candidate_revision=plan.candidate_revision)
        return {"ok": True, "release": plan.to_dict()}

    @router.post("/{release_id}/preview")
    def preview(
        release_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        control, plan, provider = plan_and_provider(release_id)
        control.controller.policy = control.policy()
        try:
            result = control.controller.create_and_qualify_preview(release_id, provider=provider)
        except Exception as exc:
            emit("owner.release.preview_failed", device_id=device_id, release_id=release_id, error_type=type(exc).__name__)
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.preview_qualified", device_id=device_id, release_id=release_id, status=result.status.value)
        return {"ok": True, "release": result.to_dict()}

    @router.post("/{release_id}/promote")
    def promote(
        release_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        control, plan, provider = plan_and_provider(release_id)
        control.controller.policy = control.policy()
        try:
            result = control.controller.promote(release_id, provider=provider)
        except Exception as exc:
            emit("owner.release.promotion_failed", device_id=device_id, release_id=release_id, error_type=type(exc).__name__)
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.promoted", device_id=device_id, release_id=release_id, status=result.status.value)
        return {"ok": True, "release": result.to_dict()}

    @router.post("/{release_id}/canary")
    def canary(
        release_id: str,
        body: CanaryBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        control = release_runtime()
        control.controller.policy = control.policy()
        try:
            result = control.controller.record_canary(
                release_id,
                baseline=CanaryMetrics(**body.baseline.model_dump()),
                candidate=CanaryMetrics(**body.candidate.model_dump()),
                additional_checks=body.additional_checks,
            )
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.canary_recorded", device_id=device_id, release_id=release_id, status=result.status.value)
        return {"ok": True, "release": result.to_dict()}

    @router.post("/{release_id}/regression")
    def regression(
        release_id: str,
        body: RegressionBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            created = release_runtime().controller.observe_regression(
                release_id,
                signal=body.signal,
                evidence=tuple(body.evidence),
                severity=body.severity,
            )
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.regression_recorded", device_id=device_id, release_id=release_id)
        return {"ok": True, "work": created.to_dict() if hasattr(created, "to_dict") else None}

    @router.post("/{release_id}/rollback")
    def rollback(
        release_id: str,
        body: RollbackBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        control, plan, provider = plan_and_provider(release_id)
        control.controller.policy = control.policy()
        try:
            result = control.controller.rollback(release_id, provider=provider, explicitly_approved=body.confirm)
        except Exception as exc:
            emit("owner.release.rollback_failed", device_id=device_id, release_id=release_id, error_type=type(exc).__name__)
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.rolled_back", device_id=device_id, release_id=release_id, restored_revision=plan.base_revision)
        return {"ok": True, "release": result.to_dict()}

    @router.post("/{release_id}/cancel")
    def cancel(
        release_id: str,
        body: CancelBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            result = release_runtime().controller.cancel(release_id, reason=body.reason)
        except Exception as exc:
            raise HTTPException(409, str(exc)) from exc
        emit("owner.release.cancelled", device_id=device_id, release_id=release_id)
        return {"ok": True, "release": result.to_dict()}

    return router
