from __future__ import annotations

from types import SimpleNamespace

import pytest

from training.comprehensive_evaluation import (
    ComprehensiveCheckpointEvaluator,
    _json_exact,
    _valid_plan_order,
)
from training.runtime_controls import BoundedLocalPeftTrainerBackend


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
