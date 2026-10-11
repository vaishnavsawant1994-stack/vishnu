from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from training.self_improvement import TrainingArtifact, TrainingDatasetSnapshot, TrainingMethod


class RemoteTrainingState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RemoteGpuProviderCapabilities:
    encrypted_transport: bool
    isolated_jobs: bool
    dataset_deletion: bool
    artifact_integrity: bool
    cost_reporting: bool

    def production_ready(self) -> tuple[bool, tuple[str, ...]]:
        missing: list[str] = []
        for name in (
            "encrypted_transport",
            "isolated_jobs",
            "dataset_deletion",
            "artifact_integrity",
            "cost_reporting",
        ):
            if not bool(getattr(self, name)):
                missing.append(name)
        return not missing, tuple(missing)


@dataclass(frozen=True)
class RemoteGpuTrainingPolicy:
    allow_remote_dataset_transfer: bool = False
    maximum_runtime_seconds: int = 6 * 3600
    maximum_cost: float | None = None
    poll_interval_seconds: float = 5.0
    allowed_methods: tuple[TrainingMethod, ...] = (
        TrainingMethod.LORA,
        TrainingMethod.QLORA,
        TrainingMethod.FULL,
    )

    def __post_init__(self) -> None:
        if not 60 <= int(self.maximum_runtime_seconds) <= 7 * 24 * 3600:
            raise ValueError("maximum_runtime_seconds must be between 60 and 604800")
        if self.maximum_cost is not None and not 0 < float(self.maximum_cost) <= 1_000_000:
            raise ValueError("maximum_cost must be positive or null")
        if not 0 <= float(self.poll_interval_seconds) <= 300:
            raise ValueError("poll_interval_seconds must be between 0 and 300")
        if not self.allowed_methods:
            raise ValueError("allowed_methods cannot be empty")


@dataclass(frozen=True)
class RemoteTrainingRequest:
    request_id: str
    snapshot_id: str
    dataset_sha256: str
    train_path: str
    validation_path: str | None
    test_path: str | None
    base_model: str
    method: TrainingMethod
    hyperparameters: dict[str, Any]
    maximum_runtime_seconds: int
    maximum_cost: float | None

    def public(self) -> dict[str, Any]:
        # Local dataset paths are deliberately omitted. Provider adapters receive
        # them in-process but must never expose workstation paths in telemetry.
        return {
            "request_id": self.request_id,
            "snapshot_id": self.snapshot_id,
            "dataset_sha256": self.dataset_sha256,
            "base_model": self.base_model,
            "method": self.method.value,
            "hyperparameters": dict(self.hyperparameters),
            "maximum_runtime_seconds": self.maximum_runtime_seconds,
            "maximum_cost": self.maximum_cost,
        }


@dataclass(frozen=True)
class RemoteTrainingJob:
    job_id: str
    state: RemoteTrainingState
    estimated_cost: float | None = None
    accrued_cost: float | None = None
    detail: str = ""


@dataclass(frozen=True)
class RemoteTrainingResult:
    checkpoint_path: str
    checkpoint_sha256: str
    metrics: dict[str, Any]
    actual_cost: float | None = None


class RemoteGpuProvider(Protocol):
    provider_id: str

    def available(self) -> tuple[bool, str | None]: ...

    def capabilities(self) -> RemoteGpuProviderCapabilities: ...

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingJob: ...

    def status(self, job_id: str) -> RemoteTrainingJob: ...

    def cancel(self, job_id: str) -> None: ...

    def materialize_result(self, job_id: str, target_dir: Path) -> RemoteTrainingResult: ...

    def cleanup(self, job_id: str) -> bool: ...


def _validate_snapshot(snapshot: TrainingDatasetSnapshot) -> None:
    if not snapshot.snapshot_id or not snapshot.sha256:
        raise ValueError("training snapshot metadata is incomplete")
    for path_value, required in (
        (snapshot.manifest_path, True),
        (snapshot.train_path, True),
        (snapshot.validation_path, snapshot.validation_records > 0),
        (snapshot.test_path, snapshot.test_records > 0),
    ):
        path = Path(path_value).expanduser().resolve()
        if required and (not path.is_file() or path.is_symlink()):
            raise RuntimeError(f"training snapshot file missing or unsafe: {path.name}")
    try:
        manifest = json.loads(Path(snapshot.manifest_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("training snapshot manifest is unreadable") from exc
    if str(manifest.get("dataset_sha256") or "") != snapshot.sha256:
        raise RuntimeError("training snapshot manifest digest mismatch")
    if bool(manifest.get("contains_hidden_chain_of_thought", True)):
        raise RuntimeError("remote training snapshot must exclude hidden chain of thought")
    if bool(manifest.get("automatic_publication", True)):
        raise RuntimeError("remote training snapshot cannot enable automatic publication")


def _tree_digest(root: Path) -> str:
    root = root.expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("remote training checkpoint must be a real directory")
    entries: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise RuntimeError("remote training checkpoint contains a symlink")
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise RuntimeError("remote training checkpoint escaped its output root") from exc
        digest = sha256(path.read_bytes()).hexdigest()
        entries.append(f"{relative}\0{path.stat().st_size}\0{digest}\n")
    if not entries:
        raise RuntimeError("remote training checkpoint is empty")
    return sha256("".join(entries).encode("utf-8")).hexdigest()


def _bounded_hyperparameters(settings: Any) -> dict[str, Any]:
    raw = getattr(settings, "hyperparameters", {}) or {}
    if not isinstance(raw, dict):
        raise ValueError("training hyperparameters must be an object")
    # The provider receives only the same bounded owner surface accepted by the
    # local controlled trainer. Unknown values are rejected rather than copied.
    from training.runtime_controls import BoundedLocalPeftTrainerBackend

    return BoundedLocalPeftTrainerBackend.normalized_hyperparameters(settings)


def _minimum_optional(left: float | None, right: float | None) -> float | None:
    values = [float(item) for item in (left, right) if item is not None]
    return min(values) if values else None


class RemoteGpuTrainerBackend:
    """Governed synchronous bridge to an owner-configured remote GPU provider.

    Provider credentials live inside the injected provider adapter and never in
    requests, datasets, registry rows, or training artifacts. The backend only
    transfers a previously governed immutable dataset snapshot when the owner
    explicitly enables remote dataset transfer. It enforces both the global
    owner training ceilings and the remote-provider-specific ceilings, cancels
    on timeout/cost breach, verifies the downloaded checkpoint tree digest, and
    requires provider-side dataset/job cleanup before returning an artifact.
    """

    def __init__(
        self,
        provider: RemoteGpuProvider,
        *,
        policy: RemoteGpuTrainingPolicy | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.provider = provider
        self.policy = policy or RemoteGpuTrainingPolicy()
        self.backend_id = f"remote_gpu:{str(provider.provider_id).strip()}"
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        if not str(provider.provider_id).strip():
            raise ValueError("remote GPU provider_id is required")

    def available(self) -> tuple[bool, str | None]:
        if not self.policy.allow_remote_dataset_transfer:
            return False, "owner has not enabled remote training dataset transfer"
        available, reason = self.provider.available()
        if not available:
            return False, reason or "remote GPU provider unavailable"
        ready, missing = self.provider.capabilities().production_ready()
        if not ready:
            return False, "remote GPU provider missing required capability: " + ",".join(missing)
        return True, None

    def _limits(self, settings: Any) -> tuple[int, float | None]:
        settings_runtime = int(getattr(settings, "max_runtime_seconds", self.policy.maximum_runtime_seconds))
        runtime = min(settings_runtime, int(self.policy.maximum_runtime_seconds))
        settings_cost = getattr(settings, "max_training_cost", None)
        cost = _minimum_optional(settings_cost, self.policy.maximum_cost)
        return runtime, cost

    @staticmethod
    def _check_cost(value: float | None, maximum: float | None) -> None:
        if value is None or maximum is None:
            return
        if float(value) > float(maximum):
            raise RuntimeError("remote training cost exceeds owner maximum")

    def train(self, snapshot: TrainingDatasetSnapshot, settings: Any, output_dir: Path) -> TrainingArtifact:
        available, reason = self.available()
        if not available:
            raise RuntimeError(reason or "remote GPU provider unavailable")
        _validate_snapshot(snapshot)
        method = TrainingMethod(getattr(settings, "method"))
        if method not in self.policy.allowed_methods:
            raise ValueError(f"training method is not allowed for remote GPU backend: {method.value}")
        base_model = str(getattr(settings, "base_model", "") or "").strip()
        if not base_model:
            raise ValueError("base_model is required for remote GPU training")
        runtime_limit, cost_limit = self._limits(settings)
        hyperparameters = _bounded_hyperparameters(settings)
        request = RemoteTrainingRequest(
            request_id=f"remote-train-{uuid4().hex[:20]}",
            snapshot_id=snapshot.snapshot_id,
            dataset_sha256=snapshot.sha256,
            train_path=str(Path(snapshot.train_path).resolve()),
            validation_path=str(Path(snapshot.validation_path).resolve()) if snapshot.validation_records else None,
            test_path=str(Path(snapshot.test_path).resolve()) if snapshot.test_records else None,
            base_model=base_model,
            method=method,
            hyperparameters=hyperparameters,
            maximum_runtime_seconds=runtime_limit,
            maximum_cost=cost_limit,
        )
        job = self.provider.submit(request)
        if not str(job.job_id).strip():
            raise RuntimeError("remote GPU provider returned an empty job id")
        job_id = job.job_id
        started = self._clock()
        cancelled = False
        cleanup_required = True
        succeeded = False
        try:
            self._check_cost(job.estimated_cost, cost_limit)
            self._check_cost(job.accrued_cost, cost_limit)
            current = job
            while current.state in {RemoteTrainingState.QUEUED, RemoteTrainingState.RUNNING}:
                elapsed = self._clock() - started
                if elapsed >= runtime_limit:
                    self.provider.cancel(job_id)
                    cancelled = True
                    raise TimeoutError("remote training exceeded owner maximum runtime")
                self._sleep(float(self.policy.poll_interval_seconds))
                current = self.provider.status(job_id)
                self._check_cost(current.estimated_cost, cost_limit)
                try:
                    self._check_cost(current.accrued_cost, cost_limit)
                except RuntimeError:
                    self.provider.cancel(job_id)
                    cancelled = True
                    raise

            if current.state is RemoteTrainingState.CANCELLED:
                raise RuntimeError("remote training was cancelled")
            if current.state is RemoteTrainingState.FAILED:
                raise RuntimeError(current.detail or "remote training failed")
            if current.state is not RemoteTrainingState.SUCCEEDED:
                raise RuntimeError(f"unsupported remote training state: {current.state}")
            self._check_cost(current.accrued_cost, cost_limit)

            output_dir = Path(output_dir).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            materialized_root = output_dir / "remote-result"
            if materialized_root.exists():
                raise FileExistsError(materialized_root)
            materialized_root.mkdir(parents=False, exist_ok=False)
            result = self.provider.materialize_result(job_id, materialized_root)
            checkpoint = Path(result.checkpoint_path).expanduser().resolve()
            try:
                checkpoint.relative_to(materialized_root)
            except ValueError as exc:
                raise RuntimeError("remote provider materialized checkpoint outside output directory") from exc
            digest = _tree_digest(checkpoint)
            if digest != str(result.checkpoint_sha256).lower():
                raise RuntimeError("remote training checkpoint integrity mismatch")
            self._check_cost(result.actual_cost, cost_limit)
            if not self.provider.cleanup(job_id):
                raise RuntimeError("remote provider did not confirm dataset/job cleanup")
            cleanup_required = False
            succeeded = True
            elapsed = max(0.0, self._clock() - started)
            metrics = {
                **dict(result.metrics),
                "remote_provider_id": self.provider.provider_id,
                "remote_job_id": job_id,
                "runtime_seconds": elapsed,
                "estimated_cost": current.estimated_cost,
                "actual_cost": result.actual_cost if result.actual_cost is not None else current.accrued_cost,
                "dataset_sha256": snapshot.sha256,
                "checkpoint_sha256": digest,
                "remote_dataset_cleanup_confirmed": True,
                "provider_credentials_persisted": False,
            }
            return TrainingArtifact(
                checkpoint_ref=str(checkpoint),
                backend_id=self.backend_id,
                base_model=base_model,
                method=method.value,
                metrics=metrics,
            )
        except Exception:
            if not cancelled and not succeeded:
                try:
                    current_state = self.provider.status(job_id).state
                except Exception:
                    current_state = None
                if current_state in {RemoteTrainingState.QUEUED, RemoteTrainingState.RUNNING}:
                    try:
                        self.provider.cancel(job_id)
                    except Exception:
                        pass
            raise
        finally:
            if cleanup_required:
                try:
                    self.provider.cleanup(job_id)
                except Exception:
                    pass
