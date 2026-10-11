from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from products.build_lifecycle import BUILD_STATUSES, ProductBuildLifecycle
from products.models import AI_MODES, PLATFORM_TARGETS, PRODUCT_STATUSES, PRODUCT_TYPES
from products.store import ProductStore
from security.request_context import current_trusted_request


class ProductCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    product_type: str = Field(default="custom")
    description: str = Field(default="", max_length=5000)
    client_name: str = Field(default="", max_length=200)
    status: str = Field(default="development")
    version: str = Field(default="0.1.0", min_length=1, max_length=80)
    ai_mode: str = Field(default="disabled")
    targets: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("product_type")
    @classmethod
    def valid_type(cls, value):
        if value not in PRODUCT_TYPES:
            raise ValueError("Unsupported product type")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in PRODUCT_STATUSES:
            raise ValueError("Unsupported product status")
        return value

    @field_validator("ai_mode")
    @classmethod
    def valid_ai_mode(cls, value):
        if value not in AI_MODES:
            raise ValueError("Unsupported AI mode")
        return value

    @field_validator("targets")
    @classmethod
    def valid_targets(cls, value):
        if any(item not in PLATFORM_TARGETS for item in value):
            raise ValueError("Unsupported platform target")
        return value


class ProductUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    product_type: str | None = None
    description: str | None = Field(default=None, max_length=5000)
    client_name: str | None = Field(default=None, max_length=200)
    status: str | None = None
    version: str | None = Field(default=None, min_length=1, max_length=80)
    branding: dict | None = None
    licensing: dict | None = None
    permissions: dict | None = None

    @field_validator("product_type")
    @classmethod
    def valid_type(cls, value):
        if value is not None and value not in PRODUCT_TYPES:
            raise ValueError("Unsupported product type")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in PRODUCT_STATUSES:
            raise ValueError("Unsupported product status")
        return value


class AIPolicyBody(BaseModel):
    mode: str = Field(default="disabled")
    provider: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=200)
    secret_ref: str = Field(default="", max_length=300)
    fallback_provider: str = Field(default="", max_length=120)
    fallback_model: str = Field(default="", max_length=200)
    local_endpoint: str = Field(default="", max_length=1000)
    sensitive_data_policy: str = Field(default="standard", max_length=120)
    monthly_budget: float | None = Field(default=None, ge=0)
    allow_fallback: bool = False

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value):
        if value not in AI_MODES:
            raise ValueError("Unsupported AI mode")
        return value


class TargetBody(BaseModel):
    target: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)

    @field_validator("target")
    @classmethod
    def valid_target(cls, value):
        if value not in PLATFORM_TARGETS:
            raise ValueError("Unsupported platform target")
        return value


class TargetListBody(BaseModel):
    targets: list[TargetBody] = Field(default_factory=list, max_length=20)


class ComponentBody(BaseModel):
    component_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    component_ref: str | None = Field(default=None, max_length=300)
    config: dict = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=-10000, le=10000)


class VersionBody(BaseModel):
    version: str | None = Field(default=None, min_length=1, max_length=80)
    notes: str = Field(default="", max_length=4000)


class BuildBody(BaseModel):
    target: str
    version: str | None = Field(default=None, max_length=80)

    @field_validator("target")
    @classmethod
    def valid_target(cls, value):
        if value not in PLATFORM_TARGETS:
            raise ValueError("Unsupported platform target")
        return value


class BuildUpdateBody(BaseModel):
    status: str | None = None
    artifact_name: str | None = Field(default=None, max_length=300)
    artifact_uri: str | None = Field(default=None, max_length=2000)
    checksum: str | None = Field(default=None, max_length=256)
    signing_verified: bool | None = None
    failure_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in BUILD_STATUSES:
            raise ValueError("Unsupported build status")
        return value


class PromoteProjectBody(BaseModel):
    product_type: str = Field(default="custom")
    client_name: str = Field(default="", max_length=200)

    @field_validator("product_type")
    @classmethod
    def valid_type(cls, value):
        if value not in PRODUCT_TYPES:
            raise ValueError("Unsupported product type")
        return value


def products_router(runtime, store: ProductStore, project_store=None):
    router = APIRouter(prefix="/iphone/api/products", tags=["our-products"])
    registry = runtime["device_registry"]
    builds = ProductBuildLifecycle(store.path)

    def authenticate(device_id: str | None, token: str | None, *, write=False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Our Products")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, "A current trusted owner session is required to change product data")
        return device_id

    def product_or_404(product_id: str):
        value = store.get(product_id)
        if not value:
            raise HTTPException(404, "Product not found")
        return value

    @router.get("/summary")
    def summary(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {"summary": store.summary()}

    @router.get("/activity")
    def activity(limit: int = Query(default=30, ge=1, le=200), pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {"activity": store.activity(limit=limit)}

    @router.get("")
    def list_products(
        q: str = Query(default="", max_length=160),
        product_type: str = Query(default="all"),
        status: str = Query(default="all"),
        sort: str = Query(default="recent", pattern="^(recent|name|created)$"),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        try:
            return {"products": store.list(q, product_type=product_type, status=status, sort=sort)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("", status_code=201)
    def create_product(body: ProductCreateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            product = store.create(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"product": product}

    @router.post("/from-project/{project_id}", status_code=201)
    def promote_project(project_id: str, body: PromoteProjectBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if project_store is None:
            raise HTTPException(503, "Project workspace is unavailable")
        project = project_store.get(project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        try:
            product = store.create_from_project(project, product_type=body.product_type, client_name=body.client_name)
        except ValueError as exc:
            raise HTTPException(409 if "already" in str(exc).lower() else 422, str(exc)) from exc
        return {"product": product}

    @router.get("/{product_id}")
    def get_product(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product = product_or_404(product_id)
        return {
            "product": product,
            "components": store.components(product_id),
            "builds": builds.list(product_id, store.builds(product_id)),
        }

    @router.patch("/{product_id}")
    def update_product(product_id: str, body: ProductUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            product = store.update(product_id, body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not product:
            raise HTTPException(404, "Product not found")
        return {"product": product}

    @router.delete("/{product_id}", status_code=204)
    def archive_product(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.archive(product_id):
            raise HTTPException(404, "Product not found")

    @router.put("/{product_id}/ai-policy")
    def set_ai_policy(product_id: str, body: AIPolicyBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            product = store.set_ai_policy(product_id, body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not product:
            raise HTTPException(404, "Product not found")
        return {"product": product}

    @router.put("/{product_id}/targets")
    def set_targets(product_id: str, body: TargetListBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            product = store.set_targets(product_id, [item.model_dump() for item in body.targets])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not product:
            raise HTTPException(404, "Product not found")
        return {"product": product}

    @router.post("/{product_id}/components", status_code=201)
    def add_component(product_id: str, body: ComponentBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            component = store.add_component(product_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not component:
            raise HTTPException(404, "Product not found")
        return {"component": component}

    @router.delete("/{product_id}/components/{component_id}", status_code=204)
    def remove_component(product_id: str, component_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.remove_component(product_id, component_id):
            raise HTTPException(404, "Component not found")

    @router.get("/{product_id}/manifest")
    def manifest(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        value = store.manifest(product_id)
        if not value:
            raise HTTPException(404, "Product not found")
        return {"manifest": value}

    @router.post("/{product_id}/versions", status_code=201)
    def create_version(product_id: str, body: VersionBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.create_version(product_id, version=body.version, notes=body.notes)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not value:
            raise HTTPException(404, "Product not found")
        return {"version": value}

    @router.get("/{product_id}/builds")
    def list_builds(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        return {"builds": builds.list(product_id, store.builds(product_id))}

    @router.post("/{product_id}/builds", status_code=202)
    def request_build(product_id: str, body: BuildBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.request_build(product_id, target=body.target, version=body.version)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, "Product not found")
        return {"build": builds.ensure(value)}

    @router.patch("/{product_id}/builds/{build_id}")
    def update_build(product_id: str, build_id: str, body: BuildUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        product_or_404(product_id)
        try:
            value = builds.update(product_id, build_id, **body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, "Build not found")
        return {"build": value}

    return router
