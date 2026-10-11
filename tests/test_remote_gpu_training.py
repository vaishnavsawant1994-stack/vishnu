from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from training.remote_gpu import (
    RemoteGpuProviderCapabilities,
    RemoteGpuTrainerBackend,
    RemoteGpuTrainingPolicy,
    RemoteTrainingJob,
    RemoteTrainingResult,
    RemoteTrainingState,
    _tree_digest,
)
from training.self_improvement import TrainingDatasetSnapshot, TrainingMethod


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += float(seconds)


class FakeProvider:
    provider_id = "test-gpu"

    def __init__(
        self,
        *,
        states=None,
        capabilities=None,
        available=True,
        estimate=1.0,
        accrued=1.0,
        actual=1.0,
        cleanup_ok=True,
        digest_ok=True,
    ) -> None:
        self._states = list(states or [RemoteTrainingState.RUNNING, RemoteTrainingState.SUCCEEDED])
        self._capabilities = capabilities or RemoteGpuProviderCapabilities(True, True, True, True, True)
        self._available = available
        self.estimate = estimate
        self.accrued = accrued
        self.actual = actual
        self.cleanup_ok = cleanup_ok
        self.digest_ok = digest_ok
        self.cancelled = 0
        self.cleaned = 0
        self.submitted = None
        self.status_calls = 0

    def available(self):
        return self._available, None if self._available else "provider_offline"

    def capabilities(self):
        return self._capabilities

    def submit(self, request):
        self.submitted = request
        state = self._states[0] if self._states else RemoteTrainingState.SUCCEEDED
        return RemoteTrainingJob("job-1", state, self.estimate, 0.0)

    def status(self, job_id):
        assert job_id == "job-1"
        self.status_calls += 1
        if len(self._states) > 1:
            self._states.pop(0)
        state = self._states[0] if self._states else RemoteTrainingState.SUCCEEDED
        detail = "provider_failed" if state is RemoteTrainingState.FAILED else ""
        return RemoteTrainingJob(job_id, state, self.estimate, self.accrued, detail)

    def cancel(self, job_id):
        assert job_id == "job-1"
        self.cancelled += 1

    def materialize_result(self, job_id, target_dir: Path):
        assert job_id == "job-1"
        checkpoint = target_dir / "checkpoint"
        checkpoint.mkdir()
        (checkpoint / "adapter_model.safetensors").write_bytes(b"weights")
        (checkpoint / "adapter_config.json").write_text("{}", encoding="utf-8")
        digest = _tree_digest(checkpoint)
        if not self.digest_ok:
            digest = "0" * 64
        return RemoteTrainingResult(
            checkpoint_path=str(checkpoint),
            checkpoint_sha256=digest,
            metrics={"quality_score": 0.91},
            actual_cost=self.actual,
        )

    def cleanup(self, job_id):
        assert job_id == "job-1"
        self.cleaned += 1
        return self.cleanup_ok


def _snapshot(tmp_path, *, hidden_cot=False) -> TrainingDatasetSnapshot:
    root = tmp_path / "dataset"
    root.mkdir()
    train = root / "train.jsonl"
    validation = root / "validation.jsonl"
    test = root / "test.jsonl"
    train.write_text('{"instruction":"x","response":"y"}\n', encoding="utf-8")
    validation.write_text('', encoding="utf-8")
    test.write_text('', encoding="utf-8")
    digest = "a" * 64
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_sha256": digest,
                "contains_hidden_chain_of_thought": hidden_cot,
                "automatic_publication": False,
            }
        ),
        encoding="utf-8",
    )
    return TrainingDatasetSnapshot(
        snapshot_id="ds-test",
        created_at="2026-10-11T00:00:00+00:00",
        dataset_name="test",
        root=str(root),
        train_path=str(train),
        validation_path=str(validation),
        test_path=str(test),
        manifest_path=str(manifest),
        records=1,
        train_records=1,
        validation_records=0,
        test_records=0,
        sha256=digest,
    )


def _settings(*, max_cost=10.0, max_runtime=120, method=TrainingMethod.LORA):
    return SimpleNamespace(
        base_model="base/model",
        method=method,
        hyperparameters={"learning_rate": 0.0002, "lora_r": 8},
        max_runtime_seconds=max_runtime,
        max_training_cost=max_cost,
    )


def _backend(provider, *, clock=None, policy=None):
    clock = clock or FakeClock()
    return RemoteGpuTrainerBackend(
        provider,
        policy=policy or RemoteGpuTrainingPolicy(
            allow_remote_dataset_transfer=True,
            maximum_runtime_seconds=120,
            maximum_cost=10.0,
            poll_interval_seconds=1.0,
        ),
        clock=clock.now,
        sleep=clock.sleep,
    )


def test_remote_training_is_disabled_without_explicit_owner_dataset_transfer_consent(tmp_path):
    provider = FakeProvider()
    backend = RemoteGpuTrainerBackend(provider)
    available, reason = backend.available()
    assert available is False
    assert "not enabled" in reason
    with pytest.raises(RuntimeError, match="not enabled"):
        backend.train(_snapshot(tmp_path), _settings(), tmp_path / "out")


def test_provider_security_capabilities_fail_closed():
    provider = FakeProvider(capabilities=RemoteGpuProviderCapabilities(True, True, False, True, True))
    backend = _backend(provider)
    available, reason = backend.available()
    assert available is False
    assert "dataset_deletion" in reason


def test_remote_gpu_success_returns_verified_local_checkpoint(tmp_path):
    provider = FakeProvider()
    clock = FakeClock()
    backend = _backend(provider, clock=clock)

    artifact = backend.train(_snapshot(tmp_path), _settings(), tmp_path / "out")

    checkpoint = Path(artifact.checkpoint_ref)
    assert checkpoint.is_dir()
    assert artifact.backend_id == "remote_gpu:test-gpu"
    assert artifact.base_model == "base/model"
    assert artifact.method == "lora"
    assert artifact.metrics["quality_score"] == 0.91
    assert artifact.metrics["remote_provider_id"] == "test-gpu"
    assert artifact.metrics["remote_job_id"] == "job-1"
    assert artifact.metrics["remote_dataset_cleanup_confirmed"] is True
    assert artifact.metrics["provider_credentials_persisted"] is False
    assert artifact.metrics["checkpoint_sha256"] == _tree_digest(checkpoint)
    assert provider.cleaned == 1
    assert provider.cancelled == 0

    public_request = provider.submitted.public()
    assert "train_path" not in public_request
    assert "validation_path" not in public_request
    assert "test_path" not in public_request
    assert public_request["dataset_sha256"] == "a" * 64


def test_submit_estimate_above_owner_cost_ceiling_is_cancelled(tmp_path):
    provider = FakeProvider(estimate=11.0, accrued=0.0)
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="cost exceeds"):
        backend.train(_snapshot(tmp_path), _settings(max_cost=10.0), tmp_path / "out")
    assert provider.cancelled >= 1
    assert provider.cleaned >= 1


def test_running_job_crossing_cost_ceiling_is_cancelled(tmp_path):
    provider = FakeProvider(states=[RemoteTrainingState.RUNNING, RemoteTrainingState.RUNNING], estimate=5.0, accrued=12.0)
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="cost exceeds"):
        backend.train(_snapshot(tmp_path), _settings(max_cost=10.0), tmp_path / "out")
    assert provider.cancelled >= 1
    assert provider.cleaned >= 1


def test_remote_training_timeout_cancels_job(tmp_path):
    provider = FakeProvider(states=[RemoteTrainingState.RUNNING, RemoteTrainingState.RUNNING, RemoteTrainingState.RUNNING])
    clock = FakeClock()
    backend = RemoteGpuTrainerBackend(
        provider,
        policy=RemoteGpuTrainingPolicy(
            allow_remote_dataset_transfer=True,
            maximum_runtime_seconds=60,
            maximum_cost=10.0,
            poll_interval_seconds=30.0,
        ),
        clock=clock.now,
        sleep=clock.sleep,
    )
    with pytest.raises(TimeoutError, match="maximum runtime"):
        backend.train(_snapshot(tmp_path), _settings(max_runtime=60), tmp_path / "out")
    assert provider.cancelled >= 1
    assert provider.cleaned >= 1


def test_failed_remote_job_is_not_registered_as_artifact(tmp_path):
    provider = FakeProvider(states=[RemoteTrainingState.RUNNING, RemoteTrainingState.FAILED])
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="provider_failed"):
        backend.train(_snapshot(tmp_path), _settings(), tmp_path / "out")
    assert provider.cleaned >= 1


def test_checkpoint_digest_mismatch_fails_closed(tmp_path):
    provider = FakeProvider(digest_ok=False)
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="integrity mismatch"):
        backend.train(_snapshot(tmp_path), _settings(), tmp_path / "out")
    assert provider.cleaned >= 1


def test_provider_must_confirm_remote_dataset_cleanup(tmp_path):
    provider = FakeProvider(cleanup_ok=False)
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="cleanup"):
        backend.train(_snapshot(tmp_path), _settings(), tmp_path / "out")
    assert provider.cleaned >= 1


def test_hidden_chain_of_thought_snapshot_is_rejected_before_submit(tmp_path):
    provider = FakeProvider()
    backend = _backend(provider)
    with pytest.raises(RuntimeError, match="hidden chain of thought"):
        backend.train(_snapshot(tmp_path, hidden_cot=True), _settings(), tmp_path / "out")
    assert provider.submitted is None


def test_remote_method_allowlist_is_enforced(tmp_path):
    provider = FakeProvider()
    policy = RemoteGpuTrainingPolicy(
        allow_remote_dataset_transfer=True,
        maximum_runtime_seconds=120,
        maximum_cost=10.0,
        poll_interval_seconds=0,
        allowed_methods=(TrainingMethod.LORA,),
    )
    backend = _backend(provider, policy=policy)
    with pytest.raises(ValueError, match="not allowed"):
        backend.train(_snapshot(tmp_path), _settings(method=TrainingMethod.FULL), tmp_path / "out")
    assert provider.submitted is None


def test_remote_backend_uses_stricter_of_owner_and_provider_limits(tmp_path):
    provider = FakeProvider()
    policy = RemoteGpuTrainingPolicy(
        allow_remote_dataset_transfer=True,
        maximum_runtime_seconds=90,
        maximum_cost=4.0,
        poll_interval_seconds=0,
    )
    backend = _backend(provider, policy=policy)
    backend.train(_snapshot(tmp_path), _settings(max_cost=8.0, max_runtime=120), tmp_path / "out")
    assert provider.submitted.maximum_runtime_seconds == 90
    assert provider.submitted.maximum_cost == 4.0
