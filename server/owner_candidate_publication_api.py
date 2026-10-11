from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict

from future_intelligence.candidate_publication import CandidatePublicationError
from security.request_context import current_trusted_request


_CONFIRMATION = "publish-qualified-candidate-as-draft-pr"


class CandidatePublicationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["publish-qualified-candidate-as-draft-pr"]


def owner_candidate_publication_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/iphone/api/owner/engineering", tags=["owner-candidate-publication"])
    registry = runtime["device_registry"]
    events = runtime.get("events")

    def authenticate(device_id: str | None, token: str | None) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if not registry.is_active(device_id):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "device:admin"):
            raise HTTPException(403, "This device is not permitted to publish engineering candidates")
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
                "message": "Fresh owner verification is required to publish a qualified candidate remotely.",
            })

    def service():
        value = runtime.get("candidate_publication")
        if value is None:
            raise HTTPException(503, "governed candidate publication is disabled or unavailable on this host")
        return value

    @router.get("/candidate-publication")
    def publication_summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        value = runtime.get("candidate_publication")
        return {
            "available": value is not None,
            "confirmation_phrase": _CONFIRMATION,
            "authority": {
                "qualified_candidate_only": True,
                "new_governed_branch_only": True,
                "force_push": False,
                "draft_pull_request_only": True,
                "merge": False,
                "deploy": False,
                "release": False,
                "body_activation": False,
            },
        }

    @router.get("/work/{work_order_id}/attempt/{attempt_id}/candidate-publication")
    def publication_preview(
        work_order_id: str,
        attempt_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        try:
            plan = service().preview(str(work_order_id), str(attempt_id))
        except KeyError as exc:
            raise HTTPException(404, "Engineering Work/Attempt not found") from exc
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError, CandidatePublicationError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "available": True,
            "plan": plan.to_dict(),
            "confirmation_phrase": _CONFIRMATION,
            "authority": {
                "force_push": False,
                "merge": False,
                "deploy": False,
                "release": False,
                "body_activation": False,
            },
        }

    @router.post("/work/{work_order_id}/attempt/{attempt_id}/candidate-publication")
    def publish_candidate(
        work_order_id: str,
        attempt_id: str,
        body: CandidatePublicationBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token)
        require_fresh_owner_verification(device_id)
        try:
            result = service().publish(
                str(work_order_id),
                str(attempt_id),
                confirmation=body.confirmation,
                explicitly_owner_approved=True,
            )
        except KeyError as exc:
            raise HTTPException(404, "Engineering Work/Attempt not found") from exc
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except CandidatePublicationError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if events is not None:
            events.emit(
                "owner.engineering.candidate_published",
                device_id=device_id,
                work_order_id=str(work_order_id),
                attempt_id=str(attempt_id),
                candidate_revision=result.remote_revision,
                pull_request_number=result.pull_request_number,
                draft=True,
                merge_authority=False,
            )
        return {
            "ok": True,
            "result": result.to_dict(),
            "authority": {
                "force_push": False,
                "merge": False,
                "deploy": False,
                "release": False,
                "body_activation": False,
            },
        }

    return router
