from __future__ import annotations

import pytest

from future_intelligence.engineering.canary import CanaryMetrics
from future_intelligence.engineering.contracts import (
    EngineeringSpec,
    QualificationGateResult,
    QualificationGateStatus,
    QualificationReport,
)
from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control import (
    GovernedReleaseController,
    ReleaseAutonomyMode,
    ReleaseControlError,
    ReleaseEnvironment,
    ReleaseOwnerPolicy,
    ReleaseRiskClass,
    ReleaseStatus,
)
from future_intelligence.release_control.providers import InMemoryReleaseProvider, ReleaseDeployment
from future_intelligence.release_control.store import InMemoryReleaseStore, JsonReleaseStore


BASE = "a" * 40
CANDIDATE = "b" * 40


def _spec(*, surfaces: tuple[str, ...] = ("pwa/home",)) -> EngineeringSpec:
    return EngineeringSpec(
        id="spec-release-1",
        work_order_id="work-release-1",
        attempt_id="attempt-release-1",
        repository="vaishnavsawant1994-stack/vishnu",
        base_revision=BASE,
        objective="Ship the exact qualified candidate safely",
        affected_surfaces=surfaces,
    )


def _report(*, candidate: str = CANDIDATE, approved: bool = True) -> QualificationReport:
    return QualificationReport(
        spec_id="spec-release-1",
        base_revision=BASE,
        candidate_revision=candidate,
        gates=(
            QualificationGateResult(
                gate="engineering.requirements",
                status=QualificationGateStatus.PASS,
                summary="requirements passed",
                evidence=("ci://exact-head",),
            ),
        ),
        reviewer="independent-reviewer",
        review_decision="approved" if approved else "changes_requested",
    )


class _HealthyEnvironment:
    def qualify_preview(self, *, target: str, spec_id: str, candidate_revision: str):
        return EnvironmentQualificationResult(
            environment="preview",
            target=target,
            healthy=True,
            checks={"health": True, "revision": candidate_revision == CANDIDATE, "spec": spec_id == "spec-release-1"},
            evidence=("preview://health",),
            summary="preview passed",
        )

    def smoke_production(self, *, target: str, release_revision: str):
        return EnvironmentQualificationResult(
            environment="production",
            target=target,
            healthy=True,
            checks={"health": True, "revision": release_revision == CANDIDATE},
            evidence=("production://smoke",),
            summary="production smoke passed",
        )


def _controller(policy: ReleaseOwnerPolicy | None = None):
    environment = _HealthyEnvironment()
    return GovernedReleaseController(
        store=InMemoryReleaseStore(),
        policy=policy or ReleaseOwnerPolicy(mode=ReleaseAutonomyMode.AUTO_LOW_RISK),
        preview_qualifier=environment,
        production_smoke=environment,
    )


def test_unqualified_candidate_cannot_enter_release_control():
    controller = _controller()
    with pytest.raises(ReleaseControlError, match="not qualified"):
        controller.create_plan(
            spec=_spec(),
            report=_report(approved=False),
            provider="memory",
            target="vishnu-production",
        )


def test_auto_low_risk_release_requires_exact_preview_smoke_and_canary():
    controller = _controller()
    provider = InMemoryReleaseProvider()
    plan = controller.create_plan(
        spec=_spec(),
        report=_report(),
        provider=provider.name,
        target="vishnu-production",
        risk_class=ReleaseRiskClass.LOW,
    )
    assert plan.approval_required is False
    assert any(item.kind == "engineering_qualification" and item.trusted for item in plan.evidence)

    with pytest.raises(ReleaseControlError, match="preview"):
        controller.promote(plan.id, provider=provider)

    plan = controller.create_and_qualify_preview(plan.id, provider=provider)
    assert plan.status is ReleaseStatus.PREVIEW_QUALIFIED
    assert plan.preview_deployment_id

    plan = controller.promote(plan.id, provider=provider)
    assert plan.status is ReleaseStatus.MONITORING
    assert plan.production_deployment_id

    plan = controller.record_canary(
        plan.id,
        baseline=CanaryMetrics(sample_count=100, error_rate=0.01, p95_latency_ms=100),
        candidate=CanaryMetrics(sample_count=100, error_rate=0.01, p95_latency_ms=105),
    )
    assert plan.status is ReleaseStatus.SUCCEEDED


def test_sensitive_surface_requires_owner_approval_even_in_auto_mode():
    controller = _controller()
    provider = InMemoryReleaseProvider()
    plan = controller.create_plan(
        spec=_spec(surfaces=("authentication/session",)),
        report=_report(),
        provider=provider.name,
        target="vishnu-production",
        risk_class=ReleaseRiskClass.LOW,
    )
    assert plan.approval_required is True
    plan = controller.create_and_qualify_preview(plan.id, provider=provider)
    with pytest.raises(ReleaseControlError, match="owner approval"):
        controller.promote(plan.id, provider=provider)
    plan = controller.approve(plan.id, owner_identity="owner")
    assert plan.approved_by == "owner"
    assert controller.promote(plan.id, provider=provider).status is ReleaseStatus.MONITORING


def test_provider_revision_drift_fails_closed():
    class DriftProvider(InMemoryReleaseProvider):
        def create_preview(self, plan):
            deployment = super().create_preview(plan)
            return ReleaseDeployment(
                id=deployment.id,
                provider=deployment.provider,
                target=deployment.target,
                revision="c" * 40,
                environment=ReleaseEnvironment.PREVIEW,
                url=deployment.url,
            )

    controller = _controller()
    provider = DriftProvider()
    plan = controller.create_plan(
        spec=_spec(), report=_report(), provider=provider.name, target="vishnu-production", risk_class=ReleaseRiskClass.LOW
    )
    with pytest.raises(ReleaseControlError, match="different revision"):
        controller.create_and_qualify_preview(plan.id, provider=provider)


def test_canary_regression_recommends_rollback_but_does_not_grant_rollback():
    controller = _controller()
    provider = InMemoryReleaseProvider()
    plan = controller.create_plan(
        spec=_spec(), report=_report(), provider=provider.name, target="vishnu-production", risk_class=ReleaseRiskClass.LOW
    )
    controller.create_and_qualify_preview(plan.id, provider=provider)
    controller.promote(plan.id, provider=provider)
    plan = controller.record_canary(
        plan.id,
        baseline=CanaryMetrics(sample_count=100, error_rate=0.01, p95_latency_ms=100),
        candidate=CanaryMetrics(sample_count=100, error_rate=0.20, p95_latency_ms=250),
    )
    assert plan.status is ReleaseStatus.ROLLBACK_RECOMMENDED
    with pytest.raises(ReleaseControlError, match="does not grant rollback"):
        controller.rollback(plan.id, provider=provider, explicitly_approved=True)


def test_explicit_rollback_requires_both_policy_authority_and_confirmation():
    policy = ReleaseOwnerPolicy(
        mode=ReleaseAutonomyMode.AUTO_LOW_RISK,
        allow_automatic_rollback=True,
    )
    controller = _controller(policy)
    provider = InMemoryReleaseProvider()
    plan = controller.create_plan(
        spec=_spec(), report=_report(), provider=provider.name, target="vishnu-production", risk_class=ReleaseRiskClass.LOW
    )
    controller.create_and_qualify_preview(plan.id, provider=provider)
    controller.promote(plan.id, provider=provider)
    controller.record_canary(
        plan.id,
        baseline=CanaryMetrics(sample_count=100, error_rate=0.01, p95_latency_ms=100),
        candidate=CanaryMetrics(sample_count=100, error_rate=0.20, p95_latency_ms=250),
    )
    with pytest.raises(ReleaseControlError):
        controller.rollback(plan.id, provider=provider, explicitly_approved=False)
    plan = controller.rollback(plan.id, provider=provider, explicitly_approved=True)
    assert plan.status is ReleaseStatus.ROLLED_BACK
    assert plan.evidence[-1].metadata["restored_revision"] == BASE


def test_json_store_round_trip_and_rejects_path_escape(tmp_path):
    store = JsonReleaseStore(tmp_path)
    controller = GovernedReleaseController(
        store=store,
        policy=ReleaseOwnerPolicy(mode=ReleaseAutonomyMode.AUTO_LOW_RISK),
        preview_qualifier=_HealthyEnvironment(),
        production_smoke=_HealthyEnvironment(),
    )
    plan = controller.create_plan(
        spec=_spec(), report=_report(), provider="memory", target="vishnu-production", risk_class=ReleaseRiskClass.LOW
    )
    restored = store.get(plan.id)
    assert restored is not None
    assert restored.to_dict() == plan.to_dict()
    with pytest.raises(ValueError, match="invalid release id"):
        store.get("../../escape")
