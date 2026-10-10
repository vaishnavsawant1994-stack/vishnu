import pytest

from models.adaptive_strategy import AdaptiveStrategy, ExecutionPattern, StrategyRequest, TaskComplexity
from models.intelligence_modes import IntelligenceMode, intelligence_profile
from models.performance import ModelPerformanceTracker, PerformanceObservation


def test_standard_preserves_existing_single_model_behavior():
    profile = intelligence_profile(IntelligenceMode.STANDARD)
    decision = AdaptiveStrategy().decide(
        StrategyRequest(
            profile=profile,
            task_domain='software_engineering',
            complexity=TaskComplexity.CRITICAL,
            evidence_required=True,
        )
    )

    assert profile.adaptive_routing is False
    assert profile.deliberation is False
    assert decision.pattern is ExecutionPattern.SINGLE
    assert decision.max_models == 1
    assert decision.verifier_required is False


def test_training_capture_defaults_on_and_owner_can_disable_it():
    assert intelligence_profile('standard').training_capture is True
    assert intelligence_profile('smart').training_capture is True
    assert intelligence_profile('deep').training_capture is True
    assert intelligence_profile('research').training_capture is True

    disabled = intelligence_profile('research', training_capture=False)
    assert disabled.training_capture is False
    assert disabled.mode is IntelligenceMode.RESEARCH
    assert disabled.max_models == 5


def test_higher_modes_are_bounded_permission_ceilings():
    strategy = AdaptiveStrategy()

    smart = strategy.decide(
        StrategyRequest(
            profile=intelligence_profile('smart'),
            complexity=TaskComplexity.CRITICAL,
            evidence_required=True,
        )
    )
    deep = strategy.decide(
        StrategyRequest(
            profile=intelligence_profile('deep'),
            complexity=TaskComplexity.HIGH,
        )
    )
    research = strategy.decide(
        StrategyRequest(
            profile=intelligence_profile('research'),
            complexity=TaskComplexity.CRITICAL,
        )
    )

    assert smart.pattern is ExecutionPattern.PRIMARY_PLUS_VERIFIER
    assert smart.max_models <= 2
    assert deep.pattern is ExecutionPattern.SPECIALIST_RACE
    assert deep.max_models <= 4
    assert research.pattern is ExecutionPattern.DEEP_CONSENSUS
    assert research.max_models <= 5
    assert 'agreement_is_not_proof' in research.reason_codes


@pytest.mark.parametrize('mode', ['smart', 'deep', 'research'])
def test_simple_tasks_do_not_spend_extra_models(mode):
    decision = AdaptiveStrategy().decide(
        StrategyRequest(
            profile=intelligence_profile(mode),
            complexity=TaskComplexity.LOW,
        )
    )

    assert decision.pattern is ExecutionPattern.SINGLE
    assert decision.max_models == 1
    assert decision.verifier_required is False


def test_evidence_requirement_can_promote_smart_to_verifier():
    decision = AdaptiveStrategy().decide(
        StrategyRequest(
            profile=intelligence_profile('smart'),
            complexity=TaskComplexity.MEDIUM,
            evidence_required=True,
        )
    )

    assert decision.pattern is ExecutionPattern.PRIMARY_PLUS_VERIFIER
    assert decision.max_models == 2
    assert decision.verifier_required is True


def test_performance_learning_is_bounded_by_sample_confidence():
    tracker = ModelPerformanceTracker(max_influence=0.5, full_weight_samples=20)
    first = tracker.record(
        PerformanceObservation(
            task_domain='coding',
            provider_id='provider-a',
            model_id='model-a',
            success=True,
            verifier_score=0.9,
            latency_ms=100.0,
            estimated_cost=0.01,
            accepted=True,
        )
    )

    assert first.samples == 1
    assert first.learning_influence == pytest.approx(0.025)
    assert first.quality_score == pytest.approx(0.9)

    latest = first
    for _ in range(30):
        latest = tracker.record(
            PerformanceObservation(
                task_domain='coding',
                provider_id='provider-a',
                model_id='model-a',
                success=True,
                verifier_score=1.0,
                accepted=True,
            )
        )

    assert latest.samples == 31
    assert latest.learning_influence == pytest.approx(0.5)
    assert 0.0 <= latest.quality_score <= 1.0
    assert latest.success_rate == pytest.approx(1.0)
    assert latest.acceptance_rate == pytest.approx(1.0)


def test_failed_or_corrected_outputs_reduce_quality_signal():
    tracker = ModelPerformanceTracker(alpha=1.0)
    failed = tracker.record(
        PerformanceObservation(
            task_domain='research',
            provider_id='provider-b',
            model_id='model-b',
            success=False,
            verifier_score=1.0,
        )
    )
    corrected = tracker.record(
        PerformanceObservation(
            task_domain='research',
            provider_id='provider-b',
            model_id='model-b',
            success=True,
            verifier_score=1.0,
            corrected=True,
            regenerated=True,
            fallback=True,
            accepted=False,
        )
    )

    assert failed.quality_score == 0.0
    assert corrected.quality_score < 1.0
    assert corrected.success_rate == pytest.approx(0.5)


def test_performance_observation_rejects_invalid_measurements():
    with pytest.raises(ValueError):
        PerformanceObservation('general', 'p', 'm', True, verifier_score=1.1)
    with pytest.raises(ValueError):
        PerformanceObservation('general', 'p', 'm', True, latency_ms=-1)
    with pytest.raises(ValueError):
        PerformanceObservation('general', 'p', 'm', True, estimated_cost=-0.1)


def test_unknown_mode_fails_closed():
    with pytest.raises(ValueError, match='unsupported intelligence mode'):
        intelligence_profile('godmode')
