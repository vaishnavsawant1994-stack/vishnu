from types import SimpleNamespace

from models.contracts import ModelRequest, ModelResponse
from models.intelligence import IntelligenceEngine
from models.intelligence_modes import IntelligenceMode
from training import PrivacyLevel, TrainingCandidateFactory, TrainingCandidateStore, TrainingCollector


class _Router:
    def __init__(self):
        self.settings = SimpleNamespace(multi_model_deliberation_enabled=False, model_max_parallel_calls=4)
        self.calls = 0

    def request(self, request):
        self.calls += 1
        return ModelResponse(request.request_id, 'local', 'test-model', content='grounded proposal')


def test_intelligence_engine_defaults_to_standard_and_accepts_focused_alias():
    engine = IntelligenceEngine(_Router())
    standard = ModelRequest(prompt='hello')
    focused = ModelRequest(prompt='analyze', metadata={'intelligence_mode': 'focused', 'task_complexity': 'high'})

    assert engine.mode_for(standard) is IntelligenceMode.STANDARD
    assert engine.should_handle(standard) is False
    assert engine.mode_for(focused) is IntelligenceMode.SMART
    assert engine.should_handle(focused) is True


def test_smart_mode_runs_advisory_verification_without_granting_authority():
    router = _Router()
    engine = IntelligenceEngine(router)
    request = ModelRequest(
        prompt='check this',
        metadata={
            'intelligence_mode': 'smart',
            'task_complexity': 'critical',
            'evidence_required': True,
            'verification_evidence': {
                'task_correctness': 1.0,
                'constraint_compliance': 1.0,
                'evidence_support': 1.0,
            },
        },
    )

    response = engine.request(request)

    assert response.content == 'grounded proposal'
    assert router.calls == 1
    assert engine.last_outcome is not None
    assert engine.last_outcome.verification is not None
    assert engine.last_outcome.verification.passed is True
    assert 'verification_is_not_authorization' in engine.last_outcome.verification.reason_codes


def test_training_store_persists_approved_candidates_and_tombstones_source(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    candidate = TrainingCandidateFactory().create(
        source_type='project',
        source_id='source-1',
        prompt='question',
        response='answer',
        privacy_level=PrivacyLevel.INTERNAL,
        provenance='project:source-1',
        consent_basis='owner-training-policy',
    )
    store.save(candidate)
    approved = store.approve(candidate.candidate_id)

    assert approved.training_eligible is True
    assert len(store.approved()) == 1
    assert store.tombstone_source('project', 'source-1') == 1
    tombstoned = store.get(candidate.candidate_id)
    assert tombstoned is not None
    assert tombstoned.training_eligible is False
    assert tombstoned.prompt == ''
    assert tombstoned.response == ''
    assert store.approved() == ()
    store.close()


def test_collector_never_silently_captures_model_exchange(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    collector = TrainingCollector(store)
    request = ModelRequest(prompt='private question')
    response = ModelResponse(request.request_id, 'local', 'model', content='private answer')

    assert collector.capture(request, response, None, SimpleNamespace()) is None
    store.close()


def test_explicit_training_metadata_captures_sanitized_candidate(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    collector = TrainingCollector(store)
    request = ModelRequest(
        prompt='Explain the verified result',
        metadata={
            'training_source_id': 'work-1',
            'training_source_type': 'project',
            'training_provenance': 'project:work-1',
            'training_consent_basis': 'owner-training-policy',
            'training_source_allowed': True,
        },
    )
    response = ModelResponse(request.request_id, 'local', 'model', content='Use the verified evidence.')

    candidate = collector.capture(request, response, None, SimpleNamespace())

    assert candidate is not None
    assert candidate.training_eligible is True
    assert store.get(candidate.candidate_id) is not None
    store.close()


def test_connected_service_source_is_ineligible_even_when_capture_requested(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    collector = TrainingCollector(store)
    request = ModelRequest(
        prompt='summarize mail',
        metadata={
            'training_source_id': 'mail-1',
            'training_source_type': 'gmail',
            'training_provenance': 'gmail:mail-1',
            'training_consent_basis': 'owner-training-policy',
            'training_source_allowed': True,
        },
    )
    response = ModelResponse(request.request_id, 'local', 'model', content='summary')

    candidate = collector.capture(request, response, None, SimpleNamespace())

    assert candidate is not None
    assert candidate.training_eligible is False
    assert 'source_training_not_allowed' in candidate.reason_codes
    store.close()
