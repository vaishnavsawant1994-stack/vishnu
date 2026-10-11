from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from products.capability_catalog import CapabilityCatalog
from products.composer import ProductComposer
from products.store import ProductStore
from projects.store import ProjectStore


def make_system():
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    products = ProductStore(root / "products.sqlite3")
    projects = ProjectStore(root / "projects.sqlite3")
    catalog = CapabilityCatalog(root / "products.sqlite3")
    composer = ProductComposer(root / "products.sqlite3", catalog, products, projects)
    return directory, products, projects, catalog, composer


class FakeWorkerRegistry:
    def all(self):
        return [
            SimpleNamespace(
                id="researcher",
                name="Researcher",
                description="Researches sources and gathers evidence",
                supported_capabilities=("research", "browser", "knowledge"),
            ),
            SimpleNamespace(
                id="coder",
                name="Coder",
                description="Implements and tests software changes",
                supported_capabilities=("coding", "files", "review"),
            ),
            SimpleNamespace(
                id="tool",
                name="Generic tool wrapper",
                description="Not a reusable agent profile",
                supported_capabilities=("tool",),
            ),
        ]


def test_catalog_sync_discovers_worker_agents_without_exporting_vishnu_runtime():
    directory, products, _, catalog, _ = make_system()
    try:
        runtime = {
            "advanced_autonomy": SimpleNamespace(_worker_registry=FakeWorkerRegistry())
        }
        counts = catalog.sync_from_runtime(runtime, products)
        assert counts["agents"] == 2
        agents = catalog.list(capability_type="agent")
        assert {row["source_ref"] for row in agents} == {"researcher", "coder"}
        assert all(row["metadata"]["master_runtime_bundled"] is False for row in agents)
    finally:
        directory.cleanup()


def test_internal_request_cannot_match_any_client_private_capability():
    directory, _, _, catalog, composer = make_system()
    try:
        private = catalog.upsert(
            name="PrivateCo Recruiting Brain",
            capability_type="agent",
            source_kind="manual",
            source_ref="privateco-recruiting",
            description="Recruiting candidate resume screening and interview ranking",
            client_scope="PrivateCo",
            commercial_state="client_specific",
            reusable=True,
            exportable=True,
            preserve_owner_classification=False,
        )
        request = composer.create_request(
            title="Internal Recruiting Helper",
            requirement="Screen recruiting candidates, resumes and rank interviews",
        )
        analyzed = composer.analyze(request["id"])
        matched = {
            item["capability"]["id"]
            for item in analyzed["blueprint"]["requirements"]
            if item.get("capability")
        }
        assert private["id"] not in matched
    finally:
        directory.cleanup()


def test_generic_classification_cannot_move_client_capability_to_shared_scope():
    directory, _, _, catalog, _ = make_system()
    try:
        private = catalog.upsert(
            name="Client Rules",
            capability_type="business_logic",
            source_kind="manual",
            source_ref="client-rules",
            client_scope="Client A",
            commercial_state="client_specific",
            preserve_owner_classification=False,
        )
        with pytest.raises(ValueError, match="explicit generalized"):
            catalog.update_classification(private["id"], client_scope="shared")
        unchanged = catalog.get(private["id"])
        assert unchanged["client_scope"] == "Client A"
    finally:
        directory.cleanup()


def test_client_generalization_requires_documented_private_data_removal():
    directory, products, _, _, composer = make_system()
    try:
        product = products.create(
            name="Client Revenue System",
            product_type="business_system",
            client_name="Client Secret Co",
        )
        component = products.add_component(
            product["id"],
            component_type="workflow",
            name="Client Secret Co Revenue Rules",
            component_ref="private-revenue-rules",
        )
        with pytest.raises(ValueError, match="requires notes"):
            composer.promote_component(
                product_id=product["id"],
                component_id=component["id"],
                commercial_state="internal_reusable",
                generalized=True,
            )
        promoted = composer.promote_component(
            product_id=product["id"],
            component_id=component["id"],
            commercial_state="internal_reusable",
            generalized=True,
            notes="Generalized calculation flow; removed client pricing, customer data, thresholds and private rules.",
        )
        assert promoted["client_scope"] == "shared"
        assert "Client Secret Co" not in promoted["name"]
        assert promoted["metadata"]["client_private_source"] is True
    finally:
        directory.cleanup()


def test_product_project_retry_does_not_duplicate_project_product_components_or_lineage():
    directory, products, projects, catalog, composer = make_system()
    try:
        capability = catalog.upsert(
            name="Company Research Agent",
            capability_type="agent",
            source_kind="worker_profile",
            source_ref="company-research",
            description="Research companies and decision makers",
            qualification_state="qualified",
            preserve_owner_classification=False,
        )
        request = composer.create_request(
            title="Client Research Employee",
            requirement="Research companies and decision makers and build a new specialist territory model",
            client_name="Client B",
            product_type="ai_employee",
            targets=["web"],
        )
        composer.analyze(request["id"])
        first = composer.create_product_project(request["id"])
        second = composer.create_product_project(request["id"])

        assert first["project"]["id"] == second["project"]["id"]
        assert first["product"]["id"] == second["product"]["id"]
        assert second["existing"] is True
        assert len(projects.list()) == 1
        assert len(products.list()) == 1

        product_id = first["product"]["id"]
        components = products.components(product_id)
        matching = [
            row for row in components
            if (row.get("config") or {}).get("capability_id") == capability["id"]
        ]
        assert len(matching) <= 1
        lineage = composer.lineage(product_id)
        keys = {
            (row["source_kind"], row["source_ref"], row["relation"])
            for row in lineage
        }
        assert len(keys) == len(lineage)
        assert ("product_request", request["id"], "created_from") in keys
        assert ("project", first["project"]["id"], "implemented_by") in keys
    finally:
        directory.cleanup()
