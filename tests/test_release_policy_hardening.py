from __future__ import annotations

import pytest

from future_intelligence.release_control.contracts import ReleasePlan, ReleaseRiskClass
from future_intelligence.release_control.policy import ReleaseAutonomyMode, ReleaseOwnerPolicy


def _plan(*, risk=ReleaseRiskClass.LOW, surfaces=("pwa/home",)):
    return ReleasePlan(
        id="release-hardening-1",
        work_order_id="work-hardening-1",
        attempt_id="attempt-hardening-1",
        engineering_spec_id="spec-hardening-1",
        repository="owner/repo",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        qualification_digest="digest-hardening-1",
        provider="render",
        target="owner/repo",
        risk_class=risk,
        affected_surfaces=surfaces,
    )


def test_auto_low_risk_policy_rejects_higher_automatic_ceiling():
    with pytest.raises(ValueError, match="low-risk"):
        ReleaseOwnerPolicy(
            mode=ReleaseAutonomyMode.AUTO_LOW_RISK,
            automatic_risk_ceiling=ReleaseRiskClass.HIGH,
        )


def test_sensitive_surface_approval_cannot_be_disabled():
    with pytest.raises(ValueError, match="sensitive release surfaces"):
        ReleaseOwnerPolicy(owner_approval_for_sensitive_surfaces=False)


def test_only_low_risk_non_sensitive_release_can_auto_promote():
    policy = ReleaseOwnerPolicy(mode=ReleaseAutonomyMode.AUTO_LOW_RISK)
    low = _plan()
    medium = _plan(risk=ReleaseRiskClass.MEDIUM)
    sensitive = _plan(surfaces=("authentication/session",))

    assert policy.allows_automatic_production(low) is True
    assert policy.requires_owner_approval(low) is False

    assert policy.allows_automatic_production(medium) is False
    assert policy.requires_owner_approval(medium) is True

    assert policy.allows_automatic_production(sensitive) is False
    assert policy.requires_owner_approval(sensitive) is True
