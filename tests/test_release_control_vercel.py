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
    def __init__(
        self,
        *,
        candidate_revision=CANDIDATE,
        base_revision=BASE,
        auto_assign=False,
        project_id="prj_test",
        candidate_target="production",
    ):
        super().__init__(config())
        self.candidate_revision = candidate_revision
        self.base_revision = base_revision
        self.auto_assign = auto_assign
        self.project_id = project_id
        self.candidate_target = candidate_target
        self.calls = []

    def _call(self, method, path, body=None, *, query=None):
        self.calls.append((method, path, body, query))
        if method == "GET" and path == "/v9/projects/prj_test":
            return {
                "id": self.project_id,
                "name": "vishnu",
                "autoAssignCustomDomains": self.auto_assign,
            }
        if method == "POST" and path == "/v13/deployments":
            return {
                "id": "dpl_candidate",
                "url": "candidate-staged.vercel.app",
                "readyState": "BUILDING",
                "gitSource": {"sha": self.candidate_revision},
            }
        if method == "GET" and path == "/v13/deployments/dpl_candidate":
            return {
                "id": "dpl_candidate",
                "url": "candidate-staged.vercel.app",
                "readyState": "READY",
                "target": self.candidate_target,
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
                        "target": "production",
                        "gitSource": {"sha": self.base_revision},
                    }
                ]
            }
        if method == "GET" and path == "/v13/deployments/dpl_baseline":
            return {
                "id": "dpl_baseline",
                "url": "baseline.vercel.app",
                "readyState": "READY",
                "target": "production",
                "gitSource": {"sha": self.base_revision},
            }
        if method == "POST" and "/rollback/dpl_baseline" in path:
            return {"ok": True}
        raise AssertionError((method, path, body, query))


def test_vercel_stages_exact_bound_git_sha_with_production_environment():
    provider = FakeVercelProvider()
    deployment = provider.create_preview(plan())
    assert deployment.id == "dpl_candidate"
    assert deployment.revision == CANDIDATE
    assert deployment.url == "https://candidate-staged.vercel.app"
    assert deployment.metadata["staged_production"] is True
    assert deployment.metadata["production_domains_assigned"] is False
    assert deployment.metadata["promotion_rebuilds"] is False

    project = next(item for item in provider.calls if item[0] == "GET" and item[1] == "/v9/projects/prj_test")
    assert project[3] is None
    create = next(item for item in provider.calls if item[0] == "POST" and item[1] == "/v13/deployments")
    assert create[2]["target"] == "production"
    assert create[2]["gitSource"]["sha"] == CANDIDATE
    assert create[2]["gitSource"]["org"] == "owner"
    assert create[2]["gitSource"]["repo"] == "repo"
    assert create[2]["meta"]["vishnuStagedProduction"] == "true"


def test_vercel_staging_fails_closed_when_project_auto_assigns_custom_domains():
    provider = FakeVercelProvider(auto_assign=True)
    with pytest.raises(VercelProviderError, match="autoAssignCustomDomains=false"):
        provider.create_preview(plan())
    assert not any(item[0] == "POST" and item[1] == "/v13/deployments" for item in provider.calls)


def test_vercel_staging_fails_closed_when_project_setting_is_missing():
    class MissingSafetyProvider(FakeVercelProvider):
        def _call(self, method, path, body=None, *, query=None):
            if method == "GET" and path == "/v9/projects/prj_test":
                self.calls.append((method, path, body, query))
                return {"id": "prj_test", "name": "vishnu"}
            return super()._call(method, path, body, query=query)

    provider = MissingSafetyProvider()
    with pytest.raises(VercelProviderError, match="autoAssignCustomDomains=false"):
        provider.create_preview(plan())
    assert not any(item[0] == "POST" and item[1] == "/v13/deployments" for item in provider.calls)


def test_vercel_staging_rejects_project_identity_drift():
    provider = FakeVercelProvider(project_id="prj_other")
    with pytest.raises(VercelProviderError, match="project identity"):
        provider.create_preview(plan())
    assert not any(item[0] == "POST" and item[1] == "/v13/deployments" for item in provider.calls)


def test_vercel_staging_requires_ready_deployment_to_prove_production_target():
    provider = FakeVercelProvider(candidate_target="preview")
    with pytest.raises(VercelProviderError, match="staged Production-target"):
        provider.create_preview(plan())


def test_vercel_promotion_reuses_qualified_staged_production_without_rebuild():
    provider = FakeVercelProvider()
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://candidate-staged.vercel.app",
    )
    deployment = provider.promote(bound)
    assert deployment.id == "dpl_candidate"
    assert deployment.revision == CANDIDATE
    assert deployment.metadata["promotion_rebuilds"] is False
    assert deployment.metadata["promoted_from_staged_production"] is True
    assert sum(1 for item in provider.calls if item[1] == "/v13/deployments") == 0
    assert any(item[0] == "POST" and "/promote/dpl_candidate" in item[1] for item in provider.calls)


def test_vercel_promotion_rejects_legacy_preview_environment_artifact_even_with_same_sha():
    provider = FakeVercelProvider(candidate_target="preview")
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://legacy-preview.vercel.app",
    )
    with pytest.raises(VercelProviderError, match="staged Production-target"):
        provider.promote(bound)
    assert not any(item[0] == "POST" and "/promote/dpl_candidate" in item[1] for item in provider.calls)


def test_vercel_staging_rejects_revision_drift():
    provider = FakeVercelProvider(candidate_revision="c" * 40)
    with pytest.raises(VercelProviderError, match="different revision|drifted"):
        provider.create_preview(plan())


def test_vercel_promotion_requires_persisted_qualified_staged_identity():
    provider = FakeVercelProvider()
    with pytest.raises(VercelProviderError, match="qualified staged"):
        provider.promote(plan())


def test_vercel_rollback_resolves_bound_base_revision_before_switching_traffic():
    provider = FakeVercelProvider()
    bound = plan(
        preview_deployment_id="dpl_candidate",
        preview_url="https://candidate-staged.vercel.app",
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
        preview_url="https://candidate-staged.vercel.app",
        production_deployment_id="dpl_candidate",
        production_url="https://vishnu.example.test",
    )
    current = provider.promote(bound)
    with pytest.raises(VercelProviderError, match="rollback revision"):
        provider.rollback(bound, current)


def test_vercel_token_is_not_exposed_by_config_repr():
    assert "super-secret-vercel-token" not in repr(config())
