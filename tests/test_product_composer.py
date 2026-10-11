from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from products.capability_catalog import CapabilityCatalog
from products.composer import ProductComposer
from products.store import ProductStore
from projects.store import ProjectStore


class FakeRisk:
    name = "READ_ONLY"


class FakeTool:
    def __init__(self, name, description, capability=""):
        self.name = name
        self.description = description
        self.capability = capability
        self.connector_id = None
        self.prohibited = False
        self.verification_required = False
        self.risk = FakeRisk()


class FakeTools:
    def all(self):
        return [
            FakeTool("lead_research", "Research companies, prospects and decision makers", "research"),
            FakeTool("gmail_send", "Send personalized email outreach", "email"),
            FakeTool("crm_update", "Update CRM records and sales pipeline", "crm"),
        ]


class FakeAutomations:
    def list(self):
        return [{"id": "auto-weekly", "title": "Weekly sales report", "prompt": "Prepare a weekly sales report", "enabled": 1}]

    def workflows(self):
        return [
            {
                "id": "wf-outreach",
                "title": "Lead outreach workflow",
                "enabled": 1,
                "paused": 0,
                "steps": [{"kind": "prompt"}, {"kind": "prompt"}],
            }
        ]


class FakeIntegrations:
    def list(self):
        return [{"id": "hubspot", "name": "HubSpot CRM", "description": "CRM integration"}]


def make_system():
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    product_store = ProductStore(root / "products.sqlite3")
    project_store = ProjectStore(root / "projects.sqlite3")
    catalog = CapabilityCatalog(root / "products.sqlite3")
    composer = ProductComposer(root / "products.sqlite3", catalog, product_store, project_store)
    return directory, product_store, project_store, catalog, composer


def test_catalog_sync_discovers_existing_vishnu_capabilities_without_secrets():
    directory, product_store, _, catalog, _ = make_system()
    try:
        product_store.create(
            name="Internal Sales Assistant",
            product_type="ai_employee",
            description="Internal sales helper",
            ai_mode="hybrid",
            targets=["web", "windows"],
        )
        counts = catalog.sync_from_runtime(
            {"tools": FakeTools(), "automations": FakeAutomations(), "integrations": FakeIntegrations()},
            product_store,
        )
        assert counts["tools"] == 3
        assert counts["automations"] == 1
        assert counts["workflows"] == 1
        assert counts["integrations"] == 1
        assert counts["products"] == 1
        rows = catalog.list(limit=100)
        names = {row["name"] for row in rows}
        assert "lead_research" in names
        assert "HubSpot CRM" in names
        assert "Internal Sales Assistant" in names
        assert all("api_key" not in str(row).lower() for row in rows)
    finally:
        directory.cleanup()


def test_client_private_capabilities_do_not_match_other_clients():
    directory, _, _, catalog, composer = make_system()
    try:
        catalog.upsert(
            name="ACME Private Lead Model",
            capability_type="business_logic",
            source_kind="manual",
            source_ref="acme-private",
            description="Lead scoring for private ACME rules",
            client_scope="ACME Ltd",
            commercial_state="client_specific",
            reusable=True,
            exportable=True,
            preserve_owner_classification=False,
        )
        other = composer.create_request(
            title="XYZ Lead Scoring",
            requirement="Score and qualify sales leads using lead scoring rules",
            client_name="XYZ Ltd",
            commercial_state="client_specific",
        )
        other = composer.analyze(other["id"])
        matched_ids = {
            item.get("capability", {}).get("id")
            for item in other["blueprint"]["requirements"]
            if item.get("capability")
        }
        private_id = catalog.list(client_scope="ACME Ltd")[0]["id"]
        assert private_id not in matched_ids

        same = composer.create_request(
            title="ACME Lead Upgrade",
            requirement="Improve lead scoring and qualify sales leads",
            client_name="ACME Ltd",
            commercial_state="client_specific",
        )
        same = composer.analyze(same["id"])
        same_ids = {
            item.get("capability", {}).get("id")
            for item in same["blueprint"]["requirements"]
            if item.get("capability")
        }
        assert private_id in same_ids
    finally:
        directory.cleanup()


def test_request_analysis_reuses_extends_and_creates_missing_capabilities():
    directory, product_store, _, catalog, composer = make_system()
    try:
        catalog.sync_from_runtime(
            {"tools": FakeTools(), "automations": FakeAutomations(), "integrations": FakeIntegrations()},
            product_store,
        )
        request = composer.create_request(
            title="Real Estate Sales Employee",
            requirement=(
                "I want an AI employee that researches leads and decision makers, sends personalized email outreach, "
                "updates HubSpot CRM, prepares weekly reports and performs real estate property valuation."
            ),
            client_name="Example Realty",
            product_type="ai_employee",
            ai_mode="client_api",
            targets=["web", "windows"],
            commercial_state="client_specific",
        )
        analyzed = composer.analyze(request["id"])
        blueprint = analyzed["blueprint"]
        assert blueprint["recommended_product_type"] == "ai_employee"
        assert blueprint["targets"] == ["web", "windows"]
        assert blueprint["reuse_count"] + blueprint["extend_count"] >= 1
        assert blueprint["create_count"] >= 1
        assert any("property valuation" in item["requirement"].lower() for item in blueprint["requirements"])
        assert blueprint["coverage_percent"] < 100
    finally:
        directory.cleanup()


def test_product_project_creation_bridges_missing_work_into_projects_and_tracks_lineage():
    directory, product_store, project_store, catalog, composer = make_system()
    try:
        reusable = catalog.upsert(
            name="Lead Research Agent",
            capability_type="agent",
            source_kind="agent",
            source_ref="lead-research-agent",
            description="Research companies, leads and decision makers",
            commercial_state="internal_reusable",
            qualification_state="qualified",
            preserve_owner_classification=False,
        )
        request = composer.create_request(
            title="Client Prospecting Employee",
            requirement="Research sales leads and decision makers, then perform a proprietary territory optimization model",
            client_name="Client One",
            product_type="ai_employee",
            ai_mode="hybrid",
            targets=["web", "android"],
            commercial_state="client_specific",
        )
        analyzed = composer.analyze(request["id"])
        assert analyzed["blueprint"]["missing_work"]

        result = composer.create_product_project(request["id"])
        product = result["product"]
        project = result["project"]
        assert result["existing"] is False
        assert product["source_project_id"] == project["id"]
        assert product["client_name"] == "Client One"
        assert product["ai_mode"] == "hybrid"
        assert {target["target"] for target in product["targets"] if target["enabled"]} == {"web", "android"}
        assert project["goal"].startswith("Research sales leads")
        assert any(task["owner"] == "vishnu" for task in project["tasks"])
        assert any("qualification" in task["title"].lower() for task in project["tasks"])
        assert any("release" in task["title"].lower() for task in project["tasks"])
        assert composer.product_classification(product["id"])["commercial_state"] == "client_specific"
        lineage = composer.lineage(product["id"])
        assert any(item["source_kind"] == "product_request" for item in lineage)
        assert any(item["source_kind"] == "project" for item in lineage)
        if any(item.get("capability") and item["capability"]["id"] == reusable["id"] for item in analyzed["blueprint"]["requirements"]):
            assert any(item["source_kind"] == "capability" and item["source_ref"] == reusable["id"] for item in lineage)

        repeated = composer.create_product_project(request["id"])
        assert repeated["existing"] is True
        assert repeated["product"]["id"] == product["id"]
    finally:
        directory.cleanup()


def test_client_component_requires_explicit_generalization_before_shared_reuse():
    directory, product_store, _, catalog, composer = make_system()
    try:
        product = product_store.create(
            name="Client HR System",
            product_type="business_system",
            client_name="Private Co",
            targets=["web"],
        )
        component = product_store.add_component(
            product["id"], component_type="workflow", name="Candidate Screening Workflow", component_ref="client-screening"
        )
        scoped = composer.promote_component(
            product_id=product["id"], component_id=component["id"], commercial_state="client_specific", generalized=False
        )
        assert scoped["client_scope"] == "Private Co"

        shared = composer.promote_component(
            product_id=product["id"], component_id=component["id"], commercial_state="internal_reusable", generalized=True,
            notes="Generalized screening sequence with all client criteria removed.",
        )
        assert shared["client_scope"] == "shared"
        assert shared["reusable"] is True
        assert shared["metadata"]["generalized"] is True
    finally:
        directory.cleanup()
