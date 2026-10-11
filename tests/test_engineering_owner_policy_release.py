from __future__ import annotations

from pathlib import Path

import pytest

from future_intelligence.engineering.contracts import EngineeringBudget, EngineeringSpec, SecurityClass
from future_intelligence.engineering.environment_qualification import HttpQualificationProbe, ReadOnlyHttpQualificationProvider
from future_intelligence.engineering.owner_policy import EngineeringOwnerPolicyStore
from future_intelligence.engineering.production_feedback import ProductionRegressionWorkBridge
from future_intelligence.engineering.release_qualification import ProductionRegression
from future_intelligence.work_orchestration import DurableWorkStore


class Response:
    def __init__(self, status_code=200, body=b"ok", encoding="utf-8"):
        self.status_code = status_code
        self.body = body
        self.encoding = encoding

    def iter_content(self, chunk_size=65536):
        del chunk_size
        yield self.body


class Session:
    def __init__(self):
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        if url.endswith("/health"):
            return Response(200, b'{"ok":true}')
        return Response(200, b"Vishnu")


def make_spec(**overrides):
    values = dict(
        id="eng-owner",
        work_order_id="work-owner",
        attempt_id="attempt-owner",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="bounded change",
        allowed_paths=("src/",),
        budget=EngineeringBudget(max_files=80, max_file_bytes=1_000_000, max_total_bytes=4_000_000, max_repair_cycles=7),
    )
    values.update(overrides)
    return EngineeringSpec(**values)


def test_owner_policy_defaults_to_analyze_and_persists_bounded_limits(tmp_path: Path):
    path = tmp_path / "engineering-policy.json"
    store = EngineeringOwnerPolicyStore(path)
    default = store.snapshot()
    assert default.mode.value == "analyze"
    assert not default.allows_workspace_mutation()
    assert not default.allows_autonomous_execution()
    updated = store.update(
        mode="review_candidate",
        max_files=12,
        max_repair_cycles=2,
        security_level="sensitive",
        browser_depth="release",
        visual_level="semantic",
        physical_device_required=True,
    )
    assert updated.allows_workspace_mutation()
    assert updated.allows_autonomous_execution()
    restored = EngineeringOwnerPolicyStore(path).snapshot()
    assert restored.mode.value == "review_candidate"
    assert restored.max_files == 12
    assert restored.max_repair_cycles == 2
    assert restored.physical_device_required is True
    assert restored.public()["merge_authority"] is False
    assert restored.public()["deploy_authority"] is False


def test_owner_policy_can_only_narrow_engineering_budget_and_security(tmp_path: Path):
    store = EngineeringOwnerPolicyStore(tmp_path / "engineering-policy.json")
    store.update(mode="auto_fix", max_files=10, max_file_bytes=250_000, max_total_bytes=1_000_000, max_repair_cycles=2)
    constrained = store.snapshot().constrain_spec(make_spec())
    assert constrained.budget.max_files == 10
    assert constrained.budget.max_file_bytes == 250_000
    assert constrained.budget.max_total_bytes == 1_000_000
    assert constrained.budget.max_repair_cycles == 2
    with pytest.raises(PermissionError):
        store.snapshot().constrain_spec(make_spec(security_class=SecurityClass.SENSITIVE))


def test_http_environment_qualification_requires_explicit_host_scope():
    with pytest.raises(ValueError, match="allowed host"):
        ReadOnlyHttpQualificationProvider((HttpQualificationProbe("health", "/health"),), allowed_hosts=())


def test_http_environment_qualification_is_read_only_origin_bound_and_bounded():
    session = Session()
    provider = ReadOnlyHttpQualificationProvider(
        (
            HttpQualificationProbe("health", "/health", required_text='"ok":true'),
            HttpQualificationProbe("home", "/iphone/", required_text="Vishnu"),
        ),
        allowed_hosts=("preview.example.test",),
        session=session,
    )
    candidate_revision = "b" * 40
    result = provider.qualify_preview(
        target="https://preview.example.test",
        spec_id="eng-1",
        candidate_revision=candidate_revision,
    )
    assert result.passed
    assert f"binding=spec:eng-1;revision:{candidate_revision}" in result.evidence
    assert all(item[1]["allow_redirects"] is False for item in session.urls)
    assert all(item[0].startswith("https://preview.example.test/") for item in session.urls)
    with pytest.raises(PermissionError):
        provider.smoke_production(target="https://other.example.test", release_revision="abc")


def test_production_regression_creates_idempotent_non_mutating_canonical_work(tmp_path: Path):
    store = DurableWorkStore(tmp_path / "work.sqlite3")
    bridge = ProductionRegressionWorkBridge(store)
    regression = ProductionRegression(
        release_revision="abc123",
        target="https://prod.example.test",
        signal="chat route returns 500",
        evidence=("health-pass", "chat-500"),
        severity="high",
    )
    first = bridge.create(regression)
    second = bridge.create(regression)
    assert first.created is True
    assert second.created is False
    assert first.work_order_id == second.work_order_id
    order = store.get_order(first.work_order_id)
    assert order is not None
    assert order.worker_type == "reviewer"
    assert order.resource_scope.allowed_paths == ()
    assert order.resource_scope.allowed_repositories == ()
    assert order.approval_policy["automatic_mutation"] is False
    assert order.approval_policy["automatic_deploy"] is False
    events = store.list_work_events(order.id)
    assert any(item.event_type == "production.regression_observed" for item in events)
