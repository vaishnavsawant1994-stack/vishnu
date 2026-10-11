from __future__ import annotations

import difflib
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from future_intelligence.work_orchestration.repository import RepositoryWorkspaceProvider, RepositoryWorkspaceSession

from .contracts import EngineeringSpec
from .policy import require_engineering_path


@dataclass(frozen=True)
class MutationEvidence:
    operation: str
    path: str
    before_sha256: str
    after_sha256: str
    bytes_written: int

    def to_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


class GovernedRepositoryEditor:
    """Workspace-bound source editor with no shell, Git remote, or approval authority."""

    def __init__(self, *, provider: RepositoryWorkspaceProvider, session: RepositoryWorkspaceSession, spec: EngineeringSpec) -> None:
        if session.repository != spec.repository:
            raise ValueError("EngineeringSpec repository does not match workspace")
        if session.work_order_id != spec.work_order_id or session.attempt_id != spec.attempt_id:
            raise ValueError("EngineeringSpec is not bound to this Work/Attempt")
        if session.base_revision != provider.resolve_revision(spec.base_revision):
            raise ValueError("EngineeringSpec base revision does not match workspace")
        self.provider = provider
        self.session = session
        self.spec = spec
        self.root = Path(session.local_path).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(self.root)
        self._mutations: list[MutationEvidence] = []
        self._mutated_paths: set[str] = set()
        self._total_written = 0

    @staticmethod
    def _sha(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _path(self, raw: str, *, must_exist: bool | None = None) -> tuple[str, Path]:
        normalized = require_engineering_path(
            raw,
            allowed_paths=self.spec.allowed_paths,
            prohibited_paths=self.spec.prohibited_paths,
            allow_authority_paths=self.spec.allow_authority_paths,
        )
        target = self.root.joinpath(*normalized.split("/"))
        resolved_parent = target.parent.resolve()
        if resolved_parent != self.root and self.root not in resolved_parent.parents:
            raise PermissionError("repository path escapes isolated workspace")
        if target.exists() and target.is_symlink():
            raise PermissionError("repository editor does not follow symlinks")
        if must_exist is True and not target.is_file():
            raise FileNotFoundError(normalized)
        if must_exist is False and target.exists():
            raise FileExistsError(normalized)
        return normalized, target

    def _bounded(self, content: str, *, path: str) -> bytes:
        if not isinstance(content, str):
            raise TypeError("repository editor accepts UTF-8 text only")
        raw = content.encode("utf-8")
        if len(raw) > self.spec.budget.max_file_bytes:
            raise ValueError(f"file exceeds EngineeringSpec byte budget: {path}")
        projected = self._total_written + len(raw)
        if projected > self.spec.budget.max_total_bytes:
            raise ValueError("engineering mutation exceeds total byte budget")
        if path not in self._mutated_paths and len(self._mutated_paths) >= self.spec.budget.max_files:
            raise ValueError("engineering mutation exceeds changed-file budget")
        return raw

    def _atomic_write(self, path: str, target: Path, content: str, *, expected_sha256: str | None) -> MutationEvidence:
        before = target.read_bytes() if target.exists() else b""
        if b"\x00" in before:
            raise ValueError("binary files are outside the governed text editor")
        before_sha = self._sha(before)
        if expected_sha256 is not None and expected_sha256 != before_sha:
            raise RuntimeError(f"stale write precondition for {path}")
        raw = self._bounded(content, path=path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".vishnu-engineering.tmp")
        if temp.exists() or temp.is_symlink():
            raise PermissionError("temporary engineering path collision")
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(target)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        evidence = MutationEvidence("write", path, before_sha, self._sha(raw), len(raw))
        self._mutations.append(evidence)
        self._mutated_paths.add(path)
        self._total_written += len(raw)
        return evidence

    def read_text(self, path: str) -> tuple[str, str]:
        normalized, target = self._path(path, must_exist=True)
        raw = target.read_bytes()
        if b"\x00" in raw or len(raw) > self.spec.budget.max_file_bytes:
            raise ValueError(f"file cannot be safely read as governed source text: {normalized}")
        return raw.decode("utf-8"), self._sha(raw)

    def search_text(self, needle: str, *, paths: Iterable[str] | None = None, case_sensitive: bool = False) -> tuple[dict[str, object], ...]:
        query = str(needle)
        if not query:
            raise ValueError("search query is required")
        roots = tuple(paths or self.spec.allowed_paths or (".",))
        results: list[dict[str, object]] = []
        compare = query if case_sensitive else query.lower()
        candidates: list[Path] = []
        for raw_root in roots:
            if str(raw_root) == ".":
                root = self.root
            else:
                _, root = self._path(str(raw_root))
            if root.is_file():
                candidates.append(root)
            elif root.is_dir() and not root.is_symlink():
                candidates.extend(item for item in root.rglob("*") if item.is_file() and not item.is_symlink())
        for item in sorted(set(candidates)):
            relative = item.relative_to(self.root).as_posix()
            try:
                require_engineering_path(relative, allowed_paths=self.spec.allowed_paths, prohibited_paths=self.spec.prohibited_paths, allow_authority_paths=self.spec.allow_authority_paths)
                raw = item.read_bytes()
                if b"\x00" in raw or len(raw) > self.spec.budget.max_file_bytes:
                    continue
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError, PermissionError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                haystack = line if case_sensitive else line.lower()
                if compare in haystack:
                    results.append({"path": relative, "line": number, "text": line[:1000]})
                    if len(results) >= self.spec.budget.max_search_results:
                        return tuple(results)
        return tuple(results)

    def create_text(self, path: str, content: str) -> MutationEvidence:
        normalized, target = self._path(path, must_exist=False)
        return self._atomic_write(normalized, target, content, expected_sha256=self._sha(b""))

    def replace_text(self, path: str, content: str, *, expected_sha256: str) -> MutationEvidence:
        normalized, target = self._path(path, must_exist=True)
        return self._atomic_write(normalized, target, content, expected_sha256=expected_sha256)

    def replace_exact(self, path: str, old: str, new: str, *, expected_sha256: str) -> MutationEvidence:
        text, actual_sha = self.read_text(path)
        if actual_sha != expected_sha256:
            raise RuntimeError(f"stale exact-replace precondition for {path}")
        count = text.count(old)
        if count != 1:
            raise ValueError(f"exact replacement requires one match; found {count}")
        normalized, target = self._path(path, must_exist=True)
        return self._atomic_write(normalized, target, text.replace(old, new, 1), expected_sha256=expected_sha256)

    def delete(self, path: str, *, expected_sha256: str) -> MutationEvidence:
        normalized, target = self._path(path, must_exist=True)
        raw = target.read_bytes()
        before_sha = self._sha(raw)
        if expected_sha256 != before_sha:
            raise RuntimeError(f"stale delete precondition for {normalized}")
        target.unlink()
        evidence = MutationEvidence("delete", normalized, before_sha, self._sha(b""), 0)
        self._mutations.append(evidence)
        self._mutated_paths.add(normalized)
        return evidence

    def rename(self, source: str, destination: str, *, expected_sha256: str) -> tuple[MutationEvidence, MutationEvidence]:
        source_name, source_path = self._path(source, must_exist=True)
        destination_name, destination_path = self._path(destination, must_exist=False)
        raw = source_path.read_bytes()
        if self._sha(raw) != expected_sha256:
            raise RuntimeError(f"stale rename precondition for {source_name}")
        if destination_name not in self._mutated_paths and len(self._mutated_paths) + (0 if source_name in self._mutated_paths else 1) >= self.spec.budget.max_files:
            raise ValueError("engineering mutation exceeds changed-file budget")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(destination_path)
        deleted = MutationEvidence("rename_from", source_name, expected_sha256, self._sha(b""), 0)
        created = MutationEvidence("rename_to", destination_name, self._sha(b""), expected_sha256, len(raw))
        self._mutations.extend((deleted, created))
        self._mutated_paths.update((source_name, destination_name))
        return deleted, created

    def restore_from_base(self, path: str) -> MutationEvidence:
        normalized, target = self._path(path)
        before = target.read_bytes() if target.exists() else b""
        try:
            base = self.provider.read_text_at(self.session.base_revision, normalized)
        except RuntimeError:
            if not target.exists():
                raise FileNotFoundError(f"{normalized} does not exist in workspace or base revision")
            target.unlink()
            evidence = MutationEvidence("restore_delete", normalized, self._sha(before), self._sha(b""), 0)
            self._mutations.append(evidence)
            self._mutated_paths.add(normalized)
            return evidence
        return self._atomic_write(normalized, target, base, expected_sha256=self._sha(before))

    def diff(self, path: str) -> str:
        normalized, target = self._path(path)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        try:
            base = self.provider.read_text_at(self.session.base_revision, normalized)
        except RuntimeError:
            base = ""
        return "".join(difflib.unified_diff(base.splitlines(True), current.splitlines(True), fromfile=f"a/{normalized}", tofile=f"b/{normalized}"))

    @property
    def mutation_evidence(self) -> tuple[MutationEvidence, ...]:
        return tuple(self._mutations)

    @property
    def mutated_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._mutated_paths))
