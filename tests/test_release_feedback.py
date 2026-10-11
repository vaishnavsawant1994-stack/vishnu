from __future__ import annotations

from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.release_control.feedback import RegressionAwareProductionSmokeProvider


REVISION = "b" * 40


class FailingSmoke:
    def smoke_production(self, *, target: str, release_revision: str):
        return EnvironmentQualificationResult(
            environment="production",
            target=target,
            healthy=False,
            checks={"health": False, "revision": release_revision == REVISION},
            evidence=("production://health-failed", "production://api-failed"),
            summary="production smoke failed",
        )


class HealthySmoke:
    def smoke_production(self, *, target: str, release_revision: str):
        return EnvironmentQualificationResult(
            environment="production",
            target=target,
            healthy=True,
            checks={"health": True},
            evidence=("production://healthy",),
            summary="production healthy",
        )


class Bridge:
    def __init__(self):
        self.rows = []

    def create(self, regression):
        self.rows.append(regression)
        return regression


def test_failed_production_smoke_creates_high_severity_regression_for_exact_revision():
    bridge = Bridge()
    provider = RegressionAwareProductionSmokeProvider(FailingSmoke(), bridge)

    result = provider.smoke_production(
        target="https://production.example.test",
        release_revision=REVISION,
    )

    assert result.passed is False
    assert len(bridge.rows) == 1
    regression = bridge.rows[0]
    assert regression.release_revision == REVISION
    assert regression.target == "https://production.example.test"
    assert regression.signal == "production smoke failed"
    assert regression.evidence == ("production://health-failed", "production://api-failed")
    assert regression.severity == "high"


def test_healthy_production_smoke_does_not_create_regression_work():
    bridge = Bridge()
    provider = RegressionAwareProductionSmokeProvider(HealthySmoke(), bridge)

    result = provider.smoke_production(
        target="https://production.example.test",
        release_revision=REVISION,
    )

    assert result.passed is True
    assert bridge.rows == []


def test_failed_smoke_without_bridge_remains_read_only_and_does_not_crash():
    provider = RegressionAwareProductionSmokeProvider(FailingSmoke(), None)
    result = provider.smoke_production(
        target="https://production.example.test",
        release_revision=REVISION,
    )
    assert result.passed is False
