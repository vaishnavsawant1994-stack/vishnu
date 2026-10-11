from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from products.store import ProductStore


def make_store():
    directory = tempfile.TemporaryDirectory()
    store = ProductStore(Path(directory.name) / "products.sqlite3")
    return directory, store


def test_product_lifecycle_manifest_and_summary():
    directory, store = make_store()
    try:
        product = store.create(
            name="ACME Sales Employee",
            product_type="ai_employee",
            description="Researches and qualifies leads.",
            client_name="ACME Ltd",
            ai_mode="hybrid",
            targets=["web", "android", "windows"],
        )
        assert product["name"] == "ACME Sales Employee"
        assert {item["target"] for item in product["targets"]} == {"web", "android", "windows"}
        assert store.summary() == {
            "total": 1,
            "development": 1,
            "ready": 0,
            "live": 0,
            "clients": 1,
            "needs_attention": 0,
        }

        component = store.add_component(
            product["id"],
            component_type="agent",
            name="Lead Research Agent",
            component_ref="agent:lead-research",
        )
        assert component["name"] == "Lead Research Agent"

        updated = store.set_ai_policy(
            product["id"],
            {
                "mode": "hybrid",
                "provider": "openai",
                "model": "client-selected",
                "secret_ref": "vault://clients/acme/openai",
                "allow_fallback": True,
            },
        )
        assert updated["ai_policy"]["secret_ref"].startswith("vault://")

        manifest = store.manifest(product["id"])
        assert manifest["schema"] == "vishnu.product/v1"
        assert manifest["client"]["display_name"] == "ACME Ltd"
        assert manifest["components"][0]["component_ref"] == "agent:lead-research"
        assert "api_key" not in str(manifest).lower()

        frozen = store.create_version(product["id"], version="0.1.0", notes="Initial product contract")
        assert frozen["version"] == "0.1.0"
        with pytest.raises(ValueError, match="already exists"):
            store.create_version(product["id"], version="0.1.0")
    finally:
        directory.cleanup()


def test_product_definitions_reject_raw_secrets():
    directory, store = make_store()
    try:
        product = store.create(name="Secure Product", product_type="custom")
        with pytest.raises(ValueError, match="Raw credentials"):
            store.set_ai_policy(product["id"], {"mode": "client_api", "api_key": "sk-do-not-store"})
        with pytest.raises(ValueError, match="Raw credentials"):
            store.update(product["id"], {"branding": {"nested": {"password": "do-not-store"}}})
        with pytest.raises(ValueError, match="Raw credentials"):
            store.set_targets(product["id"], [{"target": "web", "enabled": True, "config": {"token": "do-not-store"}}])
    finally:
        directory.cleanup()


def test_build_request_does_not_claim_artifact_exists():
    directory, store = make_store()
    try:
        product = store.create(name="Android Worker", product_type="automation", targets=["android"])
        build = store.request_build(product["id"], target="android")
        assert build["status"] == "requested"
        assert build["artifact_name"] is None
        assert build["metadata"]["artifact_ready"] is False
        assert build["metadata"]["builder_state"] == "adapter_pending"
        with pytest.raises(ValueError, match="not enabled"):
            store.request_build(product["id"], target="ios")
    finally:
        directory.cleanup()


def test_project_promotion_is_linked_and_idempotent():
    directory, store = make_store()
    try:
        project = {"id": "project-123", "name": "Recruitment System", "description": "Reusable recruiter."}
        product = store.create_from_project(project, product_type="business_system", client_name="ABC Recruitment")
        assert product["source_project_id"] == "project-123"
        assert product["client_name"] == "ABC Recruitment"
        with pytest.raises(ValueError, match="already been promoted"):
            store.create_from_project(project, product_type="business_system")
    finally:
        directory.cleanup()
