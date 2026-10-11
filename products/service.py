from __future__ import annotations

from .builders import build_plan
from .manifest import manifest_for_product
from .policies import normalize_ai_policy, normalize_permissions
from .runtime import ProductRuntimeSpec
from .store import ProductStore


class ProductService:
    """Owner-side application service for the Our Products workspace."""

    def __init__(self, store: ProductStore):
        self.store = store

    def catalogue(self, *, query="", product_type="all", status="all", sort="recent") -> dict:
        return {
            "summary": self.store.summary(),
            "products": self.store.list(query, product_type=product_type, status=status, sort=sort),
            "activity": self.store.activity(limit=20),
        }

    def create(self, **values):
        return self.store.create(**values)

    def configure_ai(self, product_id: str, policy: dict):
        normalized = normalize_ai_policy(policy)
        product = self.store.set_ai_policy(product_id, normalized)
        if product is None:
            raise KeyError(product_id)
        return product

    def configure_permissions(self, product_id: str, permissions: dict):
        normalized = normalize_permissions(permissions)
        product = self.store.update(product_id, {"permissions": normalized})
        if product is None:
            raise KeyError(product_id)
        return product

    def configure_branding(self, product_id: str, branding: dict):
        if not isinstance(branding, dict):
            raise ValueError("branding must be an object")
        product = self.store.update(product_id, {"branding": branding})
        if product is None:
            raise KeyError(product_id)
        return product

    def configure_licensing(self, product_id: str, licensing: dict):
        if not isinstance(licensing, dict):
            raise ValueError("licensing must be an object")
        product = self.store.update(product_id, {"licensing": licensing})
        if product is None:
            raise KeyError(product_id)
        return product

    def configure_targets(self, product_id: str, targets: list[dict]):
        product = self.store.set_targets(product_id, targets)
        if product is None:
            raise KeyError(product_id)
        return product

    def add_component(self, product_id: str, **component):
        result = self.store.add_component(product_id, **component)
        if result is None:
            raise KeyError(product_id)
        # Validate the full product after every component mutation so a bad
        # component cannot reach a version/build boundary unnoticed.
        manifest_for_product(self.store, product_id)
        return result

    def runtime_spec(self, product_id: str) -> ProductRuntimeSpec:
        return ProductRuntimeSpec.load(manifest_for_product(self.store, product_id))

    def freeze_version(self, product_id: str, *, version: str | None = None, notes=""):
        spec = self.runtime_spec(product_id)
        result = self.store.create_version(product_id, version=version or spec.version, notes=notes)
        if result is None:
            raise KeyError(product_id)
        return result

    def plan_build(self, product_id: str, target: str) -> dict:
        spec = self.runtime_spec(product_id)
        return build_plan(spec, target)

    def request_build(self, product_id: str, target: str, *, version: str | None = None) -> dict:
        # A request is recorded only after the manifest and target plan validate.
        self.plan_build(product_id, target)
        result = self.store.request_build(product_id, target=target, version=version)
        if result is None:
            raise KeyError(product_id)
        return result
