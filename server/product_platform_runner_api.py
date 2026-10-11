from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request
from fastapi.responses import Response

from products.build_lifecycle import ProductBuildLifecycle
from products.platform_jobs import (
    PlatformBuildJobError,
    ProductPlatformBuildJobs,
    max_artifact_bytes,
    runner_configured,
    runner_token_matches,
)
from security.request_context import current_trusted_request


def product_platform_runner_router(runtime, product_store):
    router = APIRouter(tags=["product-platform-runner"])
    registry = runtime["device_registry"]
    settings = runtime.get("settings")
    data_dir = Path(getattr(settings, "data_dir", product_store.path.parent))
    lifecycle = ProductBuildLifecycle(product_store.path)
    jobs = ProductPlatformBuildJobs(product_store, lifecycle, data_dir / "product-artifacts")
    runtime["product_platform_jobs"] = jobs

    def owner_auth(device_id: str | None, token: str | None, *, write: bool = False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Our Products")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, "A current trusted owner session is required to prepare platform builds")

    def runner_auth(authorization: str | None):
        if not runner_configured():
            raise HTTPException(503, "Product platform runner authentication is not configured")
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix) or not runner_token_matches(authorization[len(prefix):]):
            raise HTTPException(401, "Product platform runner authentication failed")

    def product_or_404(product_id: str):
        product = product_store.get(product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        return product

    @router.get("/iphone/api/products/{product_id}/builds/{build_id}/platform-job")
    def owner_download_platform_job(
        product_id: str,
        build_id: str,
        development: bool = Query(default=False),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        owner_auth(pa_device, pa_token, write=True)
        product_or_404(product_id)
        try:
            filename, raw, metadata = jobs.prepare_job(product_id, build_id, development=development)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except PlatformBuildJobError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(
            raw,
            media_type="application/vnd.vishnu.product-build-job+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Vishnu-Build-Job-SHA256": metadata["sha256"],
                "X-Vishnu-Build-Job-Signed": "true" if metadata["signed"] else "false",
                "Cache-Control": "no-store",
            },
        )

    @router.get("/iphone/api/product-runner/{product_id}/{build_id}/job")
    def runner_download_job(
        product_id: str,
        build_id: str,
        authorization: str | None = Header(default=None),
    ):
        runner_auth(authorization)
        product_or_404(product_id)
        try:
            filename, raw, metadata = jobs.prepare_job(product_id, build_id, development=False)
            jobs.mark_running(product_id, build_id)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except PlatformBuildJobError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(
            raw,
            media_type="application/vnd.vishnu.product-build-job+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Vishnu-Build-Job-SHA256": metadata["sha256"],
                "Cache-Control": "no-store",
            },
        )

    @router.put("/iphone/api/product-runner/{product_id}/{build_id}/artifact")
    async def runner_upload_artifact(
        product_id: str,
        build_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        x_vishnu_artifact_name: str | None = Header(default=None),
        x_vishnu_artifact_sha256: str | None = Header(default=None),
        x_vishnu_platform_signing_verified: str | None = Header(default=None),
        x_vishnu_runner_metadata: str | None = Header(default=None),
        content_length: int | None = Header(default=None),
    ):
        runner_auth(authorization)
        product_or_404(product_id)
        if content_length is not None and content_length > max_artifact_bytes():
            raise HTTPException(413, "Platform artifact exceeds the configured size limit")
        raw = await request.body()
        metadata = {}
        if x_vishnu_runner_metadata:
            if len(x_vishnu_runner_metadata) > 4096:
                raise HTTPException(422, "Runner metadata header is too large")
            try:
                parsed = json.loads(x_vishnu_runner_metadata)
            except ValueError as exc:
                raise HTTPException(422, "Runner metadata must be valid JSON") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(422, "Runner metadata must be a JSON object")
            metadata = parsed
        signing_verified = str(x_vishnu_platform_signing_verified or "").strip().lower() in {"1", "true", "yes"}
        try:
            build = jobs.accept_artifact(
                product_id,
                build_id,
                filename=str(x_vishnu_artifact_name or ""),
                expected_sha256=str(x_vishnu_artifact_sha256 or ""),
                payload=raw,
                platform_signing_verified=signing_verified,
                runner_metadata=metadata,
            )
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except PlatformBuildJobError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"build": build, "accepted": True}

    @router.post("/iphone/api/product-runner/{product_id}/{build_id}/failed")
    async def runner_report_failure(
        product_id: str,
        build_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        runner_auth(authorization)
        product_or_404(product_id)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        reason = str(payload.get("reason") or "Platform runner failed")[:2000] if isinstance(payload, dict) else "Platform runner failed"
        try:
            build = jobs.mark_failed(product_id, build_id, reason)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except PlatformBuildJobError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"build": build, "accepted": True}

    return router
