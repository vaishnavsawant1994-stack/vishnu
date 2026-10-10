from types import SimpleNamespace

from models.contracts import ModelRequest, ModelResponse
from models.deliberation import DeliberationEngine


class _Router:
    def __init__(self):
        self.settings = SimpleNamespace(
            multi_model_deliberation_enabled=False,
            model_max_parallel_calls=4,
        )
        self.eligible_calls = 0
        self.request_calls = 0

    def eligible_providers(self, capability, sensitivity):
        self.eligible_calls += 1
        return []

    def request(self, request):
        self.request_calls += 1
        return ModelResponse(request.request_id, 'local', 'test-model', content='single')


def test_legacy_deliberation_still_respects_environment_gate():
    router = _Router()
    result = DeliberationEngine(router, max_models=5).run(ModelRequest(prompt='task'))
    assert result.mode == 'single'
    assert router.eligible_calls == 0
    assert router.request_calls == 1


def test_owner_enabled_override_activates_bounded_deliberation_path():
    router = _Router()
    engine = DeliberationEngine(router, max_models=99, enabled=True)
    result = engine.run(ModelRequest(prompt='task'), mode='consensus')

    assert engine.max_models == 5
    assert router.eligible_calls == 1
    assert router.request_calls == 1
    assert result.mode == 'single'
    assert result.failures == ('insufficient_distinct_providers',)
