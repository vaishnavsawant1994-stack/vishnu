from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from .contracts import ReleasePlan


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


class ReleaseStore(Protocol):
    def save(self, plan: ReleasePlan) -> ReleasePlan: ...
    def get(self, release_id: str) -> ReleasePlan | None: ...
    def list(self) -> tuple[ReleasePlan, ...]: ...


class JsonReleaseStore:
    """Small durable release ledger using atomic JSON replacement.

    The store is deliberately independent of request-thread-bound SQLite
    connections. Every operation is guarded by an in-process re-entrant lock,
    and writes are fsynced before atomic replacement. Directory fsync is used on
    platforms that support opening directories and safely skipped where the OS
    does not expose that primitive (notably some Windows configurations).
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _validate_id(release_id: str) -> str:
        value = str(release_id).strip()
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("invalid release id")
        return value

    def _path(self, release_id: str) -> Path:
        value = self._validate_id(release_id)
        path = (self.root / f"{value}.json").resolve()
        if self.root not in path.parents:
            raise ValueError("release store path escaped root")
        return path

    def _fsync_directory(self) -> None:
        directory_fd = None
        try:
            directory_fd = os.open(self.root, os.O_RDONLY)
            os.fsync(directory_fd)
        except (OSError, AttributeError):
            # Atomic os.replace remains the portability baseline; directory
            # fsync is an additional durability hardening where supported.
            return
        finally:
            if directory_fd is not None:
                try:
                    os.close(directory_fd)
                except OSError:
                    pass

    def save(self, plan: ReleasePlan) -> ReleasePlan:
        destination = self._path(plan.id)
        payload = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            fd, temporary_name = tempfile.mkstemp(prefix=f".{plan.id}.", suffix=".tmp", dir=self.root)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, destination)
                self._fsync_directory()
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        return plan

    def get(self, release_id: str) -> ReleasePlan | None:
        path = self._path(release_id)
        with self._lock:
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        return ReleasePlan.from_dict(data)

    def list(self) -> tuple[ReleasePlan, ...]:
        with self._lock:
            plans: list[ReleasePlan] = []
            for path in sorted(self.root.glob("*.json")):
                if not _SAFE_ID.fullmatch(path.stem):
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                plans.append(ReleasePlan.from_dict(data))
        plans.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return tuple(plans)


class InMemoryReleaseStore:
    def __init__(self) -> None:
        self._items: dict[str, ReleasePlan] = {}
        self._lock = threading.RLock()

    def save(self, plan: ReleasePlan) -> ReleasePlan:
        with self._lock:
            self._items[plan.id] = ReleasePlan.from_dict(plan.to_dict())
        return plan

    def get(self, release_id: str) -> ReleasePlan | None:
        with self._lock:
            item = self._items.get(release_id)
            return None if item is None else ReleasePlan.from_dict(item.to_dict())

    def list(self) -> tuple[ReleasePlan, ...]:
        with self._lock:
            items = [ReleasePlan.from_dict(item.to_dict()) for item in self._items.values()]
        items.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return tuple(items)
