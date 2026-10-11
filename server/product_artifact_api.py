from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import FileResponse

from products.artifact_builders import ArtifactBuilderError, ProductArtifactBuilder
from products.build_lifecycle import ProductBuildLifecycle
from security.request_context import current_trusted_request


def product_artifact_router(runtime, store):
    """Owner-only execution/download surface for verified product builders."""

    router = APIRouter(prefix="/iphone/api/products", tags=["our-products-builders"])
    registry = runtime["device_registry"]
    lifecycle = ProductBuildLifecycle(store.path)
    settings = runtime.get("settings")
    data_dir = Path(getattr(settings, "data_dir", store.path.parent))
    builder = ProductArtifactBuilder(store, lifecycle, data_dir / "product-artifacts")
    runtime["product_artifact_builder"] = builder

    def authenticate(device_id: str | None, token: str | None, *, write: bool = False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Our Products")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, "A current trusted owner session is required to execute product builds")
        return device_id

    @router.post("/{product_id}/builds/{build_id}/execute")
    def execute_build(
        product_id: str,
        build_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            build = builder.execute(product_id, build_id)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except ArtifactBuilderError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            # The detailed failure is recorded on the owner-only build lifecycle;
            # do not leak local paths or runtime internals over the HTTP boundary.
            raise HTTPException(500, f"Product artifact build failed ({type(exc).__name__})") from exc
        return {"build": build, "builder": "verified-local-runtime", "download_ready": bool(build.get("metadata", {}).get("artifact_ready"))}

    @router.get("/{product_id}/builds/{build_id}/artifact")
    def download_build_artifact(
        product_id: str,
        build_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        try:
            path, build = builder.resolve_artifact(product_id, build_id)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except ArtifactBuilderError as exc:
            raise HTTPException(409, str(exc)) from exc
        return FileResponse(
            path,
            media_type="application/zip",
            filename=build.get("artifact_name") or path.name,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Vishnu-Artifact-SHA256": str(build.get("checksum") or ""),
            },
        )

    return router
