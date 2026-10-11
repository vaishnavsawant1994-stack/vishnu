from __future__ import annotations

import pytest

from training.contributions import (
    ContributionKind,
    ContributionMode,
    ContributionPreferences,
    ContributorPseudonymizer,
    StrategySignalAggregator,
    evaluate_contribution,
)


def test_private_mode_never_contributes():
    decision = evaluate_contribution(
        ContributionPreferences(),
        ContributionKind.AGENT_OUTCOME,
        {"task_type": "frontend", "strategy_id": "s1", "result": "success"},
    )
    assert decision.accepted is False
    assert decision.reason == "private_mode"


def test_aggregate_mode_accepts_bounded_agent_signal_only():
    preferences = ContributionPreferences(mode=ContributionMode.AGGREGATE)
    decision = evaluate_contribution(
        preferences,
        ContributionKind.AGENT_OUTCOME,
        {
            "task_type": "frontend_bug",
            "strategy_id": "repo_fix_v7",
            "result": "success",
            "tests_passed": True,
            "duration_bucket": "5-10m",
        },
    )
    assert decision.accepted is True
    assert decision.requires_training_governance is False
    assert decision.payload["strategy_id"] == "repo_fix_v7"


def test_aggregate_mode_rejects_raw_content_and_unknown_fields():
    preferences = ContributionPreferences(mode=ContributionMode.AGGREGATE)
    raw = evaluate_contribution(
        preferences,
        ContributionKind.AGENT_OUTCOME,
        {"task_type": "coding", "prompt": "private source code"},
    )
    assert raw.accepted is False
    assert raw.reason == "forbidden_or_secret_bearing_field"

    unknown = evaluate_contribution(
        preferences,
        ContributionKind.AGENT_OUTCOME,
        {"task_type": "coding", "user_message": "hello"},
    )
    assert unknown.accepted is False
    assert "unsupported fields" in unknown.reason


def test_aggregate_mode_never_accepts_conversations():
    preferences = ContributionPreferences(
        mode=ContributionMode.AGGREGATE,
        conversations=True,
    )
    decision = evaluate_contribution(
        preferences,
        ContributionKind.CONVERSATION,
        {"message_count": 3},
    )
    assert decision.accepted is False
    assert decision.reason == "aggregate_mode_allows_structured_signals_only"


def test_training_contributor_requires_explicit_opt_in_and_governance_handoff():
    disabled = ContributionPreferences(mode=ContributionMode.TRAINING_CONTRIBUTOR)
    blocked = evaluate_contribution(
        disabled,
        ContributionKind.CORRECTION,
        {"correction_text": "fixed answer"},
        privacy_cleared=True,
        secret_scan_passed=True,
        provenance_present=True,
    )
    assert blocked.accepted is False
    assert blocked.reason == "kind_not_opted_in"

    enabled = ContributionPreferences(
        mode=ContributionMode.TRAINING_CONTRIBUTOR,
        corrections=True,
    )
    privacy_blocked = evaluate_contribution(
        enabled,
        ContributionKind.CORRECTION,
        {"correction_text": "fixed answer"},
        privacy_cleared=False,
        secret_scan_passed=True,
        provenance_present=True,
    )
    assert privacy_blocked.accepted is False
    assert privacy_blocked.reason == "privacy_clearance_required"

    accepted = evaluate_contribution(
        enabled,
        ContributionKind.CORRECTION,
        {"correction_text": "fixed answer"},
        privacy_cleared=True,
        secret_scan_passed=True,
        provenance_present=True,
    )
    assert accepted.accepted is True
    assert accepted.requires_training_governance is True
    assert accepted.reason == "training_candidate_handoff_required"


def test_documents_are_off_by_default_even_for_training_contributors():
    preferences = ContributionPreferences(mode=ContributionMode.TRAINING_CONTRIBUTOR)
    decision = evaluate_contribution(
        preferences,
        ContributionKind.DOCUMENT,
        {"document_ref": "doc-1"},
        privacy_cleared=True,
        secret_scan_passed=True,
        provenance_present=True,
    )
    assert decision.accepted is False
    assert decision.reason == "kind_not_opted_in"


def test_secret_and_hidden_reasoning_fields_fail_closed():
    preferences = ContributionPreferences(
        mode=ContributionMode.TRAINING_CONTRIBUTOR,
        conversations=True,
    )
    for payload in (
        {"token": "secret"},
        {"hidden_chain_of_thought": "private reasoning"},
        {"nested": {"authorization": "Bearer abc"}},
    ):
        decision = evaluate_contribution(
            preferences,
            ContributionKind.CONVERSATION,
            payload,
            privacy_cleared=True,
            secret_scan_passed=True,
            provenance_present=True,
        )
        assert decision.accepted is False
        assert decision.reason == "forbidden_or_secret_bearing_field"


def test_pseudonymizer_is_stable_scoped_and_does_not_emit_raw_owner_id():
    pseudonymizer = ContributorPseudonymizer(b"x" * 32)
    first = pseudonymizer.pseudonym("owner@example.test")
    second = pseudonymizer.pseudonym("owner@example.test")
    other = ContributorPseudonymizer(b"y" * 32).pseudonym("owner@example.test")

    assert first == second
    assert first != other
    assert "owner@example.test" not in first
    assert first.startswith("contrib-")


def test_pseudonymizer_requires_high_entropy_key_material_length():
    with pytest.raises(ValueError, match="32 bytes"):
        ContributorPseudonymizer(b"short")


def test_strategy_aggregates_are_withheld_until_contributor_threshold():
    preferences = ContributionPreferences(mode=ContributionMode.AGGREGATE)
    aggregator = StrategySignalAggregator(minimum_contributors=3)
    decision = evaluate_contribution(
        preferences,
        ContributionKind.AGENT_OUTCOME,
        {"task_type": "frontend_bug", "strategy_id": "repo_fix_v7", "result": "success", "tests_passed": True},
    )
    pseudonymizer = ContributorPseudonymizer(b"z" * 32)

    aggregator.add(pseudonymizer.pseudonym("a"), decision)
    aggregator.add(pseudonymizer.pseudonym("b"), decision)
    assert aggregator.report() == ()

    aggregator.add(pseudonymizer.pseudonym("c"), decision)
    report = aggregator.report()
    assert len(report) == 1
    row = report[0]
    assert row["contributors"] == 3
    assert row["samples"] == 3
    assert row["success_rate"] == 1.0
    assert all(not key.endswith("pseudonym") for key in row)


def test_aggregator_rejects_raw_training_candidate_handoffs():
    preferences = ContributionPreferences(
        mode=ContributionMode.TRAINING_CONTRIBUTOR,
        conversations=True,
    )
    decision = evaluate_contribution(
        preferences,
        ContributionKind.CONVERSATION,
        {"message": "approved candidate"},
        privacy_cleared=True,
        secret_scan_passed=True,
        provenance_present=True,
    )
    aggregator = StrategySignalAggregator()
    with pytest.raises(ValueError, match="aggregate signals"):
        aggregator.add("contrib-abc", decision)
