from __future__ import annotations

import json

from future_intelligence.engineering.contracts import EngineeringSpec, SecurityClass
from future_intelligence.engineering.repository_intelligence import RepositoryGraph, RepositoryNode
from future_intelligence.engineering.specialists import (
    ENGINEERING_SPECIALISTS,
    EngineeringSpecialistSelector,
    GovernedEngineeringSpecialistConsultations,
)
from models.contracts import ModelResponse


class SpecialistModels:
    def __init__(self):
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        return ModelResponse(
            request_id=request.request_id,
            provider_id="specialist-provider",
            model_id="specialist-model",
            content=json.dumps({
                "summary": "bounded specialist advice",
                "findings": ["preserve canonical authority"],
                "suspected_files": ["pwa/index.html"],
                "required_tests": ["tests/engineering_ui/cross_browser_qualification.mjs"],
                "risks": ["responsive regression"],
            }),
        )


def test_engineering_specialist_profiles_are_existing_worker_contracts_and_proposal_only():
    ids = {profile.id for profile in ENGINEERING_SPECIALISTS}
    assert {
        "engineering-architect",
        "engineering-frontend",
        "engineering-backend",
        "engineering-database",
        "engineering-mobile",
        "engineering-ui-qa",
        "engineering-visual-reviewer",
        "engineering-accessibility-reviewer",
        "engineering-security-reviewer",
        "engineering-performance-reviewer",
        "engineering-code-reviewer",
        "engineering-release-reviewer",
    } <= ids
    assert all(profile.to_dict()["authority"] == "proposal_only" for profile in ENGINEERING_SPECIALISTS)


def test_specialist_selector_uses_engineering_spec_surfaces_and_risk_without_new_authority():
    spec = EngineeringSpec(
        id="eng-specialists",
        work_order_id="work-specialists",
        attempt_id="attempt-specialists",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="change mobile project UI and API",
        allowed_paths=("pwa/", "server/"),
        affected_surfaces=("ui", "api", "mobile"),
        schema_impacts=("projects table",),
        ui_required=True,
        accessibility_required=True,
        visual_review_required=True,
        security_class=SecurityClass.SENSITIVE,
        metadata={"performance_required": True},
    )
    roles = {profile.id for profile in EngineeringSpecialistSelector().select(spec, max_roles=8)}
    assert "engineering-architect" in roles
    assert "engineering-frontend" in roles
    assert "engineering-ui-qa" in roles
    assert "engineering-backend" in roles
    assert "engineering-database" in roles
    assert "engineering-mobile" in roles
    assert "engineering-security-reviewer" in roles


def test_specialist_consultations_use_governed_model_requests_bound_to_same_work_and_budget():
    models = SpecialistModels()
    spec = EngineeringSpec(
        id="eng-specialist-routing",
        work_order_id="work-specialist-routing",
        attempt_id="attempt-specialist-routing",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="review UI change",
        allowed_paths=("pwa/",),
        affected_surfaces=("ui",),
        ui_required=True,
        metadata={"project_id": "project-1", "max_model_cost_per_work": 3.5},
    )
    graph = RepositoryGraph(
        revision=spec.base_revision,
        fingerprint="graph-fingerprint",
        nodes=(RepositoryNode("file:pwa/index.html", "file", "pwa/index.html", "index.html"),),
        edges=(),
    )
    advice = GovernedEngineeringSpecialistConsultations(models, max_roles=3).consult(spec=spec, graph=graph)
    assert advice
    assert len(models.requests) == len(advice) <= 3
    assert all(request.task_id == spec.work_order_id for request in models.requests)
    assert all(request.execution_id == f"engineering:{spec.attempt_id}" for request in models.requests)
    assert all(request.max_cost == 3.5 for request in models.requests)
    assert all(request.metadata["model_output_authority"] is False for request in models.requests)
    assert all(request.agent_id.startswith("engineering-") for request in models.requests)
