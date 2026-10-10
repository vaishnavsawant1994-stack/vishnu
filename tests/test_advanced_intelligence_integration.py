from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.preferences import Preferences
from models.contracts import ModelRequest, ModelResponse, UsageRecord
from models.intelligence import IntelligenceEngine
from models.intelligence_modes import IntelligenceMode
from models.intelligence_settings import IntelligenceSettingsService
from models.performance import ModelPerformanceTracker, PerformanceObservation
from server.owner_intelligence_api import owner_intelligence_router
from server.owner_intelligence_ui import JS as OWNER_INTELLIGENCE_JS
from training import TrainingCandidateFactory, TrainingCandidateStore, TrainingDatasetExporter


class FakeRouter:
    def __init__(self):
        self.chat_calls = []
        self.json_calls = []
        self.requests = []
        self.primary = 'local'
        self.fallbacks = []
        self.providers = {}

    def chat(self, prompt, **kwargs):
        self.chat_calls.append((prompt, kwargs))
        return 'legacy-standard'

    def json(self, prompt, **kwargs):
        self.json_calls.append((prompt, kwargs))
        return {'legacy': True}

    def request(self, request):
        self.requests.append(request)
        return ModelResponse(
            request_id=request.request_id,
            provider_id='self_hosted',
            model_id='local-test-model',
            content='advanced-response',
            usage=UsageRecord(latency_ms=12.0, estimated_cost=0.0),
        )

    def status(self, *, probe=False):
        return {'state': 'available', 'probe': bool(probe)}


class FakeRegistry:
    def authenticate(self, device_id, token):
        return device_id == 'owner-device' and token == 'owner-token'

    def is_active(self, device_id):
        return device_id == 'owner-device'

    def authorize(self, device_id, scope):
        return device_id == 'owner-device' and scope == 'device:admin'


class FakeEvents:
    def __init__(self):
        self.events = []

    def emit(self, name, **payload):
        self.events.append((name, payload))


def test_intelligence_settings_persist_and_default_standard_is_safe(tmp_path):
    path = tmp_path / 'preferences.json'
    preferences = Preferences(path)
    service = IntelligenceSettingsService(preferences)
    initial = service.snapshot()
    assert initial.enabled is False
    assert initial.mode is IntelligenceMode.STANDARD
    assert initial.training_capture is False

    updated = service.update(
        enabled=True,
        mode='deep',
        auto_escalation=True,
        verification_enabled=True,
        training_capture=True,
        performance_learning=True,
        max_models=3,
        latency_preference='quality',
        max_cost_per_request=2.5,
    )
    assert updated.mode is IntelligenceMode.DEEP
    assert updated.max_models == 3
    assert updated.training_capture is True

    reloaded = IntelligenceSettingsService(Preferences(path)).snapshot()
    assert reloaded == updated
    assert reloaded.public()['model_output_authority'] is False


def test_standard_mode_preserves_legacy_chat_and_private_context_path(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    router = FakeRouter()
    engine = IntelligenceEngine(router, settings_service=IntelligenceSettingsService(preferences))

    result = engine.chat(
        'hello',
        system='system',
        private_context='owner-private-context',
        sensitivity='internal',
    )

    assert result == 'legacy-standard'
    assert not router.requests
    assert router.chat_calls == [(
        'hello',
        {
            'system': 'system',
            'history': None,
            'temperature': .3,
            'sensitivity': 'internal',
            'private_context': 'owner-private-context',
        },
    )]


def test_advanced_private_context_fails_closed_to_sensitive_typed_request(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='smart', auto_escalation=False, training_capture=False)
    router = FakeRouter()
    engine = IntelligenceEngine(router, settings_service=settings)

    result = engine.chat(
        'analyze',
        system='system',
        private_context='private project fact',
        sensitivity='internal',
        task_complexity='medium',
    )

    assert result == 'advanced-response'
    assert not router.chat_calls
    assert len(router.requests) == 1
    request = router.requests[0]
    assert isinstance(request, ModelRequest)
    assert request.sensitivity == 'sensitive'
    assert request.private_context == ''
    assert 'private project fact' in request.system
    assert 'never authorization' in request.system


def test_auto_escalation_keeps_simple_work_on_standard(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='research', auto_escalation=True)
    router = FakeRouter()
    engine = IntelligenceEngine(router, settings_service=settings)

    result = engine.chat('simple greeting', task_complexity='low')
    assert result == 'legacy-standard'
    assert not router.requests


def test_model_performance_learning_survives_restart(tmp_path):
    path = tmp_path / 'model-performance.sqlite3'
    tracker = ModelPerformanceTracker(path=path)
    profile = tracker.record(PerformanceObservation(
        task_domain='coding',
        provider_id='openai',
        model_id='test-model',
        success=True,
        verifier_score=.9,
        latency_ms=100,
        estimated_cost=.02,
        accepted=True,
    ))
    assert profile.samples == 1
    assert profile.learning_influence <= .5
    tracker.close()

    reopened = ModelPerformanceTracker(path=path)
    loaded = reopened.profile('coding', 'openai', 'test-model')
    assert loaded is not None
    assert loaded.samples == 1
    assert loaded.success_rate == 1.0
    assert loaded.public()['routing_authority'] is False
    reopened.close()


def test_export_contains_only_approved_eligible_candidates(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    factory = TrainingCandidateFactory()
    eligible = factory.create(
        source_type='explicit_owner_feedback',
        source_id='msg-1',
        prompt='Write a concise summary.',
        response='Concise summary.',
        privacy_level='internal',
        provenance='owner accepted response',
        provider_id='self_hosted',
        model_id='local-model',
    )
    blocked = factory.create(
        source_type='google_drive',
        source_id='drive-file-1',
        prompt='private source',
        response='private output',
        privacy_level='private',
        provenance='connected source',
        consent_basis='owner connected service',
    )
    store.save(eligible)
    store.save(blocked)
    store.approve(eligible.candidate_id)
    assert blocked.training_eligible is False

    exported = TrainingDatasetExporter(store, tmp_path / 'exports').export()
    records = [json.loads(line) for line in open(exported.dataset_path, encoding='utf-8') if line.strip()]
    manifest = json.load(open(exported.manifest_path, encoding='utf-8'))
    assert len(records) == 1
    assert records[0]['id'] == eligible.candidate_id
    assert blocked.candidate_id not in {row['id'] for row in records}
    assert manifest['contains_hidden_chain_of_thought'] is False
    assert manifest['automatic_publication'] is False
    store.close()


def test_owner_intelligence_pwa_api_requires_admin_scope_and_persists_settings(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    events = FakeEvents()
    settings = IntelligenceSettingsService(preferences, events=events)
    store = TrainingCandidateStore(tmp_path / 'training.sqlite3')
    runtime = {
        'device_registry': FakeRegistry(),
        'intelligence_settings': settings,
        'training_candidate_store': store,
        'training_dataset_exporter': TrainingDatasetExporter(store, tmp_path / 'exports'),
        'model_performance': ModelPerformanceTracker(),
        'models': FakeRouter(),
        'events': events,
        # No pwa_sessions in this isolated compatibility test; production adds
        # it and requires fresh verification for governance mutations.
    }
    app = FastAPI()
    app.include_router(owner_intelligence_router(runtime))
    client = TestClient(app)

    assert client.get('/iphone/api/owner/intelligence/summary').status_code == 401
    cookies = {'pa_device': 'owner-device', 'pa_token': 'owner-token'}
    response = client.patch(
        '/iphone/api/owner/intelligence/settings',
        cookies=cookies,
        json={'enabled': True, 'mode': 'smart', 'max_models': 2},
    )
    assert response.status_code == 200
    assert response.json()['settings']['mode'] == 'smart'
    assert IntelligenceSettingsService(Preferences(tmp_path / 'preferences.json')).snapshot().enabled is True
    store.close()


def test_owner_intelligence_ui_exposes_governed_controls_without_upload_path():
    assert 'Advanced Intelligence' in OWNER_INTELLIGENCE_JS
    assert '/owner/intelligence/training/export' in OWNER_INTELLIGENCE_JS
    assert '/owner/intelligence/training/candidates' in OWNER_INTELLIGENCE_JS
    assert 'automatic' not in '/owner/intelligence/training/export'
    assert 'upload' not in OWNER_INTELLIGENCE_JS.lower()
