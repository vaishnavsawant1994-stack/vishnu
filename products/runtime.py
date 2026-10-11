from __future__ import annotations

from dataclasses import dataclass

from .manifest import validate_manifest
from .policies import normalize_ai_policy, normalize_permissions, permission_state


@dataclass(frozen=True)
class ProductRuntimeSpec:
    """Validated, immutable view consumed by export/runtime adapters."""

    manifest: dict

    @classmethod
    def load(cls, manifest: dict) -> "ProductRuntimeSpec":
        value = validate_manifest(manifest)
        value["ai_policy"] = normalize_ai_policy(value.get("ai_policy"))
        value["permissions"] = normalize_permissions(value.get("permissions"))
        return cls(value)

    @property
    def product_id(self) -> str:
        return self.manifest["product_id"]

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def ai_mode(self) -> str:
        return self.manifest["ai_policy"]["mode"]

    @property
    def ai_enabled(self) -> bool:
        return self.ai_mode != "disabled"

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(item["target"] for item in self.manifest.get("targets", []) if item.get("enabled", True))

    def permission(self, capability: str) -> str:
        return permission_state(self.manifest.get("permissions", {}), capability)

    def declared_components(self) -> tuple[dict, ...]:
        # A defensive copy is returned so callers cannot mutate the canonical spec.
        return tuple(dict(item) for item in self.manifest.get("components", []))

    def export_descriptor(self) -> dict:
        """Safe, credential-free descriptor builders may embed into artifacts."""
        return {
            "schema": self.manifest["schema"],
            "product_id": self.product_id,
            "name": self.manifest["name"],
            "product_type": self.manifest["product_type"],
            "version": self.version,
            "ai_mode": self.ai_mode,
            "targets": list(self.targets),
            "branding": dict(self.manifest.get("branding", {})),
        }
