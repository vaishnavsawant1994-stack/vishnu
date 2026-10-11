from __future__ import annotations

import pytest

from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass
from future_intelligence.release_control.vercel_provider import (
    VercelProviderError,
    VercelReleaseConfig,
    VercelReleaseProvider,
)


BASE = "a" * 40
CANDIDATE = "b" * 40


def plan(**changes):
    value = ReleasePlan(
        id="release-vercel-test",
        work_order_id="work-1",
        attempt_id="attempt-1",
        engineering_spec_id="spec-1",
        repository="owner/repo",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        qualification_digest="d" * 64,
        provider="vercel",
        target="vishnu-production",
        risk_class=ReleaseRiskClass.LOW,
    )
    return value.with_update(**changes) if changes else value


def config():
    return VercelReleaseConfig(
        api_token="super-secret-vercel-token",
        project_id="prj_test",
        project_name="vishnu",
        github_org="owner",
        github_repo="repo",
        git_ref="main",
        production_url="https://vishnu.example.test",
        team_id="team_test",
        poll_interval_seconds=0.001,
        deployment_timeout_seconds=1,
    )


class FakeVercelProvider(VercelReleaseProvider):
    def __init__(self, *, candidate_revision=CANDIDATE, base_revision=BASE):
        super().__init__(config())
        self.candidate_revision = candidate_revision
        self.base_revision = base_revision
        self.calls = []

    def _call(self, method, path, body=None, *, query=None):
        self.calls.append((method, path, body, query))
        if method == "POST" and path == "/v13/deployments":
            return {
                "id": "dpl_candidate",
                "url": "candidate-preview.vercel.app",
                "readyState": "BUILDING",
                "gitSource": {"sha": self.candidate_revision},
            }
        if method == "GET" and path == "/v13/deployments/dpl_candidate":
            return {
                "id": "dpl_candidate",
                "url": "candidate-preview.vercel.app",
                "readyState": "READY",
                "gitSource": {"sha": self.candidate_revision},
            }
        if method == "POST" and "/promote/dpl_candidate" in path:
            return {"ok": True}
        if method == "GET" and path == "/v6/deployments":
            return {
                "deployments": [
                    {
                        "id": "dpl_baseline",
                        "url": "baseline.vercel.app",
                        "readyState": "READY",
                        "gitSource": {"sha": self.base_revision},
                    }
                ]
            }
        if method == "GET" and path == "/v13/deployments/dpl_baseline":
            return {
                "id": "dpl_baseline",
                "url": "baseline.vercel.app",
                "readyState": "READY",
                "gitSource": {"sha": self.base_revision},
            }
        if method == "POST" and "/rollback/dpl_baseline" in path:
            return {"ok": True}
        raise AssertionError((method, path, body, query))


def test_vercel_preview_builds_exact_bound_git_sha():
    provider = FakeVercelProvider()
    deployment = provider.create_preview(plan())
    assert deployment.id == "dpl_candidate"
    assert deployment.revision == CANDIDATE
    assert deployment.url == "https://candidate-preview.vercel.app"
    create = next(item for item in provider.calls if item[0] == "POST" and item[1] == "/v13/deployments")
    assert create[2]["gitSource"]["sha"] == CANDIDATE
    assert create[2]["gitSource"]["org"] == "owner"
    assert create[2]["gitSource"]["repo"] == "repo"
    assert create[2].get("target") is None


def test_vercel_promotion_reuses_qualified_preview_without_rebuild():
    provider = FakeVercelProvider()
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://candidate-preview.vercel.app",
    )
    deployment = provider.promote(bound)
    assert deployment.id == "dpl_candidate"
    assert deployment.revision == CANDIDATE
    assert deployment.metadata["promotion_rebuilds"] is False
    assert deployment.metadata["promoted_from_preview"] is True
    assert sum(1 for item in provider.calls if item[1] == "/v13/deployments") == 0
    assert any(item[0] == "POST" and "/promote/dpl_candidate" in item[1] for item in provider.calls)


def test_vercel_preview_rejects_revision_drift():
    provider = FakeVercelProvider(candidate_revision="c" * 40)
    with pytest.raises(VercelProviderError, match="different revision|drifted"):
        provider.create_preview(plan())


def test_vercel_promotion_requires_persisted_qualified_preview_identity():
    provider = FakeVercelProvider()
    with pytest.raises(VercelProviderError, match="qualified preview"):
        provider.promote(plan())


def test_vercel_rollback_resolves_bound_base_revision_before_switching_traffic():
    provider = FakeVercelProvider()
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://candidate-preview.vercel.app",
        production_deployment_id="dpl_candidate",
        production_url="https://vishnu.example.test",
    )
    current = provider.promote(bound)
    provider.calls.clear()
    restored = provider.rollback(bound, current)
    assert restored.id == "dpl_baseline"
    assert restored.revision == BASE
    history = next(item for item in provider.calls if item[1] == "/v6/deployments")
    assert history[3]["sha"] == BASE
    assert any(item[0] == "POST" and "/rollback/dpl_baseline" in item[1] for item in provider.calls)


def test_vercel_rollback_refuses_history_that_does_not_prove_base_revision():
    provider = FakeVercelProvider(base_revision="c" * 40)
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://candidate-preview.vercel.app",
        production_deployment_id="dpl_candidate",
        production_url="https://vishnu.example.test",
    )
    current = provider.promote(bound)
    with pytest.raises(VercelProviderError, match="rollback revision"):
        provider.rollback(bound, current)


def test_vercel_token_is_not_exposed_by_config_repr():
    assert "super-secret-vercel-token" not in repr(config())
