from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response

from products.build_lifecycle import ProductBuildLifecycle
from products.platform_jobs import (
    PlatformBuildJobError,
    ProductPlatformBuildJobs,
    max_artifact_bytes,
    runner_configured,
    runner_token_matches,
)
from products.runner_leases import ProductRunnerLeases, RunnerLeaseError
from products.signing import signing_available


_RUNNER_EVIDENCE_HEADER_LIMIT = 16 * 1024


def product_runner_queue_router(runtime, product_store):
    router = APIRouter(prefix="/iphone/api/products/runner", tags=["product-runner-queue"])
    settings = runtime.get("settings")
    data_dir = Path(getattr(settings, "data_dir", product_store.path.parent))
    lifecycle = ProductBuildLifecycle(product_store.path)
    platform_jobs = ProductPlatformBuildJobs(product_store, lifecycle, data_dir / "product-artifacts")
    leases = ProductRunnerLeases(product_store, lifecycle)
    runtime["product_runner_leases"] = leases

    def authenticate(authorization: str | None):
        if not runner_configured():
            raise HTTPException(503, "Product platform runner authentication is not configured")
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix) or not runner_token_matches(authorization[len(prefix):]):
            raise HTTPException(401, "Product platform runner authentication failed")

    def active_lease(build_id: str, token: str | None) -> dict:
        try:
            lease = leases._active(build_id, str(token or ""))
        except RunnerLeaseError as exc:
            raise HTTPException(409, str(exc)) from exc
        lease.pop("lease_token_hash", None)
        return lease

    def parse_evidence(raw: str | None) -> dict:
        if not raw:
            raise HTTPException(422, "X-Vishnu-Runner-Evidence is required for autonomous artifact callbacks")
        if len(raw) > _RUNNER_EVIDENCE_HEADER_LIMIT:
            raise HTTPException(422, "Runner evidence header is too large")
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(422, "Runner evidence must be valid JSON") from exc
        if not isinstance(value, dict):
            raise HTTPException(422, "Runner evidence must be a JSON object")
        return value

    @router.post("/claim")
    def claim_next_build(
        target: str = Query(min_length=1, max_length=40),
        authorization: str | None = Header(default=None),
        x_vishnu_runner_id: str | None = Header(default=None),
    ):
        authenticate(authorization)
        if not signing_available():
            raise HTTPException(503, "Production product signing must be configured before autonomous platform runners can claim work")
        try:
            lease = leases.claim(target=target, runner_id=str(x_vishnu_runner_id or ""))
        except RunnerLeaseError as exc:
            raise HTTPException(422, str(exc)) from exc
        if lease is None:
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        try:
            filename, raw, metadata = platform_jobs.prepare_job(
                lease["product_id"], lease["build_id"], development=False
            )
        except (KeyError, PlatformBuildJobError, ValueError) as exc:
            try:
                leases.release(lease["build_id"], lease["lease_token"], reason=f"Build-job preparation failed: {type(exc).__name__}", retry=True)
            except Exception:
                pass
            if isinstance(exc, KeyError):
                raise HTTPException(404, "Claimed build no longer exists") from exc
            raise HTTPException(409 if isinstance(exc, PlatformBuildJobError) else 503, str(exc)) from exc
        return Response(
            raw,
            media_type="application/vnd.vishnu.product-build-job+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Vishnu-Build-Job-SHA256": metadata["sha256"],
                "X-Vishnu-Product-ID": lease["product_id"],
                "X-Vishnu-Build-ID": lease["build_id"],
                "X-Vishnu-Build-Target": lease["target"],
                "X-Vishnu-Runner-Lease": lease["lease_token"],
                "X-Vishnu-Runner-Lease-Expires": lease["expires_at"],
                "X-Vishnu-Runner-Attempt": str(lease["attempt"]),
                "Cache-Control": "no-store",
            },
        )

    @router.post("/{build_id}/heartbeat")
    def heartbeat(
        build_id: str,
        authorization: str | None = Header(default=None),
        x_vishnu_runner_lease: str | None = Header(default=None),
    ):
        authenticate(authorization)
        try:
            lease = leases.heartbeat(build_id, str(x_vishnu_runner_lease or ""))
        except RunnerLeaseError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"lease": lease}

    @router.put("/{build_id}/artifact")
    async def upload_artifact(
        build_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_vishnu_runner_lease: str | None = Header(default=None),
        x_vishnu_artifact_name: str | None = Header(default=None),
        x_vishnu_artifact_sha256: str | None = Header(default=None),
        x_vishnu_runner_evidence: str | None = Header(default=None),
        content_length: int | None = Header(default=None),
    ):
        authenticate(authorization)
        lease = active_lease(build_id, x_vishnu_runner_lease)
        if content_length is not None and content_length > max_artifact_bytes():
            raise HTTPException(413, "Platform artifact exceeds the configured size limit")
        payload = await request.body()
        evidence = parse_evidence(x_vishnu_runner_evidence)
        try:
            build = platform_jobs.accept_artifact(
                lease["product_id"],
                build_id,
                filename=str(x_vishnu_artifact_name or ""),
                expected_sha256=str(x_vishnu_artifact_sha256 or ""),
                payload=payload,
                runner_evidence=evidence,
            )
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except PlatformBuildJobError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "build": build,
            "accepted": True,
            "lease_completion_required": True,
        }

    @router.post("/{build_id}/failed")
    async def report_failure(
        build_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_vishnu_runner_lease: str | None = Header(default=None),
    ):
        authenticate(authorization)
        lease = active_lease(build_id, x_vishnu_runner_lease)
        try:
            body = await request.json()
        except Exception:
            body = {}
        reason = str(body.get("reason") or "Platform runner failed")[:2000] if isinstance(body, dict) else "Platform runner failed"
        try:
            build = platform_jobs.mark_failed(lease["product_id"], build_id, reason)
            completed = leases.complete(build_id, str(x_vishnu_runner_lease or ""))
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except (PlatformBuildJobError, RunnerLeaseError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"build": build, "lease": completed, "accepted": True}

    @router.post("/{build_id}/complete")
    def complete(
        build_id: str,
        authorization: str | None = Header(default=None),
        x_vishnu_runner_lease: str | None = Header(default=None),
    ):
        authenticate(authorization)
        try:
            lease = leases.complete(build_id, str(x_vishnu_runner_lease or ""))
        except RunnerLeaseError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"lease": lease}

    @router.post("/{build_id}/release")
    def release(
        build_id: str,
        retry: bool = Query(default=True),
        reason: str = Query(default="Runner released lease", max_length=500),
        authorization: str | None = Header(default=None),
        x_vishnu_runner_lease: str | None = Header(default=None),
    ):
        authenticate(authorization)
        try:
            lease = leases.release(build_id, str(x_vishnu_runner_lease or ""), reason=reason, retry=retry)
        except RunnerLeaseError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"lease": lease}

    @router.get("/status")
    def queue_status(authorization: str | None = Header(default=None)):
        authenticate(authorization)
        return leases.status()

    return router
