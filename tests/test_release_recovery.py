from __future__ import annotations

from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass, ReleaseStatus
from future_intelligence.release_control.controller import GovernedReleaseController
from future_intelligence.release_control.policy import ReleaseAutonomyMode, ReleaseOwnerPolicy
from future_intelligence.release_control.policy_store import ReleasePolicyStore
from future_intelligence.release_control.providers import InMemoryReleaseProvider, ReleaseDeployment
from future_intelligence.release_control.recovery import ReleaseRecoveryService
from future_intelligence.release_control.runtime import ReleaseControlRuntime
from future_intelligence.release_control.store import InMemoryReleaseStore


BASE = "a" * 40
CANDIDATE = "b" * 40


class HealthyEnvironment:
    def qualify_preview(self, *, target, spec_id, candidate_revision):
        return EnvironmentQualificationResult(
            environment="preview", target=target, healthy=True,
            checks={"revision": candidate_revision == CANDIDATE}, evidence=("preview://recovered",),
        )

    def smoke_production(self, *, target, release_revision):
        return EnvironmentQualificationResult(
            environment="production", target=target, healthy=True,
            checks={"revision": release_revision == CANDIDATE}, evidence=("production://recovered",),
        )


class ObservingProvider(InMemoryReleaseProvider):
    def __init__(self):
        super().__init__()
        self.observe_calls = []
        self.preview_calls = 0
        self.promote_calls = 0
        self.rollback_calls = 0

    def observe(self, deployment):
        self.observe_calls.append(deployment.id)
        return ReleaseDeployment(
            id=deployment.id,
            provider=deployment.provider,
            target=deployment.target,
            revision=deployment.revision,
            environment=deployment.environment,
            url=deployment.url,
            state="ready",
        )

    def create_preview(self, plan):
        self.preview_calls += 1
        return super().create_preview(plan)

    def promote(self, plan):
        self.promote_calls += 1
        return super().promote(plan)

    def rollback(self, plan, deployment):
        self.rollback_calls += 1
        return super().rollback(plan, deployment)


def release(status, **changes):
    value = ReleasePlan(
        id=f"release-{status.value}",
        work_order_id="work-recovery",
        attempt_id="attempt-recovery",
        engineering_spec_id="spec-recovery",
        repository="owner/repo",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        qualification_digest="d" * 64,
        provider="memory",
        target="vishnu-production",
        risk_class=ReleaseRiskClass.LOW,
        status=status,
        approval_required=False,
    )
    return value.with_update(**changes) if changes else value


def runtime(tmp_path, plan):
    provider = ObservingProvider()
    store = InMemoryReleaseStore()
    store.save(plan)
    policy_store = ReleasePolicyStore(tmp_path / "release-policy.json")
    policy_store.replace(ReleaseOwnerPolicy(mode=ReleaseAutonomyMode.AUTO_LOW_RISK))
    environment = HealthyEnvironment()
    controller = GovernedReleaseController(
        store=store,
        policy=policy_store.snapshot(),
        preview_qualifier=environment,
        production_smoke=environment,
    )
    value = ReleaseControlRuntime(controller=controller, policy_store=policy_store, providers={provider.name: provider})
    return value, provider


def test_restart_never_replays_preview_action_when_deployment_id_was_not_persisted(tmp_path):
    value, provider = runtime(tmp_path, release(ReleaseStatus.PREVIEWING))
    results = ReleaseRecoveryService(value).reconcile()
    restored = value.controller.store.get("release-previewing")
    assert restored.status is ReleaseStatus.RECOVERY_REQUIRED
    assert results[0].action == "owner_reconciliation_required"
    assert provider.preview_calls == 0
    assert provider.promote_calls == 0


def test_restart_reobserves_and_requalifies_known_preview_without_redeploying(tmp_path):
    plan = release(
        ReleaseStatus.PREVIEW_QUALIFYING,
        preview_deployment_id="preview-1",
        preview_url="https://release.invalid/preview-1",
    )
    value, provider = runtime(tmp_path, plan)
    results = ReleaseRecoveryService(value).reconcile()
    restored = value.controller.store.get(plan.id)
    assert restored.status is ReleaseStatus.PREVIEW_QUALIFIED
    assert results[0].action == "preview_requalified"
    assert provider.observe_calls == ["preview-1"]
    assert provider.preview_calls == 0


def test_restart_never_replays_unknown_production_promotion(tmp_path):
    value, provider = runtime(tmp_path, release(ReleaseStatus.PROMOTING))
    ReleaseRecoveryService(value).reconcile()
    restored = value.controller.store.get("release-promoting")
    assert restored.status is ReleaseStatus.RECOVERY_REQUIRED
    assert provider.promote_calls == 0
    assert provider.rollback_calls == 0


def test_restart_reobserves_and_smokes_known_production_without_redeploying(tmp_path):
    plan = release(
        ReleaseStatus.PRODUCTION_QUALIFYING,
        production_deployment_id="prod-1",
        production_url="https://release.invalid/prod-1",
    )
    value, provider = runtime(tmp_path, plan)
    results = ReleaseRecoveryService(value).reconcile()
    restored = value.controller.store.get(plan.id)
    assert restored.status is ReleaseStatus.MONITORING
    assert results[0].action == "production_requalified"
    assert provider.observe_calls == ["prod-1"]
    assert provider.promote_calls == 0


def test_restart_never_replays_unknown_rollback(tmp_path):
    plan = release(
        ReleaseStatus.ROLLING_BACK,
        production_deployment_id="prod-rollback-source",
        production_url="https://release.invalid/prod",
    )
    value, provider = runtime(tmp_path, plan)
    ReleaseRecoveryService(value).reconcile()
    restored = value.controller.store.get(plan.id)
    assert restored.status is ReleaseStatus.RECOVERY_REQUIRED
    assert provider.rollback_calls == 0
