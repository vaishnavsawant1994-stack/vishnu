from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping


class EngineeringEvidenceLedger:
    """Append-only local evidence ledger kept outside candidate source worktrees."""

    def __init__(self, root: str | Path, *, work_order_id: str, attempt_id: str) -> None:
        raw_root = Path(root).expanduser()
        if raw_root.exists() and raw_root.is_symlink():
            raise PermissionError("engineering evidence root cannot be a symlink")
        raw_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = raw_root.resolve(strict=True)
        safe_work = self._safe_id(work_order_id)
        safe_attempt = self._safe_id(attempt_id)
        work_dir = self.root / safe_work
        if work_dir.exists() and work_dir.is_symlink():
            raise PermissionError("engineering evidence work directory cannot be a symlink")
        work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if work_dir.resolve(strict=True).parent != self.root:
            raise PermissionError("engineering evidence path escaped its root")
        self.path = work_dir / f"{safe_attempt}.jsonl"
        if self.path.exists() and self.path.is_symlink():
            raise PermissionError("engineering evidence ledger cannot be a symlink")

    @staticmethod
    def _safe_id(value: str) -> str:
        text = "".join(char for char in str(value) if char.isalnum() or char in "-_")[:96]
        if not text:
            raise ValueError("evidence identifier is required")
        return text

    def append(self, kind: str, payload: Mapping[str, Any]) -> None:
        if self.path.exists() and self.path.is_symlink():
            raise PermissionError("engineering evidence ledger became a symlink")
        record = {"ts": time.time(), "kind": str(kind), "payload": dict(payload)}
        raw = (json.dumps(record, sort_keys=True, default=str, separators=(",", ":")) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        if self.path.is_symlink():
            raise PermissionError("engineering evidence ledger became a symlink")
        result = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
        return tuple(result)
