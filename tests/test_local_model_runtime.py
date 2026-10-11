from __future__ import annotations

from types import SimpleNamespace

from server.trained_model_runtime_api import trained_model_runtime_router
from training.local_runtime import (
    LocalTransformersDeploymentBackend,
    attach_local_model_runtime,
    _token_f1,
)


class FakeRunner:
    def __init__(self, *, persistent: bool):
        self.persistent = persistent

    def available(self):
        return True, None


class BackendHolder:
    def __init__(self):
        self.backends = {}


class DeploymentHolder(BackendHolder):
    def status(self):
        return {'backends': {}}


class ShadowHolder(BackendHolder):
    def status(self):
        return {'backends': {}, 'authoritative': False}


def test_token_f1_is_bounded_and_exact_match_scores_one():
    assert _token_f1('alpha beta', 'alpha beta') == 1.0
    value = _token_f1('alpha beta', 'alpha gamma')
    assert 0.0 < value < 1.0


def test_ephemeral_deployment_is_fail_closed_unless_explicitly_allowed():
    runner = FakeRunner(persistent=False)
    backend = LocalTransformersDeploymentBackend(runner, allow_ephemeral_activation=False)
    ok, reason = backend.available()
    assert ok is False
    assert 'ephemeral' in str(reason)

    explicit = LocalTransformersDeploymentBackend(runner, allow_ephemeral_activation=True)
    ok, reason = explicit.available()
    assert ok is True
    assert reason is None


def test_attach_registers_shadow_and_deployment_backends_without_new_authority(tmp_path):
    shadow = ShadowHolder()
    deployment = DeploymentHolder()
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'events': None,
        'shadow_qualification': shadow,
        'model_deployment': deployment,
    }
    runner = FakeRunner(persistent=True)
    attach_local_model_runtime(runtime, enabled=True, persistent=True, runner=runner)

    assert runtime['trained_model_runtime'] is runner
    assert 'local_transformers' in shadow.backends
    assert 'local_transformers' in deployment.backends
    assert deployment.backends['local_transformers'].allow_ephemeral_activation is False


def test_runtime_router_registers_health_inference_and_release_boundaries(tmp_path):
    runtime = {
        'settings': SimpleNamespace(data_dir=tmp_path),
        'trained_model_runtime': object(),
        'model_deployment': DeploymentHolder(),
        'shadow_qualification': ShadowHolder(),
    }
    router = trained_model_runtime_router(runtime)
    paths = {route.path for route in router.routes}
    assert '/trained-model/health' in paths
    assert '/trained-model/qualification' in paths
    assert '/trained-model/v1/models' in paths
    assert '/trained-model/v1/chat/completions' in paths
    assert '/trained-model/release/deploy/{model_id}' in paths
    assert '/trained-model/release/rollback/{active_model_id}' in paths
