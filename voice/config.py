from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be >= 1")
    return value


@dataclass(frozen=True, slots=True)
class VoiceRuntimeSettings:
    """Configuration for the isolated provider runtime.

    The feature is deliberately disabled by default so upgrading Vishnu does not
    silently start model workers or create inference workspaces.
    """

    enabled: bool = False
    workers: int = 1
    max_pending_jobs: int = 32
    workspace_root: Path | None = None

    @classmethod
    def from_env(cls) -> "VoiceRuntimeSettings":
        root = os.getenv("VISHNU_VOICE_RUNTIME_WORKSPACE_ROOT")
        return cls(
            enabled=_env_bool("VISHNU_VOICE_RUNTIME_ENABLED", False),
            workers=_env_positive_int("VISHNU_VOICE_RUNTIME_WORKERS", 1),
            max_pending_jobs=_env_positive_int("VISHNU_VOICE_RUNTIME_MAX_PENDING", 32),
            workspace_root=Path(root).expanduser() if root else None,
        )
