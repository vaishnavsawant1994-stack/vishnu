from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from products.artifact_builders import ArtifactBuilderError, ProductArtifactBuilder
from products.build_lifecycle import ProductBuildLifecycle
from products.license_store import ProductLicenseStore
from products.package_export import build_portable_package
from products.signing import signing_available
from products.versioning import frozen_version, list_frozen_versions
from security.request_context import current_trusted_request


class LicenseCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(min_length=1, max_length=200)
    license_type: str = Field(default="organization", min_length=1, max_length=80)
    version_constraint: str | None = Field(default=None, max_length=80)
    starts_at: str | None = Field(default=None, max_length=80)
    expires_at: str | None = Field(default=None, max_length=80)
    max_users: int | None = Field(default=None, ge=1, le=1_000_000)
    max_devices: int | None = Field(default=None, ge=1, le=1_000_000)
    managed_ai: bool = False

    @field_validator("starts_at", "expires_at")
    @classmethod
    def valid_timestamp(cls, value):
        if value in (None, ""):
            return None
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("License timestamps must use ISO 8601") from exc
        return value


def product_distribution_router(runtime, product_store, license_store: ProductLicenseStore):
    router = APIRouter(prefix="/iphone/api/products", tags=["product-distribution"])
    registry = runtime["device_registry"]
    lifecycle = ProductBuildLifecycle(product_store.path)
    settings = runtime.get("settings")
    data_dir = Path(getattr(settings, "data_dir", product_store.path.parent))
    artifact_builder = ProductArtifactBuilder(product_store, lifecycle, data_dir / "product-artifacts")
    runtime["product_artifact_builder"] = artifact_builder

    def authenticate(device_id: str | None, token: str | None, *, write=False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Our Products")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, "A current trusted owner session is required to change product distribution")

    def product_or_404(product_id: str):
        product = product_store.get(product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        return product

    @router.get("/{product_id}/distribution/status")
    def distribution_status(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product = product_or_404(product_id)
        versions = list_frozen_versions(product_store, product_id)
        frozen_numbers = [item["version"] for item in versions]
        current_frozen = product["version"] in frozen_numbers
        return {
            "signing_configured": signing_available(),
            "portable_package": True,
            "current_version": product["version"],
            "current_version_frozen": current_frozen,
            "frozen_versions": frozen_numbers,
            "production_distribution_ready": signing_available() and current_frozen,
            "verified_local_build_targets": list(artifact_builder.available_targets()),
            "native_builds": "target-builder qualification required",
        }

    @router.get("/{product_id}/package")
    def download_product_package(
        product_id: str,
        development: bool = Query(default=False),
        version: str | None = Query(default=None, max_length=80),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        product = product_or_404(product_id)
        selected_version = str(version or product["version"]).strip()
        if development:
            if version:
                snapshot = frozen_version(product_store, product_id, selected_version)
                if not snapshot:
                    raise HTTPException(404, "Frozen product version not found")
                manifest = snapshot["manifest"]
            else:
                manifest = product_store.manifest(product_id)
        else:
            if not signing_available():
                raise HTTPException(503, "Production product signing is not configured")
            snapshot = frozen_version(product_store, product_id, selected_version)
            if not snapshot:
                raise HTTPException(409, "Freeze this product version before production distribution")
            manifest = snapshot["manifest"]
        if not manifest:
            raise HTTPException(404, "Product manifest not found")
        try:
            filename, raw, metadata = build_portable_package(manifest, require_signature=not development)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        suffix = "" if metadata["signed"] else "-UNSIGNED-DEVELOPMENT"
        if suffix:
            filename = filename.replace(".vishnu-product", f"{suffix}.vishnu-product")
        return Response(
            content=raw,
            media_type="application/vnd.vishnu.product+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Vishnu-Product-SHA256": metadata["package_sha256"],
                "X-Vishnu-Product-Signed": "true" if metadata["signed"] else "false",
                "X-Vishnu-Product-Version": str(manifest.get("version", selected_version)),
                "Cache-Control": "no-store",
            },
        )

    @router.post("/{product_id}/builds/{build_id}/execute")
    def execute_product_build(
        product_id: str,
        build_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        product_or_404(product_id)
        try:
            build = artifact_builder.execute(product_id, build_id)
        except KeyError as exc:
            raise HTTPException(404, "Build not found") from exc
        except ArtifactBuilderError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            # Detailed diagnostics are retained in the owner-only build lifecycle.
            # The HTTP boundary exposes only the exception class, never local paths.
            raise HTTPException(500, f"Product artifact build failed ({type(exc).__name__})") from exc
        return {
            "build": build,
            "builder": "verified-local-runtime",
            "download_ready": bool(build.get("metadata", {}).get("artifact_ready")),
        }

    @router.get("/{product_id}/builds/{build_id}/artifact")
    def download_product_build_artifact(
        product_id: str,
        build_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        try:
            path, build = artifact_builder.resolve_artifact(product_id, build_id)
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

    @router.get("/{product_id}/licenses")
    def list_licenses(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        return {"licenses": license_store.list_for_product(product_id)}

    @router.post("/{product_id}/licenses", status_code=201)
    def issue_license(product_id: str, body: LicenseCreateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        product = product_or_404(product_id)
        if not signing_available():
            raise HTTPException(503, "Production product signing is not configured")
        if body.version_constraint is None and frozen_version(product_store, product_id, product["version"]) is None:
            raise HTTPException(409, "Freeze the current product version before issuing its default commercial license")
        try:
            license_record = license_store.issue(
                product=product,
                metadata={"issued_from": "our-products"},
                **body.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"license": license_record}

    @router.get("/{product_id}/licenses/{license_id}/download")
    def download_license(product_id: str, license_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        record = license_store.get(license_id)
        if not record or record["product_id"] != product_id:
            raise HTTPException(404, "License not found")
        raw = json.dumps(record["document"], sort_keys=True, indent=2).encode("utf-8")
        return Response(
            content=raw,
            media_type="application/vnd.vishnu.license+json",
            headers={
                "Content-Disposition": f'attachment; filename="{license_id}.vishnu-license.json"',
                "Cache-Control": "no-store",
            },
        )

    @router.post("/{product_id}/licenses/{license_id}/revoke")
    def revoke_license(product_id: str, license_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        product_or_404(product_id)
        record = license_store.revoke(product_id, license_id)
        if not record:
            raise HTTPException(404, "License not found")
        return {"license": record}

    return router
