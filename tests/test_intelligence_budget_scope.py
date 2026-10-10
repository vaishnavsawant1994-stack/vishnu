from core.preferences import Preferences
from models.contracts import ModelRequest, ModelResponse
from models.intelligence import IntelligenceEngine
from models.intelligence_settings import IntelligenceSettingsService


class _Router:
    def __init__(self):
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        return ModelResponse(request.request_id, 'local', 'test-model', content='ok')


def test_owner_cost_limit_gets_request_unique_execution_scope(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(
        enabled=True,
        mode='smart',
        auto_escalation=False,
        max_cost_per_request=1.50,
        training_capture=False,
    )
    router = _Router()
    engine = IntelligenceEngine(router, settings_service=settings)
    original = ModelRequest(
        prompt='analyze',
        metadata={'task_complexity': 'medium', 'task_domain': 'analysis'},
    )

    response = engine.request(original)

    assert response.content == 'ok'
    assert len(router.requests) == 1
    bounded = router.requests[0]
    assert bounded.request_id == original.request_id
    assert bounded.execution_id == f'intelligence:{original.request_id}'
    assert bounded.max_cost == 1.50
