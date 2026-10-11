from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from products.build_lifecycle import BUILD_STATUSES, ProductBuildLifecycle
from products.manifest import manifest_for_product
from products.models import AI_MODES, PLATFORM_TARGETS, PRODUCT_STATUSES, PRODUCT_TYPES
from products.service import ProductService
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
    route: str = Field(default="default", max_length=120)
    fallback_provider: str = Field(default="", max_length=120)
    fallback_model: str = Field(default="", max_length=200)
    local_endpoint: str = Field(default="", max_length=1000)
    endpoint_ref: str = Field(default="", max_length=1000)
    monthly_budget: float | None = Field(default=None, ge=0)
    allow_fallback: bool = False
    routes: list[dict] = Field(default_factory=list, max_length=20)
    fallback_route: str = Field(default="", max_length=120)

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value):
        if value not in AI_MODES:
            raise ValueError("Unsupported AI mode")
        return value

    def as_policy(self) -> dict:
        value = self.model_dump()
        mode = value["mode"]
        if mode == "disabled":
            return {"mode": "disabled"}
        if mode == "client_api":
            return {
                "mode": mode,
                "provider": value["provider"],
                "model": value["model"],
                "secret_ref": value["secret_ref"],
            }
        if mode == "managed":
            result = {"mode": mode, "route": value["route"] or "default"}
            if value["monthly_budget"] is not None:
                result["monthly_budget"] = value["monthly_budget"]
            return result
        if mode == "local":
            return {
                "mode": mode,
                "endpoint_ref": value["endpoint_ref"] or value["local_endpoint"],
                "model": value["model"] or "auto",
            }

        routes = list(value["routes"])
        if not routes:
            if value["secret_ref"] or value["provider"]:
                routes.append({
                    "id": "client-primary",
                    "mode": "client_api",
                    "provider": value["provider"],
                    "model": value["model"],
                    "secret_ref": value["secret_ref"],
                    "capabilities": ["default"],
                })
            if value["endpoint_ref"] or value["local_endpoint"]:
                routes.append({
                    "id": "local-private",
                    "mode": "local",
                    "model": value["model"],
                    "endpoint_ref": value["endpoint_ref"] or value["local_endpoint"],
                    "capabilities": ["private"],
                })
            if value["allow_fallback"] or value["fallback_provider"]:
                routes.append({
                    "id": "managed-fallback",
                    "mode": "managed",
                    "provider": value["fallback_provider"],
                    "model": value["fallback_model"],
                    "capabilities": ["fallback"],
                })
        return {
            "mode": "hybrid",
            "routes": routes,
            "fallback_route": value["fallback_route"] or (routes[-1].get("id") if routes else ""),
        }


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
    failure_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in BUILD_STATUSES:
            raise ValueError("Unsupported build status")
        return value


class PermissionsBody(BaseModel):
    permissions: dict = Field(default_factory=dict)


class BrandingBody(BaseModel):
    branding: dict = Field(default_factory=dict)


class LicensingBody(BaseModel):
    licensing: dict = Field(default_factory=dict)


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
    build_lifecycle = ProductBuildLifecycle(store.path)
    service = ProductService(store)

    def authenticate(device_id: str | None, token: str | None, *, write=False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Our Products")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, "A current trusted owner session is required to change product data")
        return device_id

    def translate(call, *, conflict=False):
        try:
            return call()
        except KeyError as exc:
            raise HTTPException(404, "Product not found") from exc
        except ValueError as exc:
            raise HTTPException(409 if conflict else 422, str(exc)) from exc

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
    def list_products(q: str = Query(default="", max_length=160), product_type: str = Query(default="all"), status: str = Query(default="all"), sort: str = Query(default="recent", pattern="^(recent|name|created)$"), pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {"products": translate(lambda: store.list(q, product_type=product_type, status=status, sort=sort))}

    @router.post("", status_code=201)
    def create_product(body: ProductCreateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"product": translate(lambda: service.create(**body.model_dump()))}

    @router.post("/from-project/{project_id}", status_code=201)
    def promote_project(project_id: str, body: PromoteProjectBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if project_store is None:
            raise HTTPException(503, "Project workspace is unavailable")
        project = project_store.get(project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        return {"product": translate(lambda: store.create_from_project(project, product_type=body.product_type, client_name=body.client_name), conflict=True)}

    @router.get("/{product_id}")
    def get_product(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product = product_or_404(product_id)
        return {
            "product": product,
            "components": store.components(product_id),
            "builds": build_lifecycle.list(product_id, store.builds(product_id)),
            "manifest": translate(lambda: manifest_for_product(store, product_id)),
        }

    @router.patch("/{product_id}")
    def update_product(product_id: str, body: ProductUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        product = translate(lambda: store.update(product_id, body.model_dump(exclude_unset=True)))
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
        return {"product": translate(lambda: service.configure_ai(product_id, body.as_policy()))}

    @router.put("/{product_id}/permissions")
    def set_permissions(product_id: str, body: PermissionsBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"product": translate(lambda: service.configure_permissions(product_id, body.permissions))}

    @router.put("/{product_id}/branding")
    def set_branding(product_id: str, body: BrandingBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"product": translate(lambda: service.configure_branding(product_id, body.branding))}

    @router.put("/{product_id}/licensing")
    def set_licensing(product_id: str, body: LicensingBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"product": translate(lambda: service.configure_licensing(product_id, body.licensing))}

    @router.put("/{product_id}/targets")
    def set_targets(product_id: str, body: TargetListBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"product": translate(lambda: service.configure_targets(product_id, [item.model_dump() for item in body.targets]))}

    @router.post("/{product_id}/components", status_code=201)
    def add_component(product_id: str, body: ComponentBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"component": translate(lambda: service.add_component(product_id, **body.model_dump()))}

    @router.delete("/{product_id}/components/{component_id}", status_code=204)
    def remove_component(product_id: str, component_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.remove_component(product_id, component_id):
            raise HTTPException(404, "Component not found")

    @router.get("/{product_id}/manifest")
    def manifest(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {"manifest": translate(lambda: manifest_for_product(store, product_id))}

    @router.post("/{product_id}/versions", status_code=201)
    def create_version(product_id: str, body: VersionBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {"version": translate(lambda: service.freeze_version(product_id, version=body.version, notes=body.notes), conflict=True)}

    @router.get("/{product_id}/builds")
    def list_builds(product_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        product_or_404(product_id)
        return {"builds": build_lifecycle.list(product_id, store.builds(product_id))}

    @router.post("/{product_id}/builds", status_code=202)
    def request_build(product_id: str, body: BuildBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        plan = translate(lambda: service.plan_build(product_id, body.target))
        build = translate(lambda: service.request_build(product_id, body.target, version=body.version))
        return {"plan": plan, "build": build_lifecycle.ensure(build)}

    @router.patch("/{product_id}/builds/{build_id}")
    def update_build(product_id: str, build_id: str, body: BuildUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        product_or_404(product_id)
        value = translate(lambda: build_lifecycle.update(product_id, build_id, **body.model_dump(exclude_unset=True)))
        if not value:
            raise HTTPException(404, "Build not found")
        return {"build": value}

    return router
