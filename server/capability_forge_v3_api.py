from __future__ import annotations

import html
import os
import time
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from future_intelligence.engineering.canary import CanaryMetrics
from security.request_context import current_trusted_request


class OAuthStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[str] = Field(default_factory=list, max_length=50)
    redirect_uri: str | None = Field(default=None, max_length=1000)


class ProviderVerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str = Field(min_length=1, max_length=240)
    parameters: dict[str, Any] = Field(default_factory=dict)
    capability_id: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=80)


class CanaryInvokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    build_id: str = Field(min_length=1, max_length=240)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RolloutPromotionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_stage: str = Field(min_length=1, max_length=40)
    ticket_id: str | None = Field(default=None, max_length=240)


class ActiveHealthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_count: int = Field(ge=1, le=1_000_000)
    error_rate: float = Field(ge=0.0, le=1.0)
    p95_latency_ms: float = Field(ge=0.0, le=3_600_000.0)


def _owner_guards(runtime):
    registry = runtime["device_registry"]

    def authenticate(device_id: str | None, token: str | None) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token) or not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "device:admin"):
            raise HTTPException(403, "This device is not permitted to manage Capability Forge")
        return device_id

    def fresh(device_id: str):
        if runtime.get("pwa_sessions") is None:
            return None
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
                "message": "Fresh owner verification is required for Capability Forge V3 mutations.",
            })
        return context

    return authenticate, fresh


def capability_forge_v3_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/owner/forge/v3", tags=["capability-forge-v3"])
    authenticate, fresh = _owner_guards(runtime)

    def require(name: str):
        value = runtime.get(name)
        if value is None:
            raise HTTPException(503, f"{name.replace('_', ' ')} is unavailable on this host")
        return value

    @router.get("/readiness")
    def readiness(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        service = require("capability_forge_production_readiness")
        sessions = runtime.get("pwa_sessions")
        result = service.evaluate(
            public_base_url=os.getenv("VISHNU_PUBLIC_BASE_URL"),
            oauth_redirect_uri=os.getenv("VISHNU_CAPABILITY_OAUTH_REDIRECT_URI"),
            android_asset_links=runtime.get("android_asset_links", []),
            apple_app_site_association=runtime.get("apple_app_site_association", {}),
            native_client_redirects=getattr(sessions, "native_client_redirects", {}) if sessions is not None else {},
            provenance_available=runtime.get("capability_forge_provenance") is not None,
            provider_verification_available=runtime.get("capability_forge_provider_verifier") is not None,
            canary_available=runtime.get("capability_forge_rollout") is not None,
            external_oauth_available=runtime.get("capability_forge_oauth") is not None,
        )
        payload = result.to_dict()
        payload["production_activation_authority"] = False
        payload["configuration_only"] = True
        return payload

    @router.get("/oauth/providers")
    def oauth_providers(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        providers = runtime.get("oauth_providers") or {}
        return {"items": [{"id": str(key), "scopes": list(value.scopes)} for key, value in sorted(providers.items())]}

    @router.post("/oauth/{capability_id}/{provider_id}/start")
    def oauth_start(capability_id: str, provider_id: str, body: OAuthStartBody,
                    pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        context = fresh(device_id)
        callback = str(body.redirect_uri or os.getenv("VISHNU_CAPABILITY_OAUTH_REDIRECT_URI") or "").strip()
        if not callback:
            raise HTTPException(409, "Capability OAuth callback URI is not configured")
        service = require("capability_forge_oauth")
        try:
            return service.begin(
                capability_id,
                provider_id,
                scopes=body.scopes or None,
                owner_id="owner",
                device_id=device_id,
                session_id=getattr(context, "session_id", None),
                security_epoch=getattr(context, "security_epoch", None),
                redirect_uri=callback,
            )
        except KeyError as exc:
            raise HTTPException(404, "Capability or OAuth provider was not found") from exc
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/oauth/{capability_id}/status")
    def oauth_status(capability_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return require("capability_forge_oauth").status(capability_id)

    @router.post("/oauth/{capability_id}/{provider_id}/revoke")
    def oauth_revoke(capability_id: str, provider_id: str,
                     pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        context = fresh(device_id)
        try:
            result = require("capability_forge_oauth").revoke(
                capability_id,
                provider_id,
                owner_id="owner",
                device_id=device_id,
                session_id=getattr(context, "session_id", None),
            )
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return result

    @router.post("/providers/verify")
    def verify_provider(body: ProviderVerifyBody,
                        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        fresh(device_id)
        try:
            return require("capability_forge_provider_verifier").verify(
                body.tool_name,
                body.parameters,
                capability_id=body.capability_id,
                version=body.version,
                data_classification="internal",
            )
        except KeyError as exc:
            raise HTTPException(404, "Provider verification tool was not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Provider verification failed: {type(exc).__name__}") from exc

    @router.get("/rollout/{capability_id}/{version}")
    def rollout_state(capability_id: str, version: str,
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        try:
            return require("capability_forge_rollout").get(capability_id, version)
        except KeyError as exc:
            raise HTTPException(404, "Forge rollout was not found") from exc

    @router.post("/rollout/{capability_id}/{version}/canary")
    def invoke_canary(capability_id: str, version: str, body: CanaryInvokeBody,
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        fresh(device_id)
        lifecycle = require("capability_forge_lifecycle")
        build = lifecycle.get_build(body.build_id)
        if not build or build.get("status") != "packaged":
            raise HTTPException(409, "Forge build is not a packaged qualified candidate")
        payload = dict(build.get("payload") or {})
        if str(payload.get("capability_id") or "") != str(capability_id) or str(payload.get("version") or "") != str(version):
            raise HTTPException(409, "Forge canary build identity does not match the requested rollout")
        rollout = require("capability_forge_rollout").get(capability_id, version)
        stage = str(rollout.get("stage") or "")
        if stage not in {"internal", "limited"}:
            raise HTTPException(409, "This rollout stage does not accept pre-activation canary invocations")
        try:
            return require("capability_forge_canary_runner").invoke(
                package_ref=str(payload.get("package_ref") or ""),
                manifest_digest=str(payload.get("manifest_digest") or ""),
                parameters=body.parameters,
                stage=stage,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/rollout/{capability_id}/{version}/promotion")
    def rollout_promotion(capability_id: str, version: str, body: RolloutPromotionBody,
                          pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        context = fresh(device_id)
        rollout = require("capability_forge_rollout")
        try:
            if body.ticket_id:
                return rollout.promote(
                    capability_id,
                    version,
                    target_stage=body.target_stage,
                    ticket_id=body.ticket_id,
                    owner_id="owner",
                    device_id=device_id,
                    session_id=getattr(context, "session_id", None),
                )
            ticket_id = rollout.request_promotion(
                capability_id,
                version,
                target_stage=body.target_stage,
                owner_id="owner",
                device_id=device_id,
                session_id=getattr(context, "session_id", None),
            )
            return {"approval_id": ticket_id, "committed": False, "target_stage": body.target_stage}
        except (KeyError, ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/health/{capability_id}/{version}")
    def active_health(capability_id: str, version: str, body: ActiveHealthBody,
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token)
        fresh(device_id)
        baseline = CanaryMetrics(body.sample_count, body.error_rate, body.p95_latency_ms)
        try:
            return require("capability_forge_rollout").active_health(capability_id, version, baseline=baseline)
        except KeyError as exc:
            raise HTTPException(404, "Forge capability health record was not found") from exc

    return router


def capability_forge_oauth_callback_router(runtime) -> APIRouter:
    router = APIRouter(tags=["capability-forge-oauth"])

    @router.get("/iphone/capability-oauth/callback", response_class=HTMLResponse)
    def callback(state: str = Query(..., min_length=16, max_length=512),
                 code: str | None = Query(default=None, max_length=8192),
                 error: str | None = Query(default=None, max_length=200)):
        service = runtime.get("capability_forge_oauth")
        if service is None:
            raise HTTPException(503, "Capability OAuth is unavailable on this host")
        if error:
            service.discard(state)
            message = "The provider did not authorize this capability."
            status = 400
        elif not code:
            service.discard(state)
            message = "The provider callback did not include an authorization code."
            status = 400
        else:
            try:
                binding = service.complete_state(state=state, code=code)
                message = f"Connected {html.escape(binding.capability_id)}. You can return to Capability Forge."
                status = 200
            except Exception as exc:
                message = f"Capability OAuth could not be completed ({html.escape(type(exc).__name__)})."
                status = 409
        page = f"""<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Capability OAuth</title><body style='font:16px system-ui;max-width:38rem;margin:12vh auto;padding:1.5rem;background:#09111b;color:#edf2f7'>
<main><h1>Capability connection</h1><p>{message}</p><p><a href='/capabilities/forge' style='color:#85c8ff'>Return to Capability Forge</a></p></main></body></html>"""
        return HTMLResponse(page, status_code=status, headers={
            "Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
        })

    return router
