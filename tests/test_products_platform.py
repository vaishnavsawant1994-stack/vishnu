from __future__ import annotations

import pytest

from products.builders import build_plan
from products.manifest import ManifestValidationError, manifest_for_product, validate_manifest
from products.policies import normalize_ai_policy, normalize_permissions, permission_state
from products.runtime import ProductRuntimeSpec
from products.store import ProductStore


def _store(tmp_path):
    return ProductStore(tmp_path / "products.sqlite3")


def test_no_ai_product_manifest_and_build_plan(tmp_path):
    store = _store(tmp_path)
    product = store.create(
        name="Invoice Automation",
        product_type="automation",
        ai_mode="disabled",
        targets=["web", "windows", "docker"],
    )
    store.add_component(
        product["id"],
        component_type="workflow",
        component_ref="automation.invoice_ingest",
        name="Invoice ingestion",
        config={"watch_folder": "invoices"},
    )
    manifest = manifest_for_product(store, product["id"])
    spec = ProductRuntimeSpec.load(manifest)

    assert spec.ai_enabled is False
    assert set(spec.targets) == {"web", "windows", "docker"}
    plan = build_plan(spec, "windows")
    assert plan["target"] == "windows"
    assert plan["artifact_kinds"] == ["exe", "msi"]
    assert plan["artifact_ready"] is False


def test_byok_requires_secret_reference_not_raw_api_key(tmp_path):
    store = _store(tmp_path)
    product = store.create(name="Research Employee", product_type="ai_employee", targets=["web"])

    with pytest.raises(ValueError, match="Raw credentials"):
        store.set_ai_policy(product["id"], {"mode": "client_api", "api_key": "sk-do-not-store"})

    policy = normalize_ai_policy(
        {
            "mode": "client_api",
            "provider": "openai",
            "model": "client-selected-model",
            "secret_ref": "vault://client/research/openai",
        }
    )
    store.set_ai_policy(product["id"], policy)
    spec = ProductRuntimeSpec.load(manifest_for_product(store, product["id"]))
    assert spec.ai_mode == "client_api"
    assert spec.manifest["ai_policy"]["secret_ref"].startswith("vault://")


def test_permissions_default_deny():
    permissions = normalize_permissions({"browser.search": "allow", "email.send": "ask"})
    assert permission_state(permissions, "browser.search") == "allow"
    assert permission_state(permissions, "email.send") == "ask"
    assert permission_state(permissions, "payments.execute") == "deny"


def test_hybrid_policy_has_explicit_routes():
    policy = normalize_ai_policy(
        {
            "mode": "hybrid",
            "routes": [
                {
                    "id": "client-primary",
                    "mode": "client_api",
                    "provider": "azure_openai",
                    "secret_ref": "vault://client/acme/azure",
                    "capabilities": ["chat", "summary"],
                },
                {
                    "id": "managed-fallback",
                    "mode": "managed",
                    "capabilities": ["reasoning"],
                },
            ],
            "fallback_route": "managed-fallback",
        }
    )
    assert policy["mode"] == "hybrid"
    assert policy["fallback_route"] == "managed-fallback"
    assert len(policy["routes"]) == 2


def test_manifest_rejects_owner_data_and_credentials():
    base = {
        "schema": "vishnu.product/v1",
        "product_id": "p1",
        "name": "Safe Product",
        "product_type": "custom",
        "version": "1.0.0",
        "components": [],
        "ai_policy": {"mode": "disabled"},
        "permissions": {},
        "targets": [],
        "branding": {},
        "licensing": {},
    }
    validate_manifest(base)

    bad_owner = dict(base, owner_memory={"private": True})
    with pytest.raises(ManifestValidationError, match="Forbidden owner fields"):
        validate_manifest(bad_owner)

    bad_secret = dict(base, branding={"api_key": "secret"})
    with pytest.raises(ManifestValidationError, match="Raw credential"):
        validate_manifest(bad_secret)


def test_builder_rejects_non_enabled_target(tmp_path):
    store = _store(tmp_path)
    product = store.create(name="Web Only", targets=["web"])
    spec = ProductRuntimeSpec.load(manifest_for_product(store, product["id"]))
    with pytest.raises(ValueError, match="not enabled"):
        build_plan(spec, "android")


def test_worker_is_a_first_class_delivery_target(tmp_path):
    store = _store(tmp_path)
    product = store.create(name="Operations Worker", product_type="automation", targets=["worker"])
    spec = ProductRuntimeSpec.load(manifest_for_product(store, product["id"]))
    plan = build_plan(spec, "worker")
    assert plan["target"] == "worker"
    assert plan["adapter"] == "server"
    assert "worker_bundle" in plan["artifact_kinds"]
    assert plan["artifact_ready"] is False
