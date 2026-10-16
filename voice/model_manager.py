from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path

from voice.registry import VoiceModelMetadata, VoiceModelRegistry


class LocalModelState(str, Enum):
    READY = "ready"
    MISSING = "missing"
    HASH_MISMATCH = "hash_mismatch"
    SIZE_MISMATCH = "size_mismatch"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class LocalModelStatus:
    model_id: str
    path: str
    state: LocalModelState
    observed_sha256: str | None = None
    observed_size_bytes: int | None = None

    @property
    def ready(self) -> bool:
        return self.state is LocalModelState.READY


class LocalVoiceModelManager:
    """Inventory and verify explicitly provisioned local voice-model artifacts.

    This class intentionally has no download/install method. Operators provision
    model files separately; Vishnu verifies the registered license/provenance and
    local artifact before a caller chooses to load it.
    """

    def __init__(self, registry: VoiceModelRegistry, *, events=None) -> None:
        self.registry = registry
        self.events = events
        self._paths: dict[str, Path] = {}

    @staticmethod
    def _local_path(path: str | Path) -> Path:
        raw = str(path)
        if "://" in raw:
            raise ValueError("voice model artifact must be a local path")
        return Path(path).expanduser().resolve()

    def register_local(
        self,
        metadata: VoiceModelMetadata,
        path: str | Path,
        *,
        require_commercial: bool = False,
        require_redistribution: bool = False,
    ) -> LocalModelStatus:
        local_path = self._local_path(path)
        self.registry.validate_license(
            metadata,
            require_commercial=require_commercial,
            require_redistribution=require_redistribution,
        )
        try:
            existing = self.registry.get(metadata.model_id)
        except KeyError:
            self.registry.register(metadata)
        else:
            if existing != metadata:
                raise ValueError(f"voice model metadata changed for registered model: {metadata.model_id}")
        self._paths[metadata.model_id] = local_path
        status = self.verify(metadata.model_id)
        self._emit(status)
        return status

    def verify(self, model_id: str) -> LocalModelStatus:
        metadata = self.registry.get(model_id)
        path = self._paths.get(model_id)
        if path is None:
            raise KeyError(f"no local artifact registered for voice model: {model_id}")
        if not path.is_file():
            return LocalModelStatus(model_id, str(path), LocalModelState.MISSING)

        observed_size = path.stat().st_size
        if metadata.size_bytes is not None and observed_size != metadata.size_bytes:
            return LocalModelStatus(
                model_id,
                str(path),
                LocalModelState.SIZE_MISMATCH,
                observed_size_bytes=observed_size,
            )

        digest = sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        observed_hash = digest.hexdigest()
        expected_hash = metadata.artifact_sha256
        if expected_hash is None:
            return LocalModelStatus(
                model_id,
                str(path),
                LocalModelState.UNVERIFIED,
                observed_sha256=observed_hash,
                observed_size_bytes=observed_size,
            )
        if observed_hash != expected_hash.lower():
            return LocalModelStatus(
                model_id,
                str(path),
                LocalModelState.HASH_MISMATCH,
                observed_sha256=observed_hash,
                observed_size_bytes=observed_size,
            )
        return LocalModelStatus(
            model_id,
            str(path),
            LocalModelState.READY,
            observed_sha256=observed_hash,
            observed_size_bytes=observed_size,
        )

    def require_ready(self, model_id: str) -> Path:
        status = self.verify(model_id)
        if not status.ready:
            raise RuntimeError(f"voice model {model_id!r} is not ready: {status.state.value}")
        return Path(status.path)

    def status(self) -> tuple[LocalModelStatus, ...]:
        return tuple(self.verify(model_id) for model_id in sorted(self._paths))

    def _emit(self, status: LocalModelStatus) -> None:
        if self.events is None:
            return
        self.events.emit(
            "voice.model.verified",
            model_id=status.model_id,
            state=status.state.value,
            ready=status.ready,
            observed_size_bytes=status.observed_size_bytes,
        )
