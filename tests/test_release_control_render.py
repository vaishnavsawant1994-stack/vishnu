from __future__ import annotations

import pytest

from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass
from future_intelligence.release_control.render_provider import (
    RenderProviderError,
    RenderReleaseConfig,
    RenderReleaseProvider,
)


BASE = "a" * 40
CANDIDATE = "b" * 40


def plan():
    return ReleasePlan(
        id="release-render-test",
        work_order_id="work-1",
        attempt_id="attempt-1",
        engineering_spec_id="spec-1",
        repository="owner/repo",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        qualification_digest="d" * 64,
        provider="render",
        target="vishnu-production",
        risk_class=ReleaseRiskClass.LOW,
    )


def config():
    return RenderReleaseConfig(
        api_token="super-secret-render-token",
        preview_service_id="srv-preview",
        production_service_id="srv-production",
        preview_url="https://preview.example.test",
        production_url="https://production.example.test",
        poll_interval_seconds=0.001,
        deployment_timeout_seconds=1,
    )


class FakeRenderProvider(RenderReleaseProvider):
    def __init__(self, *, auto_deploy="off", returned_revision=CANDIDATE):
        super().__init__(config())
        self.auto_deploy = auto_deploy
        self.returned_revision = returned_revision
        self.calls = []

    def _call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and "/deploys/" not in path:
            return {"autoDeployTrigger": self.auto_deploy}
        if method == "POST":
            return {"id": "dep-1", "commit": {"id": self.returned_revision}}
        if method == "GET" and "/deploys/" in path:
            return {"id": "dep-1", "status": "live", "commit": {"id": self.returned_revision}, "trigger": "api"}
        raise AssertionError((method, path, body))


def test_render_provider_refuses_auto_deploy_before_triggering_release():
    provider = FakeRenderProvider(auto_deploy="commit")
    with pytest.raises(RenderProviderError, match="auto-deploy"):
        provider.create_preview(plan())
    assert not any(method == "POST" for method, _path, _body in provider.calls)


def test_render_provider_deploys_exact_candidate_only_when_manual_only():
    provider = FakeRenderProvider(auto_deploy="off")
    deployment = provider.create_preview(plan())
    assert deployment.revision == CANDIDATE
    assert deployment.metadata["auto_deploy_verified_off"] is True
    post = next(call for call in provider.calls if call[0] == "POST")
    assert post[2]["commitId"] == CANDIDATE


def test_render_provider_rejects_revision_drift():
    provider = FakeRenderProvider(returned_revision="c" * 40)
    with pytest.raises(RenderProviderError, match="different revision"):
        provider.create_preview(plan())


def test_render_provider_accepts_provably_equivalent_short_and_full_sha():
    provider = FakeRenderProvider(returned_revision=CANDIDATE[:12])
    deployment = provider.create_preview(plan())
    assert deployment.revision == CANDIDATE


def test_render_token_is_not_exposed_by_config_repr():
    value = config()
    assert "super-secret-render-token" not in repr(value)


def test_preview_and_production_must_be_distinct_services():
    with pytest.raises(ValueError, match="distinct services"):
        RenderReleaseConfig(
            api_token="token",
            preview_service_id="same",
            production_service_id="same",
            preview_url="https://preview.example.test",
            production_url="https://prod.example.test",
        )
