from pathlib import Path

import pytest

from future_intelligence.capability_forge import (
    CapabilityForgeService,
    CapabilityForgeStore,
    CapabilityRisk,
    CapabilityRoute,
    GapStatus,
)


class FakeCatalog:
    def __init__(self, rows=None):
        self.rows = {row["id"]: dict(row) for row in (rows or [])}

    def search(self, query, limit=20):
        needle = str(query).lower()
        return [row for row in self.rows.values() if needle in str(row.get("name", "")).lower()][:limit]

    def get(self, capability_id):
        row = self.rows.get(capability_id)
        return dict(row) if row else None


@pytest.fixture()
def store(tmp_path: Path):
    return CapabilityForgeStore(tmp_path / "capability-forge.sqlite3")


def test_detector_requires_explicit_gap_signal(store):
    service = CapabilityForgeService(store)
    assert service.observe_gap("conversation", {"summary": "ordinary request"}) is None
    assert store.list_gaps() == []


def test_gap_detection_is_durable_and_deduplicates_occurrences(store):
    service = CapabilityForgeService(store)
    payload = {
        "capability_gap": True,
        "capability_name": "Supplier price monitor",
        "requested_outcome": "Track supplier prices and report changes",
        "required_operations": ["fetch supplier page", "extract price"],
        "project_id": "project-1",
    }
    first = service.observe_gap("project", payload)
    second = service.observe_gap("project", payload)
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert second.occurrences == 2
    restored = store.get_gap(first.id)
    assert restored is not None
    assert restored.occurrences == 2
    assert "project_id:project-1" in restored.evidence


def test_spec_is_frozen_persisted_and_marks_gap_specified(store):
    service = CapabilityForgeService(store)
    gap = service.observe_gap(
        "workflow",
        {
            "unsupported": True,
            "capability_name": "Read telemetry package",
            "requested_outcome": "Parse a proprietary telemetry file into typed records",
        },
    )
    assert gap is not None
    spec = service.specify(
        gap.id,
        {
            "inputs": {"path": {"type": "string"}},
            "outputs": {"records": {"type": "array"}},
            "filesystem_read": ["/imports"],
            "acceptance_criteria": ["Parses the qualification fixture without data loss."],
        },
    )
    restored = store.get_spec(spec.id)
    assert restored == spec
    assert store.get_gap(gap.id).status is GapStatus.SPECIFIED
    assert restored.acceptance_criteria == ("Parses the qualification fixture without data loss.",)


def test_planner_reuses_exact_catalog_capability_before_generating(store):
    catalog = FakeCatalog([
        {"id": "openapi:prices", "name": "Supplier price monitor", "method": "GET"},
    ])
    service = CapabilityForgeService(store, catalog=catalog)
    proposal = service.propose(
        "conversation",
        {
            "capability_gap": True,
            "capability_name": "Supplier price monitor",
            "requested_outcome": "Read the latest supplier price",
        },
    )
    assert proposal is not None
    _, _, plan = proposal
    assert plan.route is CapabilityRoute.EXISTING
    assert plan.candidate_capability_ids == ("openapi:prices",)


@pytest.mark.parametrize(
    ("signal", "route"),
    [
        ({"external_api": True}, CapabilityRoute.OPENAPI_DISCOVERY),
        ({"mcp": True}, CapabilityRoute.MCP_DISCOVERY),
        ({"requires_core_change": True}, CapabilityRoute.CORE_ENGINEERING),
        ({}, CapabilityRoute.GENERATED),
    ],
)
def test_planner_selects_narrow_governed_route(store, signal, route):
    service = CapabilityForgeService(store)
    payload = {
        "capability_gap": True,
        "capability_name": f"Capability {route.value}",
        "requested_outcome": "Provide a reusable governed ability",
        **signal,
    }
    proposal = service.propose("system", payload)
    assert proposal is not None
    _, _, plan = proposal
    assert plan.route is route
    assert plan.owner_review_required is True


def test_risk_mapper_detects_write_authority_and_secret_expansion(store):
    service = CapabilityForgeService(store)
    proposal = service.propose(
        "execution",
        {
            "error_code": "capability_missing",
            "capability_name": "CRM note writer",
            "requested_outcome": "Create a CRM note",
            "required_operations": ["create note"],
            "external_api": True,
            "network_hosts": ["https://crm.example.com/api"],
            "secret_names": ["crm_api_key"],
            "side_effects": ["write external CRM state"],
        },
    )
    assert proposal is not None
    _, spec, plan = proposal
    assert spec.network_hosts == ("crm.example.com",)
    assert plan.risk is not None
    assert plan.risk.risk is CapabilityRisk.WRITE
    assert plan.risk.authority_expansion is True
    assert plan.risk.owner_review_required is True


def test_f1_service_has_no_activation_authority(store):
    service = CapabilityForgeService(store)
    assert service.activation_allowed is False
    assert not hasattr(service, "activate")
    assert not hasattr(service, "execute")
    assert not hasattr(service, "install")
