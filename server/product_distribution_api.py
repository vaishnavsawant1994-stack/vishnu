from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Cookie, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from products.license_store import ProductLicenseStore
from products.package_export import build_portable_package
from products.signing import signing_available
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
        product_or_404(product_id)
        return {
            "signing_configured": signing_available(),
            "portable_package": True,
            "production_distribution_ready": signing_available(),
            "native_builds": "target-builder qualification required",
        }

    @router.get("/{product_id}/package")
    def download_product_package(
        product_id: str,
        development: bool = Query(default=False),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        manifest = product_store.manifest(product_id)
        if not manifest:
            raise HTTPException(404, "Product manifest not found")
        if not development and not signing_available():
            raise HTTPException(503, "Production product signing is not configured")
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
                "Cache-Control": "no-store",
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
