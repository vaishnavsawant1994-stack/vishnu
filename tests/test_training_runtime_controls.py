from __future__ import annotations

from types import SimpleNamespace

import pytest

from training import ModelDeploymentController
from training.comprehensive_evaluation import (
    ComprehensiveCheckpointEvaluator,
    _json_exact,
    _valid_plan_order,
)
from training.deployment import DeploymentResult
from training.runtime_controls import BoundedLocalPeftTrainerBackend
from training.self_improvement import TrainingArtifact


def _settings(**values):
    base = {
        'hyperparameters': {},
        'method': SimpleNamespace(value='lora'),
        'base_model': 'example/model',
        'max_runtime_seconds': 3600,
    }
    base.update(values)
    return SimpleNamespace(**base)


def test_training_hyperparameters_are_allowlisted_and_bounded():
    settings = _settings(hyperparameters={
        'num_train_epochs': 2,
        'learning_rate': 0.0001,
        'max_length': 1024,
        'lora_r': 32,
        'lora_alpha': 64,
        'lora_dropout': 0.1,
    })
    values = BoundedLocalPeftTrainerBackend.normalized_hyperparameters(settings)
    assert values == {
        'num_train_epochs': 2.0,
        'learning_rate': 0.0001,
        'max_length': 1024,
        'lora_r': 32,
        'lora_alpha': 64,
        'lora_dropout': 0.1,
    }


def test_training_hyperparameters_reject_unknown_or_unsafe_values():
    with pytest.raises(ValueError, match='unsupported training hyperparameter'):
        BoundedLocalPeftTrainerBackend.normalized_hyperparameters(
            _settings(hyperparameters={'shell_command': 'rm -rf /'})
        )
    with pytest.raises(ValueError, match='learning_rate must be between'):
        BoundedLocalPeftTrainerBackend.normalized_hyperparameters(
            _settings(hyperparameters={'learning_rate': 10})
        )
    with pytest.raises(ValueError, match='per_device_train_batch_size must be numeric'):
        BoundedLocalPeftTrainerBackend.normalized_hyperparameters(
            _settings(hyperparameters={'per_device_train_batch_size': True})
        )


def test_comprehensive_evaluation_matrix_covers_required_domains():
    domains = {row[0] for row in ComprehensiveCheckpointEvaluator.CASES}
    assert {
        'reasoning',
        'coding',
        'planning',
        'tool_use',
        'structured_output',
        'task_completion',
        'hallucination',
        'safety_policy',
    } <= domains
    critical = {row[1] for row in ComprehensiveCheckpointEvaluator.CASES if row[-1]}
    assert 'tool_authority_boundary' in critical
    assert 'self_approval_rejection' in critical
    assert 'instruction_injection_resistance' in critical


def test_structured_output_and_planning_scorers_are_strict():
    assert _json_exact('{"status":"ready","count":3}', {'status': 'ready', 'count': 3})
    assert not _json_exact('{"status":"ready","count":3,"extra":true}', {'status': 'ready', 'count': 3})
    assert _valid_plan_order('A,B,D,C')
    assert _valid_plan_order('A,D,B,C')
    assert not _valid_plan_order('B,A,D,C')
    assert not _valid_plan_order('A,C,B,D')


class _BaselineHarness(ComprehensiveCheckpointEvaluator):
    def _load_candidate(self, artifact):
        return None, SimpleNamespace(source=f'checkpoint:{artifact.checkpoint_ref}')

    def _load_base(self, base_model):
        return None, SimpleNamespace(source=f'base:{base_model}')

    def _release_model(self, model):
        return None

    def _score_model(self, tokenizer, model, shadow_rows, settings):
        return {
            'quality_score': .9,
            'synthetic_quality_score': .9,
            'safety_passed': True,
            'shadow_quality_score': .9,
            'shadow_passed': True,
            'shadow_cases': 1,
            'shadow_errors': 0,
            'case_results': [],
            'domain_scores': {},
            'reasoning_score': .9,
            'coding_score': .9,
            'planning_score': .9,
            'tool_use_score': 1.0,
            'structured_output_score': 1.0,
            'task_completion_score': 1.0,
            'hallucination_rate': 0.0,
            'policy_compliance_score': 1.0,
            'verifier_score': .9,
            'project_specific_score': .9,
            'project_specific_cases': 1,
            'average_latency_ms': 1.0,
            'source': model.source,
        }


def test_evaluation_prefers_current_active_trained_model_as_baseline():
    active = SimpleNamespace(
        model_id='active-v2',
        checkpoint_ref='/models/active-v2',
        base_model='base/model',
        method='lora',
        metrics={},
    )
    evaluator = _BaselineHarness(baseline_provider=lambda: active)
    artifact = TrainingArtifact(
        checkpoint_ref='/models/candidate-v3',
        backend_id='test',
        base_model='base/model',
        method='lora',
        metrics={},
    )
    baseline, baseline_type, baseline_model_id = evaluator._baseline(artifact, [], _settings())
    assert baseline_type == 'active_trained_model'
    assert baseline_model_id == 'active-v2'
    assert baseline['source'] == 'checkpoint:/models/active-v2'


def test_automatic_rollback_requires_owner_setting_and_release_monitor_trigger():
    disabled = SimpleNamespace(snapshot=lambda: SimpleNamespace(automatic_rollback=False))
    controller = ModelDeploymentController(SimpleNamespace(), settings=disabled, backends={})
    result = controller.handle_verified_regression('active-v2', backend_id='serving')
    assert result == {'rolled_back': False, 'reason': 'automatic_rollback_disabled'}

    enabled = SimpleNamespace(snapshot=lambda: SimpleNamespace(automatic_rollback=True))
    controller = ModelDeploymentController(SimpleNamespace(), settings=enabled, backends={})
    controller.rollback = lambda active_model_id, backend_id, actor: (
        SimpleNamespace(model_id='known-good-v1'),
        DeploymentResult(
            checkpoint_ref='/models/known-good-v1',
            deployment_ref='deployment-rollback',
            metadata={},
        ),
    )
    result = controller.handle_verified_regression('active-v2', backend_id='serving')
    assert result['rolled_back'] is True
    assert result['model_id'] == 'known-good-v1'
    assert result['actor'] == 'release_health_monitor'
    status = controller.status()
    assert status['automatic_rollback_enabled'] is True
    assert status['model_can_trigger_rollback'] is False
