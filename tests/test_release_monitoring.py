from __future__ import annotations

from dataclasses import replace

from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass, ReleaseStatus
from future_intelligence.release_control.controller import GovernedReleaseController
from future_intelligence.release_control.monitoring import ProductionReleaseMonitor
from future_intelligence.release_control.policy_store import ReleasePolicyStore
from future_intelligence.release_control.providers import InMemoryReleaseProvider, ReleaseDeployment
from future_intelligence.release_control.runtime import ReleaseControlRuntime
from future_intelligence.release_control.store import InMemoryReleaseStore


BASE = "a" * 40
CANDIDATE = "b" * 40


class HealthySmoke:
    def smoke_production(self, *, target: str, release_revision: str):
        return EnvironmentQualificationResult(
            environment="production",
            target=target,
            healthy=True,
            checks={"health": True, "revision": release_revision == CANDIDATE},
            evidence=("monitor://smoke",),
            summary="production healthy",
        )


class FailingObserveProvider(InMemoryReleaseProvider):
    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment:
        raise RuntimeError("provider unavailable")


class DriftObserveProvider(InMemoryReleaseProvider):
    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment:
        return replace(deployment, revision="c" * 40)


class RegressionBridge:
    def __init__(self):
        self.rows = []

    def create(self, regression):
        self.rows.append(regression)
        return regression


def make_runtime(tmp_path, *, provider=None, max_observations=1000, bridge=None):
    provider = provider or InMemoryReleaseProvider()
    store = InMemoryReleaseStore()
    policy_store = ReleasePolicyStore(tmp_path / "release-monitor-policy.json")
    policy_store.update(max_monitoring_observations=max_observations)
    controller = GovernedReleaseController(
        store=store,
        policy=policy_store.snapshot(),
        production_smoke=HealthySmoke(),
        regression_bridge=bridge,
    )
    runtime = ReleaseControlRuntime(
        controller=controller,
        policy_store=policy_store,
        providers={provider.name: provider},
    )
    plan = ReleasePlan(
        id="release-monitor-1",
        work_order_id="work-monitor-1",
        attempt_id="attempt-monitor-1",
        engineering_spec_id="spec-monitor-1",
        repository="owner/repo",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        qualification_digest="digest-monitor-1",
        provider=provider.name,
        target="owner/repo",
        risk_class=ReleaseRiskClass.LOW,
        status=ReleaseStatus.MONITORING,
        production_deployment_id="production-deploy-1",
        production_url="https://release.invalid/production",
    )
    store.save(plan)
    return runtime, plan


def test_healthy_monitor_observation_is_trusted_and_read_only(tmp_path):
    runtime, plan = make_runtime(tmp_path)
    monitor = ProductionReleaseMonitor(runtime)

    result = monitor.check_once(plan.id)
    persisted = runtime.controller.require(plan.id)

    assert result.outcome == "healthy"
    assert persisted.status is ReleaseStatus.MONITORING
    evidence = persisted.evidence[-1]
    assert evidence.kind == "production_monitor_observation"
    assert evidence.trusted is True
    assert evidence.revision == CANDIDATE
    assert evidence.metadata["smoke"]["passed"] is True


def test_transient_monitor_failure_does_not_immediately_recommend_rollback(tmp_path):
    runtime, plan = make_runtime(tmp_path, provider=FailingObserveProvider())
    monitor = ProductionReleaseMonitor(runtime, failure_threshold=3)

    first = monitor.check_once(plan.id)
    second = monitor.check_once(plan.id)
    persisted = runtime.controller.require(plan.id)

    assert first.outcome == "transient_failure"
    assert second.outcome == "transient_failure"
    assert persisted.status is ReleaseStatus.MONITORING
    assert [item.kind for item in persisted.evidence].count("production_monitor_error") == 2


def test_repeated_monitor_failure_recommends_rollback_and_creates_regression_work(tmp_path):
    bridge = RegressionBridge()
    runtime, plan = make_runtime(tmp_path, provider=FailingObserveProvider(), bridge=bridge)
    monitor = ProductionReleaseMonitor(runtime, failure_threshold=3)

    monitor.check_once(plan.id)
    monitor.check_once(plan.id)
    result = monitor.check_once(plan.id)
    persisted = runtime.controller.require(plan.id)

    assert result.outcome == "rollback_recommended"
    assert persisted.status is ReleaseStatus.ROLLBACK_RECOMMENDED
    assert len(bridge.rows) == 1
    assert bridge.rows[0].release_revision == CANDIDATE
    assert "production monitor failed 3 consecutive observations" in bridge.rows[0].signal
    assert not any(item.kind == "rollback_execution" for item in persisted.evidence)


def test_revision_drift_is_treated_as_failed_health_proof_without_rollback_execution(tmp_path):
    bridge = RegressionBridge()
    runtime, plan = make_runtime(tmp_path, provider=DriftObserveProvider(), bridge=bridge)
    monitor = ProductionReleaseMonitor(runtime, failure_threshold=1)

    result = monitor.check_once(plan.id)
    persisted = runtime.controller.require(plan.id)

    assert result.outcome == "rollback_recommended"
    assert persisted.status is ReleaseStatus.ROLLBACK_RECOMMENDED
    assert bridge.rows
    assert not any(item.kind == "rollback_execution" for item in persisted.evidence)


def test_monitor_observation_budget_is_enforced(tmp_path):
    runtime, plan = make_runtime(tmp_path, max_observations=1)
    monitor = ProductionReleaseMonitor(runtime)

    assert monitor.check_once(plan.id).outcome == "healthy"
    second = monitor.check_once(plan.id)
    persisted = runtime.controller.require(plan.id)

    assert second.outcome == "observation_limit_reached"
    assert second.observation_count == 1
    assert len(persisted.evidence) == 1


def test_non_monitoring_release_is_a_noop(tmp_path):
    runtime, plan = make_runtime(tmp_path)
    runtime.controller.store.save(plan.with_update(status=ReleaseStatus.SUCCEEDED, production_deployment_id="production-deploy-1"))
    monitor = ProductionReleaseMonitor(runtime)

    result = monitor.check_once(plan.id)
    assert result.outcome == "not_monitoring"
    assert runtime.controller.require(plan.id).status is ReleaseStatus.SUCCEEDED
