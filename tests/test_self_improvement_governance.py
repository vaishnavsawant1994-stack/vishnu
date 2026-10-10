from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.preferences import Preferences
from models.contracts import ModelResponse
from models.intelligence import IntelligenceEngine
from models.intelligence_modes import IntelligenceMode
from models.intelligence_settings import IntelligenceSettingsService
from models.performance import ModelPerformanceTracker, PerformanceObservation
from server.self_improvement_ui import JS as SELF_IMPROVEMENT_JS
from training import (
    AutoTrainingCoordinator,
    EvaluationResult,
    PrivacyLevel,
    TrainingArtifact,
    TrainingCandidateFactory,
    TrainingCandidateStore,
    TrainingCollector,
    TrainingDatasetSnapshotBuilder,
    TrainingRegistry,
    TrainingSettingsService,
)


class _LegacyRouter:
    def __init__(self):
        self._last = {'provider': 'self_hosted', 'model': 'local-model'}

    def chat(self, prompt, **kwargs):
        return f'answer:{prompt}'

    def json(self, prompt, **kwargs):
        return {'answer': prompt}

    def status(self, *, probe=False):
        return {'state': 'available'}


class _Trainer:
    backend_id = 'fake'

    def __init__(self, *, cost=.25, fail=False):
        self.cost = cost
        self.fail = fail
        self.calls = 0

    def available(self):
        return True, None

    def estimate_cost(self, snapshot, settings):
        return self.cost

    def train(self, snapshot, settings, output_dir):
        self.calls += 1
        if self.fail:
            raise RuntimeError('synthetic trainer failure')
        checkpoint = Path(output_dir) / 'checkpoint'
        checkpoint.mkdir(parents=True, exist_ok=True)
        (checkpoint / 'adapter.bin').write_bytes(b'not-stored-in-git')
        return TrainingArtifact(
            checkpoint_ref=str(checkpoint),
            backend_id=self.backend_id,
            base_model=settings.base_model,
            method=settings.method.value,
            metrics={'estimated_cost': self.cost, 'resource': {'gpu_seconds': 1}},
        )


class _Evaluator:
    def __init__(self, *, passed=True, safety=True):
        self.passed = passed
        self.safety = safety

    def evaluate(self, artifact, snapshot, settings):
        return EvaluationResult(
            passed=self.passed and self.safety,
            quality_score=.93 if self.passed else .6,
            baseline_quality_score=.82,
            safety_passed=self.safety,
            shadow_passed=self.passed,
            reasons=('evaluation_passed',) if self.passed and self.safety else ('security_regression',),
            metrics={'reasoning': .9, 'coding': .9, 'planning': .9, 'safety': 1.0 if self.safety else 0.0},
        )


def _approved(store: TrainingCandidateStore, start: int, count: int) -> None:
    factory = TrainingCandidateFactory()
    for index in range(start, start + count):
        candidate = factory.create(
            source_type='explicit_owner_feedback',
            source_id=f'source-{index}',
            prompt=f'prompt {index}',
            response=f'answer {index}',
            privacy_level='internal',
            provenance=f'owner-feedback:{index}',
            verifier_score=.95,
        )
        store.save(candidate)
        store.approve(candidate.candidate_id)


def _coordinator(tmp_path, store, trainer, evaluator=None, **settings_values):
    settings = TrainingSettingsService(tmp_path / 'training-settings.json')
    settings.update(
        enabled=True,
        backend_id='fake',
        base_model='base-model',
        method='lora',
        min_approved_records=10,
        min_new_examples_since_last_training=2,
        shadow_min_samples=2,
        **settings_values,
    )
    registry = TrainingRegistry(tmp_path / 'registry.sqlite3')
    coordinator = AutoTrainingCoordinator(
        settings=settings,
        candidates=store,
        snapshots=TrainingDatasetSnapshotBuilder(store, tmp_path / 'datasets'),
        registry=registry,
        backends={'fake': trainer},
        evaluator=evaluator or _Evaluator(),
        output_root=tmp_path / 'models',
    )
    return settings, registry, coordinator


def test_training_capture_is_on_by_default_and_owner_off_stops_new_candidates(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    assert settings.snapshot().training_capture is True
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    engine = IntelligenceEngine(
        _LegacyRouter(),
        settings_service=settings,
        capture_hook=TrainingCollector(store).capture,
    )

    assert engine.chat('one') == 'answer:one'
    assert store.stats()['total'] == 1
    settings.update(training_capture=False)
    assert engine.chat('two') == 'answer:two'
    assert store.stats()['total'] == 1
    store.close()


def test_secret_privacy_consent_provenance_and_quality_gates_fail_closed():
    factory = TrainingCandidateFactory()
    secret = factory.create(
        source_type='project', source_id='1', prompt='api_key=TOPSECRET123', response='ok',
        provenance='project:1', verifier_score=.95,
    )
    assert secret.contains_secret is True
    assert secret.training_eligible is False
    assert 'TOPSECRET123' not in secret.prompt

    private_without_consent = factory.create(
        source_type='project', source_id='2', prompt='q', response='a', privacy_level=PrivacyLevel.PRIVATE,
        provenance='project:2', verifier_score=.95,
    )
    assert private_without_consent.training_eligible is False
    assert 'consent_basis_required' in private_without_consent.reason_codes

    no_provenance = factory.create(
        source_type='project', source_id='3', prompt='q', response='a', verifier_score=.95,
    )
    assert no_provenance.training_eligible is False
    unverified = factory.create(
        source_type='project', source_id='4', prompt='q', response='a', provenance='project:4',
    )
    assert unverified.training_eligible is False
    assert 'quality_verification_required' in unverified.reason_codes


def test_dataset_versions_are_immutable_and_source_splits_do_not_leak(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 30)
    builder = TrainingDatasetSnapshotBuilder(store, tmp_path / 'datasets')
    first = builder.build(min_records=10)
    first_manifest = Path(first.manifest_path).read_text(encoding='utf-8')
    second = builder.build(min_records=10)
    assert second.snapshot_id == first.snapshot_id
    assert second.sha256 == first.sha256
    assert Path(second.manifest_path).read_text(encoding='utf-8') == first_manifest

    import json
    def sources(path):
        return {json.loads(line)['source_fingerprint'] for line in Path(path).read_text(encoding='utf-8').splitlines() if line}
    train, validation, test = sources(first.train_path), sources(first.validation_path), sources(first.test_path)
    assert train and validation and test
    assert not train & validation
    assert not train & test
    assert not validation & test
    store.close()


def test_auto_training_requires_minimum_new_examples_and_respects_cost_cap(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 10)
    trainer = _Trainer(cost=.25)
    settings, registry, coordinator = _coordinator(tmp_path, store, trainer, max_training_cost=1.0)
    first = coordinator.run_once()
    assert first is not None
    assert trainer.calls == 1
    assert coordinator.run_once() is None

    _approved(store, 10, 1)
    assert coordinator.run_once() is None
    _approved(store, 11, 1)
    second = coordinator.run_once()
    assert second is not None
    assert second.job_id != first.job_id
    assert trainer.calls == 2
    registry.close()
    store.close()

    other = tmp_path / 'cost-case'
    store2 = TrainingCandidateStore(other / 'candidates.sqlite3')
    _approved(store2, 0, 10)
    _, registry2, costly = _coordinator(other, store2, _Trainer(cost=5.0), max_training_cost=1.0)
    with pytest.raises(RuntimeError, match='cost exceeds'):
        costly.run_once()
    assert registry2.jobs() == ()
    registry2.close()
    store2.close()


def test_training_failure_is_persisted_without_promotion_or_activation(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 10)
    _, registry, coordinator = _coordinator(tmp_path, store, _Trainer(fail=True))
    with pytest.raises(RuntimeError, match='synthetic trainer failure'):
        coordinator.run_once()
    job = registry.jobs(limit=1)[0]
    assert job.status.value == 'failed'
    governed = registry.governance.job_public(job.job_id)
    assert governed['status'] == 'failed'
    assert governed['failure_reason'] == 'RuntimeError'
    assert registry.models() == ()
    registry.close()
    store.close()


def test_security_regression_fails_evaluation_and_cannot_be_promoted(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 10)
    settings, registry, coordinator = _coordinator(tmp_path, store, _Trainer(), _Evaluator(passed=True, safety=False))
    job = coordinator.run_once()
    model = registry.get_model(job.model_id)
    assert model is not None
    lifecycle = registry.governance.lifecycle(model.model_id)
    assert lifecycle['status'] == 'evaluation_failed'
    with pytest.raises(ValueError):
        registry.approve_promotion(model.model_id, owner_id='owner')
    registry.close()
    store.close()


def test_live_shadow_is_non_authoritative_and_requires_sufficient_evidence(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 10)
    settings, registry, coordinator = _coordinator(tmp_path, store, _Trainer())
    job = coordinator.run_once()
    model_id = job.model_id
    assert registry.governance.lifecycle(model_id)['status'] == 'shadow'
    registry.governance.record_shadow(
        model_id, request_id='r1', passed=True, quality_score=.95, baseline_quality_score=.90,
    )
    assert registry.governance.qualify_shadow(model_id, settings.snapshot()) is False
    summary = registry.governance.shadow_summary(model_id)
    assert summary['authoritative'] is False
    registry.governance.record_shadow(
        model_id, request_id='r2', passed=True, quality_score=.96, baseline_quality_score=.90,
    )
    assert registry.governance.qualify_shadow(model_id, settings.snapshot()) is True
    assert registry.governance.lifecycle(model_id)['status'] == 'candidate'
    registry.close()
    store.close()


def test_performance_history_is_task_specific_confidence_bounded_and_decays():
    tracker = ModelPerformanceTracker(full_weight_samples=20, recency_half_life_days=10)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    profile = tracker.record(PerformanceObservation(
        task_domain='coding', task_complexity='high', specialist_role='reviewer',
        provider_id='p', model_id='m', success=True, verifier_score=.9,
        tool_agreement=.8, explicit_feedback=1.0, observed_at=old,
    ))
    assert profile.sample_confidence == pytest.approx(.05)
    assert profile.recency_weight < .1
    assert profile.learning_influence < .005
    assert tracker.profile('coding', 'p', 'm', task_complexity='medium', specialist_role='reviewer') is None


def test_auto_mode_uses_sufficient_poor_history_only_as_bounded_escalation(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='auto', performance_learning=True)
    tracker = ModelPerformanceTracker(full_weight_samples=20)
    for _ in range(6):
        tracker.record(PerformanceObservation(
            task_domain='coding', task_complexity='medium', specialist_role='general',
            provider_id='p', model_id='m', success=False,
        ))
    engine = IntelligenceEngine(_LegacyRouter(), settings_service=settings, performance=tracker)
    from models.contracts import ModelRequest
    request = ModelRequest(prompt='code', routing_policy='coding', metadata={'task_domain': 'coding', 'task_complexity': 'medium'})
    assert engine.mode_for(request) is IntelligenceMode.DEEP


def test_source_revocation_preserves_audit_lineage_and_identifies_affected_models(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    _approved(store, 0, 10)
    settings, registry, coordinator = _coordinator(tmp_path, store, _Trainer())
    job = coordinator.run_once()
    first = store.approved()[0]
    affected_before = registry.governance.affected_models_for_source(first.source_fingerprint)
    assert any(item['model_id'] == job.model_id for item in affected_before)

    source_id = next(f'source-{i}' for i in range(10) if store.source_fingerprint('explicit_owner_feedback', f'source-{i}') == first.source_fingerprint)
    assert store.tombstone_source('explicit_owner_feedback', source_id) == 1
    affected = registry.governance.revoke_source(first.source_fingerprint, 'owner_deleted_source')
    assert any(item['model_id'] == job.model_id for item in affected)
    assert store.source_candidates('explicit_owner_feedback', source_id)[0].training_eligible is False
    assert registry.governance.affected_models_for_source(first.source_fingerprint)
    registry.close()
    store.close()


def test_owner_self_improvement_ui_is_responsive_and_exposes_correct_governance():
    assert 'Training Capture' in SELF_IMPROVEMENT_JS
    assert 'ON by default' in SELF_IMPROVEMENT_JS
    assert 'Performance learning' in SELF_IMPROVEMENT_JS
    assert 'Live shadow minimum samples' in SELF_IMPROVEMENT_JS
    assert 'Automatic rollback' in SELF_IMPROVEMENT_JS
    assert '@media(max-width:720px)' in SELF_IMPROVEMENT_JS
    assert 'No automatic public or Hugging Face publishing' in SELF_IMPROVEMENT_JS
    assert 'auto-merge' in SELF_IMPROVEMENT_JS
