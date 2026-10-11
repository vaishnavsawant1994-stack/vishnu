from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .policy import ReleaseOwnerPolicy


class ReleasePolicyStore:
    """Thread-safe durable owner policy authority for release control."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._policy = self._load()

    def _load(self) -> ReleaseOwnerPolicy:
        if not self.path.exists():
            return ReleaseOwnerPolicy()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("release policy must be a JSON object")
            return ReleaseOwnerPolicy.from_dict(value)
        except Exception:
            # Invalid policy files fail closed to the approval-required default.
            return ReleaseOwnerPolicy()

    def _save(self, policy: ReleaseOwnerPolicy) -> None:
        payload = json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def snapshot(self) -> ReleaseOwnerPolicy:
        with self._lock:
            return ReleaseOwnerPolicy.from_dict(self._policy.to_dict())

    def replace(self, policy: ReleaseOwnerPolicy) -> ReleaseOwnerPolicy:
        with self._lock:
            self._save(policy)
            self._policy = policy
            return self.snapshot()

    def update(self, **changes: Any) -> ReleaseOwnerPolicy:
        with self._lock:
            data = self._policy.to_dict()
            unknown = set(changes) - set(data)
            if unknown:
                raise ValueError(f"unsupported release policy settings: {sorted(unknown)}")
            data.update(changes)
            policy = ReleaseOwnerPolicy.from_dict(data)
            self._save(policy)
            self._policy = policy
            return self.snapshot()
