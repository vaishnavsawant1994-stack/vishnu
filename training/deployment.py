from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from training.self_improvement import TrainedModelStatus


@dataclass(frozen=True)
class DeploymentResult:
    checkpoint_ref: str
    deployment_ref: str
    metadata: dict[str, Any]


class ModelDeploymentBackend(Protocol):
    backend_id: str
    def available(self) -> tuple[bool, str | None]: ...
    def deploy(self, model) -> DeploymentResult: ...
    def running_checkpoint(self, deployment_ref: str) -> str | None: ...


class UnavailableDeploymentBackend:
    backend_id = 'unavailable'
    def available(self) -> tuple[bool, str | None]:
        return False, 'no trained-model deployment backend is configured'
    def deploy(self, model):
        raise RuntimeError('no trained-model deployment backend is configured')
    def running_checkpoint(self, deployment_ref: str) -> str | None:
        return None


class ModelDeploymentController:
    """Separate release boundary for an owner-approved trained checkpoint.

    Training/evaluation cannot call this controller implicitly. Deployment is
    permitted only for a model already marked OWNER_APPROVED, and activation is
    recorded only after the serving backend proves the exact approved checkpoint
    is running. The controller cannot approve a model itself.
    """

    def __init__(self, registry, *, backends: dict[str, ModelDeploymentBackend] | None = None, events=None) -> None:
        self.registry = registry
        self.backends = dict(backends or {})
        self.events = events

    def backend_status(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for backend_id, backend in self.backends.items():
            available, reason = backend.available()
            result[backend_id] = {'available': bool(available), 'reason': reason}
        return result

    def deploy(self, model_id: str, *, backend_id: str, actor: str = 'release_controller'):
        model = self.registry.get_model(model_id)
        if model is None:
            raise KeyError(model_id)
        if model.status is not TrainedModelStatus.OWNER_APPROVED:
            raise ValueError('owner promotion approval is required before model deployment')
        backend = self.backends.get(str(backend_id))
        if backend is None:
            raise RuntimeError(f'deployment backend unavailable: {backend_id}')
        available, reason = backend.available()
        if not available:
            raise RuntimeError(reason or f'deployment backend unavailable: {backend_id}')
        result = backend.deploy(model)
        if str(result.checkpoint_ref) != str(model.checkpoint_ref):
            raise ValueError('deployment backend returned a checkpoint different from the approved model')
        running = backend.running_checkpoint(result.deployment_ref)
        if str(running or '') != str(model.checkpoint_ref):
            raise RuntimeError('deployment backend could not prove the exact approved checkpoint is running')
        activated = self.registry.confirm_activation(
            model_id,
            checkpoint_ref=model.checkpoint_ref,
            actor=str(actor or 'release_controller'),
        )
        if self.events is not None:
            self.events.emit(
                'training.model_activated',
                model_id=model_id,
                backend_id=backend_id,
                deployment_ref=result.deployment_ref,
                checkpoint_ref=model.checkpoint_ref,
                actor=str(actor or 'release_controller'),
            )
        return activated, result

    def status(self) -> dict[str, Any]:
        return {
            'backends': self.backend_status(),
            'owner_approval_required': True,
            'exact_checkpoint_confirmation_required': True,
            'automatic_owner_approval': False,
            'automatic_production_activation': False,
        }
