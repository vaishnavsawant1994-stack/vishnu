from __future__ import annotations

from future_intelligence.engineering.contracts import (
    EngineeringSpec,
    QualificationGateResult,
    QualificationGateStatus,
    QualificationReport,
    SecurityClass,
)
from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control.automation import ReleaseAutomationService
from future_intelligence.release_control.controller import GovernedReleaseController
from future_intelligence.release_control.policy import ReleaseAutonomyMode, ReleaseOwnerPolicy
from future_intelligence.release_control.policy_store import ReleasePolicyStore
from future_intelligence.release_control.providers import InMemoryReleaseProvider
from future_intelligence.release_control.runtime import ReleaseControlRuntime
from future_intelligence.release_control.store import InMemoryReleaseStore


BASE = "a" * 40
CANDIDATE = "b" * 40


class HealthyEnvironment:
    def qualify_preview(self, *, target, spec_id, candidate_revision):
        return EnvironmentQualificationResult(
            environment="preview", target=target, healthy=True,
            checks={"candidate": candidate_revision == CANDIDATE}, evidence=("preview://ok",),
        )

    def smoke_production(self, *, target, release_revision):
        return EnvironmentQualificationResult(
            environment="production", target=target, healthy=True,
            checks={"candidate": release_revision == CANDIDATE}, evidence=("production://ok",),
        )


class RecordingAutomation(ReleaseAutomationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = []

    def start(self, release_id: str) -> bool:
        self.started.append(release_id)
        return True


def spec(*, surfaces=("pwa/home",), security_class=SecurityClass.STANDARD):
    return EngineeringSpec(
        id="spec-auto-1",
        work_order_id="work-auto-1",
        attempt_id="attempt-auto-1",
        repository="owner/repo",
        base_revision=BASE,
        objective="Release a qualified candidate",
        affected_surfaces=tuple(surfaces),
        security_class=security_class,
    )


def report(*, approved=True):
    return QualificationReport(
        spec_id="spec-auto-1",
        base_revision=BASE,
        candidate_revision=CANDIDATE,
        gates=(QualificationGateResult(
            gate="requirements",
            status=QualificationGateStatus.PASS,
            summary="passed",
            evidence=("ci://exact",),
        ),),
        reviewer="independent-reviewer",
        review_decision="approved" if approved else "changes_requested",
    )


def runtime(tmp_path, *, mode=ReleaseAutonomyMode.AUTO_LOW_RISK, providers=1):
    policy_store = ReleasePolicyStore(tmp_path / "release-policy.json")
    policy_store.replace(ReleaseOwnerPolicy(mode=mode))
    environment = HealthyEnvironment()
    controller = GovernedReleaseController(
        store=InMemoryReleaseStore(),
        policy=policy_store.snapshot(),
        preview_qualifier=environment,
        production_smoke=environment,
    )
    configured = {}
    for index in range(providers):
        provider = InMemoryReleaseProvider(host=f"release-{index}.invalid")
        provider.name = f"memory-{index}"
        configured[provider.name] = provider
    return ReleaseControlRuntime(controller=controller, policy_store=policy_store, providers=configured)


def test_low_risk_qualified_candidate_is_handed_off_and_auto_start_is_requested(tmp_path):
    value = runtime(tmp_path)
    automation = RecordingAutomation(value)
    result = automation.handoff(spec=spec(), report=report())

    assert result.created is True
    assert result.automatic_execution_started is True
    assert automation.started == [result.release_id]
    plan = value.controller.require(result.release_id)
    assert plan.risk_class.label == "low"
    assert plan.approval_required is False


def test_sensitive_candidate_is_handed_off_but_never_auto_started(tmp_path):
    value = runtime(tmp_path)
    automation = RecordingAutomation(value)
    result = automation.handoff(
        spec=spec(surfaces=("authentication/session",)),
        report=report(),
    )

    assert result.created is True
    assert result.automatic_execution_started is False
    assert automation.started == []
    plan = value.controller.require(result.release_id)
    assert plan.risk_class.label == "high"
    assert plan.approval_required is True


def test_authority_security_class_is_critical_and_approval_gated(tmp_path):
    value = runtime(tmp_path)
    automation = RecordingAutomation(value)
    result = automation.handoff(
        spec=spec(security_class=SecurityClass.AUTHORITY),
        report=report(),
    )
    plan = value.controller.require(result.release_id)
    assert plan.risk_class.label == "critical"
    assert plan.approval_required is True
    assert automation.started == []


def test_unqualified_engineering_result_never_creates_release_plan(tmp_path):
    value = runtime(tmp_path)
    automation = RecordingAutomation(value)
    result = automation.handoff(spec=spec(), report=report(approved=False))
    assert result.created is False
    assert value.controller.store.list() == ()
    assert automation.started == []


def test_multiple_providers_require_an_explicit_default_provider(tmp_path):
    value = runtime(tmp_path, providers=2)
    automation = RecordingAutomation(value)
    result = automation.handoff(spec=spec(), report=report())
    assert result.created is False
    assert "unambiguous" in result.reason

    selected = RecordingAutomation(value, default_provider="memory-1")
    selected_result = selected.handoff(spec=spec(), report=report())
    assert selected_result.created is True
    assert value.controller.require(selected_result.release_id).provider == "memory-1"


def test_approval_required_mode_never_requests_automatic_execution(tmp_path):
    value = runtime(tmp_path, mode=ReleaseAutonomyMode.APPROVAL_REQUIRED)
    automation = RecordingAutomation(value)
    result = automation.handoff(spec=spec(), report=report())
    assert result.created is True
    assert result.automatic_execution_started is False
    assert automation.started == []
