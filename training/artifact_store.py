from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Protocol
from uuid import uuid4

from training.deployment import DeploymentResult
from training.self_improvement import TrainingArtifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class ModelArtifactManifest:
    schema_version: int
    artifact_id: str
    artifact_sha256: str
    created_at: str
    checkpoint_ref: str
    files: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    immutable: bool = True

    def public(self) -> dict[str, Any]:
        return asdict(self)


class ModelArtifactStore(Protocol):
    persistent: bool

    def stage(self, checkpoint_ref: str | Path, *, metadata: dict[str, Any] | None = None) -> ModelArtifactManifest: ...
    def verify(self, checkpoint_ref: str | Path) -> ModelArtifactManifest: ...
    def status(self) -> dict[str, Any]: ...


class FilesystemModelArtifactStore:
    """Content-addressed immutable checkpoint storage.

    Persistence is an explicit deployment property. Merely writing a checkpoint
    to a filesystem does not make it production durable; the release environment
    must set ``VISHNU_MODEL_ARTIFACT_STORE_PERSISTENT=true`` only when ``root``
    is backed by a durable volume.
    """

    manifest_name = 'artifact-manifest.json'

    def __init__(self, root: str | Path, *, persistent: bool = False) -> None:
        self.root = Path(root).expanduser().resolve()
        self.artifacts_root = self.root / 'artifacts'
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.persistent = bool(persistent)

    @staticmethod
    def _safe_relative(path: Path, root: Path) -> str:
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError('artifact file escaped checkpoint root') from exc
        value = relative.as_posix()
        if not value or value.startswith('../') or '/..' in value:
            raise ValueError('invalid artifact path')
        return value

    def _inventory(self, checkpoint: Path, *, include_manifest: bool = False) -> tuple[dict[str, Any], ...]:
        checkpoint = checkpoint.expanduser().resolve()
        if not checkpoint.is_dir():
            raise ValueError('checkpoint_ref must be an existing directory')
        files: list[dict[str, Any]] = []
        for item in sorted(checkpoint.rglob('*')):
            if item.is_symlink():
                raise ValueError('symbolic links are not permitted in model artifacts')
            if not item.is_file():
                continue
            relative = self._safe_relative(item, checkpoint)
            if not include_manifest and relative == self.manifest_name:
                continue
            digest = sha256()
            with item.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            files.append({'path': relative, 'size': item.stat().st_size, 'sha256': digest.hexdigest()})
        if not files:
            raise ValueError('checkpoint contains no files')
        return tuple(files)

    @staticmethod
    def _inventory_digest(files: tuple[dict[str, Any], ...]) -> str:
        canonical = json.dumps(list(files), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return sha256(canonical.encode('utf-8')).hexdigest()

    def is_managed(self, checkpoint_ref: str | Path) -> bool:
        try:
            Path(checkpoint_ref).expanduser().resolve().relative_to(self.artifacts_root)
            return True
        except (ValueError, OSError):
            return False

    def stage(self, checkpoint_ref: str | Path, *, metadata: dict[str, Any] | None = None) -> ModelArtifactManifest:
        source = Path(checkpoint_ref).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('checkpoint_ref must be an existing directory')
        try:
            self.root.relative_to(source)
        except ValueError:
            pass
        else:
            raise ValueError('artifact store cannot be nested inside the source checkpoint')

        files = self._inventory(source)
        digest = self._inventory_digest(files)
        artifact_id = f'artifact-{digest[:24]}'
        target = self.artifacts_root / digest
        manifest_path = target / self.manifest_name
        if target.exists():
            manifest = self.verify(target)
            if manifest.artifact_sha256 != digest:
                raise RuntimeError('immutable artifact digest mismatch')
            return manifest

        staging = self.root / f'.staging-{uuid4().hex}'
        try:
            staging.mkdir(parents=True, exist_ok=False)
            for entry in files:
                relative = Path(str(entry['path']))
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, destination)
            copied = self._inventory(staging)
            if copied != files or self._inventory_digest(copied) != digest:
                raise RuntimeError('artifact copy verification failed')
            manifest = ModelArtifactManifest(
                schema_version=1,
                artifact_id=artifact_id,
                artifact_sha256=digest,
                created_at=_now(),
                checkpoint_ref=str(target),
                files=files,
                metadata=dict(metadata or {}),
                immutable=True,
            )
            (staging / self.manifest_name).write_text(
                json.dumps(manifest.public(), sort_keys=True, indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
            try:
                staging.replace(target)
            except FileExistsError:
                shutil.rmtree(staging, ignore_errors=True)
            return self.verify(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def verify(self, checkpoint_ref: str | Path) -> ModelArtifactManifest:
        checkpoint = Path(checkpoint_ref).expanduser().resolve()
        if not self.is_managed(checkpoint):
            raise ValueError('checkpoint is not managed by this artifact store')
        manifest_path = checkpoint / self.manifest_name
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError('artifact manifest is missing')
        try:
            payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception as exc:
            raise ValueError('artifact manifest is unreadable') from exc
        if not isinstance(payload, dict) or int(payload.get('schema_version', 0)) != 1:
            raise ValueError('unsupported artifact manifest')
        files = self._inventory(checkpoint)
        digest = self._inventory_digest(files)
        if digest != str(payload.get('artifact_sha256') or ''):
            raise RuntimeError('artifact content digest mismatch')
        recorded = tuple(payload.get('files') or ())
        if recorded != files:
            raise RuntimeError('artifact file inventory mismatch')
        expected_id = f'artifact-{digest[:24]}'
        if str(payload.get('artifact_id') or '') != expected_id:
            raise RuntimeError('artifact id mismatch')
        if str(payload.get('checkpoint_ref') or '') != str(checkpoint):
            raise RuntimeError('artifact checkpoint reference mismatch')
        return ModelArtifactManifest(
            schema_version=1,
            artifact_id=expected_id,
            artifact_sha256=digest,
            created_at=str(payload.get('created_at') or ''),
            checkpoint_ref=str(checkpoint),
            files=files,
            metadata=dict(payload.get('metadata') or {}),
            immutable=True,
        )

    def status(self) -> dict[str, Any]:
        return {
            'backend': 'filesystem',
            'root': str(self.root),
            'persistent': self.persistent,
            'content_addressed': True,
            'immutable': True,
            'integrity': 'sha256-file-inventory',
            'production_durable': self.persistent,
        }


class ArtifactPublishingTrainerBackend:
    """Publish a trainer checkpoint into immutable storage before registration."""

    def __init__(self, inner, store: ModelArtifactStore) -> None:
        self.inner = inner
        self.store = store
        self.backend_id = str(getattr(inner, 'backend_id', 'artifact_publishing'))

    def available(self) -> tuple[bool, str | None]:
        return self.inner.available()

    def estimate_cost(self, snapshot, settings):
        estimator = getattr(self.inner, 'estimate_cost', None)
        return None if not callable(estimator) else estimator(snapshot, settings)

    def train(self, snapshot, settings, output_dir: Path) -> TrainingArtifact:
        artifact = self.inner.train(snapshot, settings, output_dir)
        manifest = self.store.stage(
            artifact.checkpoint_ref,
            metadata={
                'backend_id': artifact.backend_id,
                'base_model': artifact.base_model,
                'method': artifact.method,
                'dataset_snapshot_id': getattr(snapshot, 'snapshot_id', None),
                'dataset_sha256': getattr(snapshot, 'sha256', None),
            },
        )
        metrics = dict(artifact.metrics or {})
        metrics.update({
            'artifact_id': manifest.artifact_id,
            'artifact_sha256': manifest.artifact_sha256,
            'artifact_store': 'filesystem',
            'artifact_persistent': bool(self.store.persistent),
            'artifact_verified': True,
        })
        return TrainingArtifact(
            checkpoint_ref=manifest.checkpoint_ref,
            backend_id=artifact.backend_id,
            base_model=artifact.base_model,
            method=artifact.method,
            metrics=metrics,
        )


class ArtifactVerifiedDeploymentBackend:
    """Require a verified durable artifact before any production activation."""

    def __init__(self, inner, store: ModelArtifactStore) -> None:
        self.inner = inner
        self.store = store
        self.backend_id = str(getattr(inner, 'backend_id', 'artifact_verified'))

    def available(self) -> tuple[bool, str | None]:
        if not self.store.persistent:
            return False, 'trained-model artifact store is not declared persistent; production activation is blocked'
        return self.inner.available()

    def deploy(self, model) -> DeploymentResult:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason or 'artifact-verified deployment backend unavailable')
        self.store.verify(str(getattr(model, 'checkpoint_ref', '') or ''))
        result = self.inner.deploy(model)
        if str(result.checkpoint_ref) != str(getattr(model, 'checkpoint_ref', '') or ''):
            raise RuntimeError('deployment returned a checkpoint different from the verified artifact')
        return DeploymentResult(
            checkpoint_ref=result.checkpoint_ref,
            deployment_ref=result.deployment_ref,
            metadata={**dict(result.metadata or {}), 'artifact_verified': True, 'artifact_persistent': True},
        )

    def running_checkpoint(self, deployment_ref: str) -> str | None:
        checkpoint = self.inner.running_checkpoint(deployment_ref)
        if not checkpoint:
            return None
        try:
            self.store.verify(checkpoint)
        except Exception:
            return None
        return checkpoint


def build_model_artifact_store(data_dir: str | Path) -> FilesystemModelArtifactStore:
    configured = str(os.getenv('VISHNU_MODEL_ARTIFACT_STORE_DIR', '') or '').strip()
    root = Path(configured).expanduser() if configured else Path(data_dir) / 'model-artifacts'
    return FilesystemModelArtifactStore(
        root,
        persistent=_env_bool('VISHNU_MODEL_ARTIFACT_STORE_PERSISTENT', False),
    )
