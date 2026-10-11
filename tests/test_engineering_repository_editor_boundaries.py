from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from future_intelligence.engineering.contracts import EngineeringBudget, EngineeringSpec
from future_intelligence.engineering.repository_editor import GovernedRepositoryEditor
from future_intelligence.work_orchestration.repository import RepositoryWorkspaceSession


BASE = "a" * 40


class FakeProvider:
    repository = "owner/repo"

    def __init__(self, root: Path):
        self.root = root

    def resolve_revision(self, revision: str) -> str:
        return BASE if revision in {"HEAD", BASE} else str(revision)

    def read_text_at(self, revision: str, path: str) -> str:
        assert self.resolve_revision(revision) == BASE
        target = self.root / path
        if not target.is_file():
            raise RuntimeError("missing at base")
        return target.read_text(encoding="utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def editor(tmp_path: Path, *, max_files: int = 4, max_file_bytes: int = 1000, max_total_bytes: int = 4000):
    root = tmp_path / "workspace"
    (root / "src").mkdir(parents=True)
    provider = FakeProvider(root)
    session = RepositoryWorkspaceSession(
        repository="owner/repo",
        work_order_id="work-1",
        attempt_id="attempt-1",
        base_revision=BASE,
        branch_ref="vishnu/work/test",
        local_path=root,
    )
    spec = EngineeringSpec(
        id="eng-1",
        work_order_id="work-1",
        attempt_id="attempt-1",
        repository="owner/repo",
        base_revision=BASE,
        objective="Exercise repository mutation boundaries",
        allowed_paths=("src/",),
        budget=EngineeringBudget(
            max_files=max_files,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            max_repair_cycles=1,
        ),
    )
    return GovernedRepositoryEditor(provider=provider, session=session, spec=spec), root


def test_delete_consumes_changed_file_budget(tmp_path: Path):
    governed, root = editor(tmp_path, max_files=1)
    first = b"FIRST = 1\n"
    second = b"SECOND = 2\n"
    (root / "src" / "first.py").write_bytes(first)
    (root / "src" / "second.py").write_bytes(second)

    governed.delete("src/first.py", expected_sha256=sha(first))
    with pytest.raises(ValueError, match="changed-file budget"):
        governed.delete("src/second.py", expected_sha256=sha(second))
    assert (root / "src" / "second.py").read_bytes() == second


def test_rename_rejects_binary_and_invalid_utf8_sources(tmp_path: Path):
    governed, root = editor(tmp_path)
    binary = b"\x00\x01\x02"
    invalid_utf8 = b"\xff\xfe"
    (root / "src" / "binary.bin").write_bytes(binary)
    (root / "src" / "invalid.txt").write_bytes(invalid_utf8)

    with pytest.raises(ValueError, match="binary files"):
        governed.rename("src/binary.bin", "src/binary-moved.bin", expected_sha256=sha(binary))
    with pytest.raises(ValueError, match="valid UTF-8"):
        governed.rename("src/invalid.txt", "src/invalid-moved.txt", expected_sha256=sha(invalid_utf8))
    assert (root / "src" / "binary.bin").exists()
    assert (root / "src" / "invalid.txt").exists()


def test_rename_rejects_oversized_source(tmp_path: Path):
    governed, root = editor(tmp_path, max_file_bytes=1000, max_total_bytes=4000)
    oversized = b"x" * 1001
    (root / "src" / "large.txt").write_bytes(oversized)

    with pytest.raises(ValueError, match="byte budget"):
        governed.rename("src/large.txt", "src/large-moved.txt", expected_sha256=sha(oversized))
    assert (root / "src" / "large.txt").exists()


def test_rename_consumes_total_change_byte_budget(tmp_path: Path):
    governed, root = editor(tmp_path, max_files=3, max_file_bytes=1000, max_total_bytes=1000)
    source = b"s" * 500
    (root / "src" / "source.txt").write_bytes(source)

    governed.create_text("src/created.txt", "c" * 600)
    with pytest.raises(ValueError, match="total byte budget"):
        governed.rename("src/source.txt", "src/moved.txt", expected_sha256=sha(source))
    assert (root / "src" / "source.txt").exists()
    assert not (root / "src" / "moved.txt").exists()
