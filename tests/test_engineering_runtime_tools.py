from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from future_intelligence.engineering.runtime import EngineeringRuntime
from future_intelligence.work_orchestration import (
    DurableWorkStore,
    GoalSpec,
    RepositoryStatus,
    RepositoryWorkspaceSession,
    ResourceScope,
    WorkOrder,
    WorkOrderStatus,
    WorkPlan,
)
from tools import engineering_repository


BASE = "a" * 40
COMMITTED = "b" * 40


class FakeRepositoryProvider:
    repository = "owner/repo"

    def __init__(self, base_root: Path, workspace_root: Path):
        self.base_root = base_root
        self.workspace_root = workspace_root
        self.session = None
        self.revision = BASE

    def resolve_revision(self, revision: str) -> str:
        if revision in {"HEAD", BASE}:
            return BASE
        return str(revision)

    def read_text_at(self, revision: str, path: str) -> str:
        if self.resolve_revision(revision) != BASE:
            raise RuntimeError("unknown revision")
        target = self.base_root / path
        if not target.is_file():
            raise RuntimeError("path does not exist at revision")
        return target.read_text(encoding="utf-8")

    def prepare(self, *, repository, work_order_id, attempt_id, base_revision, branch_ref):
        assert repository == self.repository
        target = self.workspace_root / attempt_id
        shutil.copytree(self.base_root, target)
        self.session = RepositoryWorkspaceSession(
            repository, work_order_id, attempt_id, self.resolve_revision(base_revision), branch_ref, target
        )
        return self.session

    def resume(self, *, repository, work_order_id, attempt_id, base_revision, branch_ref):
        if self.session is None:
            raise RuntimeError("workspace missing")
        assert (repository, work_order_id, attempt_id, self.resolve_revision(base_revision), branch_ref) == (
            self.session.repository,
            self.session.work_order_id,
            self.session.attempt_id,
            self.session.base_revision,
            self.session.branch_ref,
        )
        return self.session

    def _changed(self):
        if self.session is None:
            return ()
        changed = []
        files = set()
        files.update(p.relative_to(self.base_root).as_posix() for p in self.base_root.rglob("*") if p.is_file())
        files.update(p.relative_to(self.session.local_path).as_posix() for p in self.session.local_path.rglob("*") if p.is_file())
        for path in sorted(files):
            base = self.base_root / path
            work = self.session.local_path / path
            base_bytes = base.read_bytes() if base.exists() else None
            work_bytes = work.read_bytes() if work.exists() else None
            if base_bytes != work_bytes:
                changed.append(path)
        return tuple(changed)

    def changed_paths(self, *, base_revision, working_revision):
        assert self.resolve_revision(base_revision) == BASE
        return self._changed() if working_revision == COMMITTED else ()

    def status(self, session):
        assert session == self.session
        changes = self._changed()
        return RepositoryStatus(self.revision, bool(changes) and self.revision == BASE, changes)

    def commit_all(self, session, *, message):
        assert session == self.session
        assert message
        changes = self._changed()
        if not changes:
            raise ValueError("nothing to commit")
        self.revision = COMMITTED
        return RepositoryStatus(COMMITTED, False, changes)

    def preserve(self, session):
        assert session == self.session


class RecordingRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        assert tool.name not in self.tools
        self.tools[tool.name] = tool


def build_runtime(tmp_path: Path):
    base = tmp_path / "base"
    workspace = tmp_path / "workspaces"
    (base / "src").mkdir(parents=True)
    (base / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    store = DurableWorkStore(tmp_path / "work.sqlite3")
    goal = GoalSpec(
        id="goal-eng", title="Engineering", objective="Change source safely",
        desired_outcome="Qualified isolated source change",
    )
    store.upsert_goal(goal)
    order = WorkOrder(
        id="work-eng", plan_id="plan-eng", title="Modify application source",
        objective="Change VALUE from one to two", worker_type="software_engineer",
        status=WorkOrderStatus.QUEUED,
        resource_scope=ResourceScope(
            allowed_repositories=("owner/repo",), allowed_paths=("src/",)
        ),
        success_criteria=("VALUE is 2",),
        verification_strategy={"tests": ["unit"], "ui_required": False},
        retry_policy={"max_attempts": 3},
    )
    plan = WorkPlan(
        id="plan-eng", goal_id=goal.id, version=1, summary="Engineering plan",
        work_orders=(order,),
    )
    store.save_plan(plan)
    provider = FakeRepositoryProvider(base, workspace)
    runtime = EngineeringRuntime(
        repository_provider=provider,
        work_store=store,
        evidence_root=tmp_path / "engineering-evidence",
    )
    coordinator = runtime.prepare(
        order.id, worker_id="coding-agent", runtime_epoch=1, base_revision=BASE
    )
    return runtime, store, provider, coordinator


def test_runtime_prepares_canonical_isolated_workspace_and_commits_locally(tmp_path: Path):
    runtime, store, provider, coordinator = build_runtime(tmp_path)
    attempt_id = coordinator.spec.attempt_id
    read = runtime.execute("work-eng", attempt_id, "read", {"path": "src/app.py"})
    assert read["content"] == "VALUE = 1\n"

    changed = runtime.execute(
        "work-eng", attempt_id, "replace_exact",
        {"path": "src/app.py", "old": "VALUE = 1", "new": "VALUE = 2", "expected_sha256": read["sha256"]},
    )
    assert changed["verified_scope"] is True
    assert (provider.session.local_path / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    workspace = runtime._workspace_for("work-eng", attempt_id)
    assert workspace.state.value == "dirty"

    commit = runtime.commit("work-eng", attempt_id, message="Implement scoped change")
    assert commit["revision"] == COMMITTED
    assert commit["push_authority"] is False
    assert commit["merge_authority"] is False
    assert commit["deploy_authority"] is False
    assert store.get_attempt(attempt_id).status.value == "running"


def test_repository_tools_are_model_visible_but_work_attempt_bound(tmp_path: Path):
    runtime, _store, _provider, coordinator = build_runtime(tmp_path)
    attempt_id = coordinator.spec.attempt_id
    registry = RecordingRegistry()
    engineering_repository.register(registry, runtime)
    assert {
        "repository_read", "repository_search", "repository_diff", "repository_status",
        "repository_create_file", "repository_modify_file", "repository_apply_patch",
        "repository_delete_file", "repository_rename_file", "repository_restore_file",
    }.issubset(registry.tools)

    read_tool = registry.tools["repository_read"]
    read = read_tool.handler({"work_order_id": "work-eng", "attempt_id": attempt_id, "path": "src/app.py"})
    patch_tool = registry.tools["repository_apply_patch"]
    result = patch_tool.handler({
        "work_order_id": "work-eng", "attempt_id": attempt_id, "path": "src/app.py",
        "old": "VALUE = 1", "new": "VALUE = 2", "expected_sha256": read["sha256"],
    })
    verified = patch_tool.verifier({}, result)
    assert verified.verified
    assert verified.evidence["remote_mutation"] is False

    with pytest.raises(PermissionError):
        read_tool.handler({"work_order_id": "work-eng", "attempt_id": "wrong-attempt", "path": "src/app.py"})


def test_runtime_rejects_paths_outside_engineering_spec(tmp_path: Path):
    runtime, _store, _provider, coordinator = build_runtime(tmp_path)
    with pytest.raises(PermissionError):
        runtime.execute("work-eng", coordinator.spec.attempt_id, "read", {"path": "tools/registry.py"})
