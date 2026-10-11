from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from products.capability_catalog import (
    CAPABILITY_TYPES,
    COMMERCIAL_STATES,
    QUALIFICATION_STATES,
    CapabilityCatalog,
)
from products.composer import ProductComposer
from products.models import AI_MODES, PLATFORM_TARGETS, PRODUCT_TYPES
from security.request_context import current_trusted_request
from server.project_autonomy_api import ProjectAutonomyService
from server.project_work_api import ProjectWorkService


class ProductRequestBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    requirement: str = Field(min_length=3, max_length=12000)
    client_name: str = Field(default="", max_length=200)
    product_type: str = Field(default="")
    ai_mode: str = Field(default="disabled")
    targets: list[str] = Field(default_factory=list, max_length=20)
    commercial_state: str | None = None

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, value):
        if value and value not in PRODUCT_TYPES:
            raise ValueError("Unsupported product type")
        return value

    @field_validator("ai_mode")
    @classmethod
    def validate_ai_mode(cls, value):
        if value not in AI_MODES:
            raise ValueError("Unsupported AI mode")
        return value

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, value):
        if any(item not in PLATFORM_TARGETS for item in value):
            raise ValueError("Unsupported platform target")
        return value

    @field_validator("commercial_state")
    @classmethod
    def validate_commercial_state(cls, value):
        if value is not None and value not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        return value


class CapabilityBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capability_type: str = Field(default="custom")
    description: str = Field(default="", max_length=5000)
    source_kind: str = Field(default="manual", max_length=100)
    source_ref: str = Field(min_length=1, max_length=500)
    client_scope: str = Field(default="shared", max_length=200)
    commercial_state: str = Field(default="internal_reusable")
    qualification_state: str = Field(default="available")
    exportable: bool = True
    reusable: bool = True
    ai_required: bool = False
    ai_modes: list[str] = Field(default_factory=list, max_length=10)
    platforms: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=100)
    inputs: list[dict | str] = Field(default_factory=list, max_length=100)
    outputs: list[dict | str] = Field(default_factory=list, max_length=100)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    permissions: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator("capability_type")
    @classmethod
    def validate_type(cls, value):
        if value not in CAPABILITY_TYPES:
            raise ValueError("Unsupported capability type")
        return value

    @field_validator("commercial_state")
    @classmethod
    def validate_commercial(cls, value):
        if value not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        return value

    @field_validator("qualification_state")
    @classmethod
    def validate_qualification(cls, value):
        if value not in QUALIFICATION_STATES:
            raise ValueError("Unsupported qualification state")
        return value

    @field_validator("ai_modes")
    @classmethod
    def validate_ai_modes(cls, value):
        if any(item not in AI_MODES for item in value):
            raise ValueError("Unsupported AI mode")
        return value

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value):
        if any(item not in PLATFORM_TARGETS for item in value):
            raise ValueError("Unsupported platform target")
        return value


class CapabilityClassificationBody(BaseModel):
    commercial_state: str | None = None
    qualification_state: str | None = None
    reusable: bool | None = None
    exportable: bool | None = None
    client_scope: str | None = Field(default=None, max_length=200)

    @field_validator("commercial_state")
    @classmethod
    def validate_commercial(cls, value):
        if value is not None and value not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        return value

    @field_validator("qualification_state")
    @classmethod
    def validate_qualification(cls, value):
        if value is not None and value not in QUALIFICATION_STATES:
            raise ValueError("Unsupported qualification state")
        return value


class ProductClassificationBody(BaseModel):
    commercial_state: str
    notes: str = Field(default="", max_length=2000)

    @field_validator("commercial_state")
    @classmethod
    def validate_state(cls, value):
        if value not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        return value


class PromoteComponentBody(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    component_id: str = Field(min_length=1, max_length=100)
    commercial_state: str = Field(default="internal_reusable")
    generalized: bool = False
    notes: str = Field(default="", max_length=3000)

    @field_validator("commercial_state")
    @classmethod
    def validate_state(cls, value):
        if value not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        return value


def product_composer_router(runtime, catalog: CapabilityCatalog, composer: ProductComposer):
    # Nested below /iphone/api/products: Product Composer is an owner-side factory
    # function, never part of a customer Product Project.
    router = APIRouter(prefix="/composer", tags=["product-composer"])
    registry = runtime["device_registry"]

    def authenticate(device_id: str | None, token: str | None, *, write=False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, "This browser is not trusted or its session was revoked")
        if hasattr(registry, "authorize") and not registry.authorize(device_id, "ai:chat"):
            raise HTTPException(403, "This device is not permitted to use Product Composer")
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(
                401, "A current trusted owner session is required to change Product Composer data"
            )
        return context

    def start_project_work(project_id: str, context, max_steps: int) -> dict:
        if composer.project_store is None:
            raise RuntimeError("Project workspace is unavailable")
        work = ProjectWorkService(runtime, composer.project_store)
        autonomy = ProjectAutonomyService(runtime, composer.project_store)
        snapshot = work.snapshot(project_id)
        plan_created = False
        if snapshot.get("state") != "planned":
            plan = work.create_plan(
                project_id,
                session_id=context.session_id,
            )
            plan_created = bool(plan.get("created"))
        result = autonomy.set(
            project_id,
            "active",
            device_id=context.device_id,
            session_id=context.session_id,
            reauthenticated_at=context.reauthenticated_at,
            advance_now=True,
            max_steps=max_steps,
        )
        advance = result.get("advance") or {}
        return {
            "status": "started",
            "mode": result.get("mode"),
            "plan_created": plan_created,
            "stop_reason": advance.get("stop_reason"),
            "executed_task_ids": list(advance.get("executed_task_ids") or []),
            "execution_authority": result.get("execution_authority"),
        }

    @router.get("/summary")
    def summary(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        return {"summary": composer.summary()}

    @router.post("/sync")
    def sync_catalog(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        counts = catalog.sync_from_runtime(runtime, composer.product_store)
        return {"synced": counts, "summary": catalog.summary()}

    @router.get("/capabilities")
    def list_capabilities(
        q: str = Query(default="", max_length=200),
        capability_type: str = Query(default="all"),
        commercial_state: str = Query(default="all"),
        client_scope: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=300, ge=1, le=1000),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        return {
            "capabilities": catalog.list(
                q,
                capability_type=capability_type,
                commercial_state=commercial_state,
                client_scope=client_scope,
                limit=limit,
            ),
            "summary": catalog.summary(),
        }

    @router.post("/capabilities", status_code=201)
    def create_capability(
        body: CapabilityBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            capability = catalog.upsert(
                **body.model_dump(), preserve_owner_classification=False
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"capability": capability}

    @router.patch("/capabilities/{capability_id}")
    def classify_capability(
        capability_id: str,
        body: CapabilityClassificationBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            capability = catalog.update_classification(
                capability_id, **body.model_dump(exclude_unset=True)
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not capability:
            raise HTTPException(404, "Capability not found")
        return {"capability": capability}

    @router.post("/capabilities/promote", status_code=201)
    def promote_component(
        body: PromoteComponentBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            capability = composer.promote_component(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not capability:
            raise HTTPException(404, "Product component not found")
        return {"capability": capability}

    @router.get("/requests")
    def list_requests(
        status: str = Query(default="all", max_length=80),
        limit: int = Query(default=200, ge=1, le=500),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        return {"requests": composer.list_requests(status=status, limit=limit)}

    @router.post("/requests", status_code=201)
    def create_request(
        body: ProductRequestBody,
        analyze: bool = Query(default=True),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            request = composer.create_request(**body.model_dump())
            if analyze:
                request = composer.analyze(request["id"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"request": request}

    @router.get("/requests/{request_id}")
    def get_request(
        request_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        request = composer.get_request(request_id)
        if not request:
            raise HTTPException(404, "Product request not found")
        return {"request": request, "matches": composer.request_matches(request_id)}

    @router.post("/requests/{request_id}/analyze")
    def analyze_request(
        request_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        request = composer.analyze(request_id)
        if not request:
            raise HTTPException(404, "Product request not found")
        return {"request": request, "matches": composer.request_matches(request_id)}

    @router.post("/requests/{request_id}/product-project", status_code=201)
    def create_product_project(
        request_id: str,
        start_work: bool = Query(default=True),
        max_steps: int = Query(default=10, ge=1, le=20),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        context = authenticate(pa_device, pa_token, write=True)
        try:
            result = composer.create_product_project(request_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not result:
            raise HTTPException(404, "Product request not found")

        work_start = {"status": "not_requested"}
        # Automatic work begins only on the first successful creation. A network
        # retry therefore cannot silently advance more work. Explicit retries use
        # /start-work below and remain governed by P10/P6 approvals and policies.
        if start_work and not result.get("existing"):
            try:
                work_start = start_project_work(result["project"]["id"], context, max_steps)
            except Exception as exc:
                work_start = {
                    "status": "blocked",
                    "detail": str(exc)[:500],
                    "message": (
                        "The Product Project was created safely, but governed automatic work could not start. "
                        "The owner can retry Start Vishnu Work without recreating the product."
                    ),
                }
        elif start_work:
            work_start = {
                "status": "skipped_existing",
                "message": "Existing Product Project was reused; no automatic execution was repeated.",
            }
        return {**result, "work_start": work_start}

    @router.post("/requests/{request_id}/start-work")
    def retry_product_project_work(
        request_id: str,
        max_steps: int = Query(default=10, ge=1, le=20),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        context = authenticate(pa_device, pa_token, write=True)
        request = composer.get_request(request_id)
        if not request:
            raise HTTPException(404, "Product request not found")
        if not request.get("project_id"):
            raise HTTPException(409, "Create the Product Project before starting Vishnu work")
        try:
            return {
                "request_id": request_id,
                "project_id": request["project_id"],
                "work_start": start_project_work(request["project_id"], context, max_steps),
            }
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.get("/products/{product_id}/lineage")
    def lineage(
        product_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        if not composer.product_store.get(product_id):
            raise HTTPException(404, "Product not found")
        return {
            "product_id": product_id,
            "classification": composer.product_classification(product_id),
            "lineage": composer.lineage(product_id),
        }

    @router.put("/products/{product_id}/classification")
    def classify_product(
        product_id: str,
        body: ProductClassificationBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, write=True)
        try:
            classification = composer.set_product_classification(
                product_id, body.commercial_state, body.notes
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not classification:
            raise HTTPException(404, "Product not found")
        return {"classification": classification}

    return router
