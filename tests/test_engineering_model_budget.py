from __future__ import annotations

import json

from future_intelligence.engineering.contracts import EngineeringSpec, SecurityClass
from future_intelligence.engineering.model_json import governed_engineering_json
from models.contracts import ModelResponse


class RequestModels:
    def __init__(self):
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        return ModelResponse(
            request_id=request.request_id,
            provider_id="test-private",
            model_id="test-model",
            content=json.dumps({"ok": True}),
        )


def test_engineering_json_uses_typed_model_request_bound_to_work_attempt_and_cost_ceiling():
    models = RequestModels()
    spec = EngineeringSpec(
        id="eng-budget",
        work_order_id="work-budget",
        attempt_id="attempt-budget",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="bounded model call",
        allowed_paths=("src/",),
        security_class=SecurityClass.SENSITIVE,
        metadata={"project_id": "project-budget", "max_model_cost_per_work": 1.25},
    )
    payload = governed_engineering_json(
        models,
        spec=spec,
        prompt="return JSON",
        system="JSON only",
        role="vishnu-software-engineer",
        sensitivity="sensitive",
    )
    assert payload == {"ok": True}
    assert len(models.requests) == 1
    request = models.requests[0]
    assert request.task_id == "work-budget"
    assert request.execution_id == "engineering:attempt-budget"
    assert request.project_id == "project-budget"
    assert request.agent_id == "vishnu-software-engineer"
    assert request.routing_policy == "coding"
    assert request.max_cost == 1.25
    assert request.sensitivity == "sensitive"
    assert request.metadata["model_output_authority"] is False


def test_engineering_reviewer_uses_review_policy_on_same_work_budget_scope():
    models = RequestModels()
    spec = EngineeringSpec(
        id="eng-review-budget",
        work_order_id="work-budget",
        attempt_id="attempt-budget",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="bounded review",
        allowed_paths=("src/",),
        metadata={"max_model_cost_per_work": 2.0},
    )
    governed_engineering_json(
        models,
        spec=spec,
        prompt="review",
        system="JSON only",
        role="independent-engineering-reviewer",
    )
    request = models.requests[0]
    assert request.task_id == "work-budget"
    assert request.routing_policy == "review"
    assert request.max_cost == 2.0
