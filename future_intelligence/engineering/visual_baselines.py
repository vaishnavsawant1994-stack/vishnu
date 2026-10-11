from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .visual_qa import VisualDiffResult, VisualRegressionAnalyzer


@dataclass(frozen=True)
class VisualBaselineKey:
    screen: str
    browser: str
    device: str
    state: str = "normal"
    theme: str = "default"
    reference_version: str = "v1"

    @property
    def id(self) -> str:
        parts = (self.screen, self.browser, self.device, self.state, self.theme, self.reference_version)
        return "|".join(str(item).strip() for item in parts)


@dataclass(frozen=True)
class VisualBaselineEntry:
    key: VisualBaselineKey
    relative_path: str
    sha256: str
    approved_by: str
    approved_at: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VisualBaselineEntry":
        return cls(
            key=VisualBaselineKey(**dict(data["key"])),
            relative_path=str(data["relative_path"]),
            sha256=str(data["sha256"]),
            approved_by=str(data["approved_by"]),
            approved_at=str(data["approved_at"]),
        )


class VisualBaselineError(RuntimeError):
    pass


class ApprovedVisualBaselineStore:
    """Read-only authority for explicitly approved visual references.

    Candidate screenshots can never approve or overwrite a reference through this
    class. Missing, unapproved, path-escaping, symlinked, or checksum-mismatched
    references fail closed so visual qualification remains pending/failing.
    """

    def __init__(self, root: str | Path, manifest: str | Path = "manifest.json") -> None:
        self.root = Path(root).expanduser().resolve()
        self.manifest_path = (self.root / manifest).resolve()
        if self.root != self.manifest_path.parent and self.root not in self.manifest_path.parents:
            raise VisualBaselineError("visual baseline manifest escapes root")

    def _entries(self) -> dict[str, VisualBaselineEntry]:
        if not self.manifest_path.is_file() or self.manifest_path.is_symlink():
            raise VisualBaselineError("approved visual baseline manifest is unavailable")
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or int(payload.get("version", 0)) != 1:
            raise VisualBaselineError("unsupported visual baseline manifest")
        entries: dict[str, VisualBaselineEntry] = {}
        for raw in payload.get("entries", ()):
            entry = VisualBaselineEntry.from_dict(raw)
            if not entry.approved_by.strip() or not entry.approved_at.strip():
                raise VisualBaselineError(f"baseline is not explicitly approved: {entry.key.id}")
            entries[entry.key.id] = entry
        return entries

    def resolve(self, key: VisualBaselineKey) -> Path:
        entry = self._entries().get(key.id)
        if entry is None:
            raise VisualBaselineError(f"approved visual baseline is missing: {key.id}")
        relative = PurePosixPath(entry.relative_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise VisualBaselineError("unsafe visual baseline path")
        path = self.root.joinpath(*relative.parts)
        if not path.is_file() or path.is_symlink():
            raise VisualBaselineError("approved visual baseline file is unavailable")
        resolved = path.resolve()
        if resolved.parent != self.root and self.root not in resolved.parents:
            raise VisualBaselineError("visual baseline file escapes root")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry.sha256:
            raise VisualBaselineError("approved visual baseline checksum mismatch")
        return path

    def compare(self, key: VisualBaselineKey, candidate: str | Path | bytes, *, analyzer: VisualRegressionAnalyzer | None = None, threshold: int = 12) -> VisualDiffResult:
        baseline = self.resolve(key)
        return (analyzer or VisualRegressionAnalyzer()).compare(baseline, candidate, threshold=threshold)
