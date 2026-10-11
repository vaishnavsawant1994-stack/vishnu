from __future__ import annotations

import re
from copy import deepcopy

from .models import AI_MODES, PLATFORM_TARGETS, PRODUCT_TYPES, ensure_choice


SCHEMA = "vishnu.product/v1"
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_SECRET_NAMES = {
    "api_key",
    "apikey",
    "api-key",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "client_secret",
    "private_key",
}


class ManifestValidationError(ValueError):
    pass


def _walk_for_secrets(value, path="manifest"):
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).strip().lower()
            if lowered in _SECRET_NAMES and child not in (None, ""):
                raise ManifestValidationError(
                    f"Raw credential at {path}.{key}; use a secret_ref managed by the runtime vault"
                )
            _walk_for_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_secrets(child, f"{path}[{index}]")


def validate_manifest(value: dict) -> dict:
    """Validate and return a defensive copy of a distributable product manifest.

    The manifest is intentionally an allow-list. It contains product metadata and
    references/configuration for declared components, never owner state or raw
    credentials. Platform builders consume only a manifest that passes here.
    """
    if not isinstance(value, dict):
        raise ManifestValidationError("Product manifest must be a JSON object")
    manifest = deepcopy(value)
    if manifest.get("schema") != SCHEMA:
        raise ManifestValidationError(f"Unsupported product manifest schema: {manifest.get('schema')!r}")

    product_id = str(manifest.get("product_id") or "").strip()
    name = str(manifest.get("name") or "").strip()
    version = str(manifest.get("version") or "").strip()
    if not product_id:
        raise ManifestValidationError("product_id is required")
    if not name:
        raise ManifestValidationError("name is required")
    ensure_choice(manifest.get("product_type"), PRODUCT_TYPES, "product type")
    if not _VERSION.match(version):
        raise ManifestValidationError("version must use semantic version form, for example 1.2.0")

    components = manifest.get("components", [])
    if not isinstance(components, list):
        raise ManifestValidationError("components must be a list")
    seen_components = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ManifestValidationError(f"components[{index}] must be an object")
        component_id = str(component.get("id") or "").strip()
        component_type = str(component.get("component_type") or "").strip()
        component_name = str(component.get("name") or "").strip()
        if not component_id or not component_type or not component_name:
            raise ManifestValidationError(
                f"components[{index}] requires id, component_type and name"
            )
        if component_id in seen_components:
            raise ManifestValidationError(f"Duplicate component id: {component_id}")
        seen_components.add(component_id)

    policy = manifest.get("ai_policy") or {"mode": "disabled"}
    if not isinstance(policy, dict):
        raise ManifestValidationError("ai_policy must be an object")
    mode = ensure_choice(policy.get("mode", "disabled"), AI_MODES, "AI mode")
    policy["mode"] = mode
    manifest["ai_policy"] = policy

    targets = manifest.get("targets", [])
    if not isinstance(targets, list):
        raise ManifestValidationError("targets must be a list")
    seen_targets = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ManifestValidationError(f"targets[{index}] must be an object")
        target_name = ensure_choice(target.get("target"), PLATFORM_TARGETS, "platform target")
        if target_name in seen_targets:
            raise ManifestValidationError(f"Duplicate platform target: {target_name}")
        seen_targets.add(target_name)
        target["target"] = target_name

    for mapping_name in ("permissions", "branding", "licensing"):
        mapping = manifest.get(mapping_name) or {}
        if not isinstance(mapping, dict):
            raise ManifestValidationError(f"{mapping_name} must be an object")
        manifest[mapping_name] = mapping

    # Explicitly forbid master-system data from being smuggled into a manifest.
    forbidden = {
        "owner_memory",
        "owner_conversations",
        "owner_credentials",
        "signing_private_key",
        "master_api_keys",
        "other_clients",
    }
    present = sorted(forbidden.intersection(manifest))
    if present:
        raise ManifestValidationError(f"Forbidden owner fields in product manifest: {', '.join(present)}")

    _walk_for_secrets(manifest)
    return manifest


def manifest_for_product(store, product_id: str) -> dict:
    manifest = store.manifest(product_id)
    if manifest is None:
        raise KeyError(product_id)
    return validate_manifest(manifest)
