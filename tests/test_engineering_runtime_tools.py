from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from evolution.verification import VerificationCheck, VerificationReport
from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.final_qualification import EngineeringCandidateFinalizer
from future_intelligence.engineering.qualification import VerificationObservation
from future_intelligence.engineering.reviewer_adapter import EngineeringReviewDecision
from future_intelligence.engineering.runtime import EngineeringRuntime
from future_intelligence.engineering.traceability import RequirementTrace
from future_intelligence.engineering.work_executor import EngineeringWorkExecutor
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
        return RepositoryStatus(COMMITTED, False, ())

    def preserve(self, session):
        assert session == self.session


class RecordingRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        assert tool.name not in self.tools
        self.tools[tool.name] = tool


class EditModels:
    def json(self, prompt, *, system="Return valid JSON only.", sensitivity="internal"):
        assert sensitivity == "internal"
        return {
            "summary": "Change the requested constant",
            "operations": [{
                "operation": "replace_exact",
                "path": "src/app.py",
                "old": "VALUE = 1",
                "new": "VALUE = 2",
                "reason": "required outcome",
            }],
            "assumptions": [],
        }


class PassingVerifier:
    def verify(self, session, *, revision):
        assert revision == COMMITTED
        return VerificationReport(
            revision=revision,
            checks=(
                VerificationCheck("build", ("python", "-m", "compileall"), True, 0, 1, "h1", ""),
                VerificationCheck("unit-tests", ("pytest",), True, 0, 2, "h2", ""),
                VerificationCheck("integration-tests", ("pytest",), True, 0, 3, "h3", ""),
                VerificationCheck("protected-code-scope", ("internal",), True, 0, 0, "h4", ""),
            ),
        )


class ApprovingReviewer:
    def __init__(self):
        self.calls = 0

    def review(self, **_kwargs):
        self.calls += 1
        return EngineeringReviewDecision(
            decision="approved", reviewer="independent-test-reviewer",
            summary="local and external evidence is internally consistent", findings=(),
        )


def build_runtime(tmp_path: Path, *, prepare: bool = True):
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
    coordinator = None
    if prepare:
        coordinator = runtime.prepare(
            order.id, worker_id="coding-agent", runtime_epoch=1, base_revision=BASE
        )
    return runtime, store, provider, coordinator


def latest_attempt_status(store: DurableWorkStore, work_order_id: str) -> str | None:
    row = store.connection.execute(
        """
        SELECT status FROM work_attempts
        WHERE work_order_id = ?
        ORDER BY attempt_number DESC
        LIMIT 1
        """,
        (work_order_id,),
    ).fetchone()
    return None if row is None else str(row["status"])


def candidate_spec(runtime: EngineeringRuntime, attempt_id: str) -> EngineeringSpec:
    workspace = runtime._workspace_for("work-eng", attempt_id)
    return EngineeringSpec.from_dict(dict(workspace.metadata)["engineering_spec"])


def requirement_traces(spec: EngineeringSpec) -> tuple[RequirementTrace, ...]:
    expected = tuple(dict.fromkeys((*spec.requirements, *spec.success_criteria)))
    return tuple(RequirementTrace(item, (f"evidence:{index}",), True) for index, item in enumerate(expected, 1))


def performance_observation() -> VerificationObservation:
    return VerificationObservation(
        "performance",
        True,
        "candidate performance budget passed",
        ("performance:evidence",),
        metadata={"candidate_revision": COMMITTED},
    )


def test_runtime_prepares_canonical_isolated_workspace_and_commits_locally(tmp_path: Path):
    runtime, store, provider, coordinator = build_runtime(tmp_path)
    assert coordinator is not None
    attempt_id = coordinator.spec.attempt_id
    read = runtime.execute("work-eng", attempt_id, "read", {"path": "src/app.py"})
    assert read["content"] == "VALUE = 1\n"
    with pytest.raises(PermissionError, match="Engineering Autonomy"):
        runtime.execute(
            "work-eng", attempt_id, "replace_exact",
            {"path": "src/app.py", "old": "VALUE = 1", "new": "VALUE = 2", "expected_sha256": read["sha256"]},
        )
    runtime.owner_policy.update(mode="workspace")
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
    assert commit["changes"] == ["src/app.py"]
    assert commit["push_authority"] is False
    assert commit["merge_authority"] is False
    assert commit["deploy_authority"] is False
    assert store.get_attempt(attempt_id).status.value == "running"


def test_repository_tools_are_model_visible_but_work_attempt_bound(tmp_path: Path):
    runtime, _store, _provider, coordinator = build_runtime(tmp_path)
    assert coordinator is not None
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
    with pytest.raises(PermissionError, match="Engineering Autonomy"):
        patch_tool.handler({
            "work_order_id": "work-eng", "attempt_id": attempt_id, "path": "src/app.py",
            "old": "VALUE = 1", "new": "VALUE = 2", "expected_sha256": read["sha256"],
        })
    runtime.owner_policy.update(mode="workspace")
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
    assert coordinator is not None
    with pytest.raises(PermissionError):
        runtime.execute("work-eng", coordinator.spec.attempt_id, "read", {"path": "tools/registry.py"})


def test_work_executor_creates_candidate_and_defers_review_until_all_gates_have_evidence(tmp_path: Path):
    runtime, store, provider, _ = build_runtime(tmp_path, prepare=False)
    runtime.owner_policy.update(mode="auto_fix")
    reviewer = ApprovingReviewer()
    executor = EngineeringWorkExecutor(
        runtime=runtime,
        models=EditModels(),
        verification_provider=PassingVerifier(),
        reviewer=reviewer,
    )
    result = executor.execute("work-eng", runtime_epoch=7, base_revision=BASE)
    assert result.candidate_revision == COMMITTED
    assert result.verification_passed is True
    assert result.status == "verifying"
    assert result.qualification["qualified"] is False
    assert result.review["decision"] == "pending"
    assert reviewer.calls == 0
    assert "src/app.py" in result.changed_paths
    assert (provider.session.local_path / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    attempt = store.get_attempt(result.attempt_id)
    assert attempt is not None and attempt.status.value == "succeeded"
    assert attempt.metadata["engineering_local_observations"]
    order = store.get_order("work-eng")
    assert order is not None and order.status is WorkOrderStatus.VERIFYING


def test_finalizer_combines_external_evidence_and_requirements_then_runs_independent_review(tmp_path: Path):
    runtime, store, _provider, _ = build_runtime(tmp_path, prepare=False)
    runtime.owner_policy.update(mode="auto_fix")
    local_reviewer = ApprovingReviewer()
    executor = EngineeringWorkExecutor(runtime=runtime, models=EditModels(), verification_provider=PassingVerifier(), reviewer=local_reviewer)
    local = executor.execute("work-eng", runtime_epoch=10, base_revision=BASE)
    assert local_reviewer.calls == 0

    final_reviewer = ApprovingReviewer()
    finalizer = EngineeringCandidateFinalizer(runtime=runtime, reviewer=final_reviewer)
    spec = candidate_spec(runtime, local.attempt_id)
    final = finalizer.finalize(
        "work-eng",
        local.attempt_id,
        external_observations=(performance_observation(),),
        requirement_traces=requirement_traces(spec),
    )
    assert final.status == "qualified"
    assert final.qualification.qualified is True
    assert final.review["decision"] == "approved"
    assert final_reviewer.calls == 1
    payload = final.to_dict()
    assert payload["push_authority"] is False
    assert payload["merge_authority"] is False
    assert payload["deploy_authority"] is False
    assert payload["activation_authority"] is False
    order = store.get_order("work-eng")
    assert order is not None and order.status is WorkOrderStatus.VERIFYING
    events = store.list_work_events("work-eng")
    assert any(item.event_type == "engineering.candidate.qualified" for item in events)


def test_finalizer_rejects_unbound_or_evidence_free_external_pass_claims(tmp_path: Path):
    runtime, _store, _provider, _ = build_runtime(tmp_path, prepare=False)
    runtime.owner_policy.update(mode="auto_fix")
    local = EngineeringWorkExecutor(runtime=runtime, models=EditModels(), verification_provider=PassingVerifier(), reviewer=ApprovingReviewer()).execute(
        "work-eng", runtime_epoch=11, base_revision=BASE
    )
    spec = candidate_spec(runtime, local.attempt_id)
    finalizer = EngineeringCandidateFinalizer(runtime=runtime, reviewer=ApprovingReviewer())
    with pytest.raises(ValueError, match="requires evidence"):
        finalizer.finalize(
            "work-eng",
            local.attempt_id,
            external_observations=(VerificationObservation("performance", True, metadata={"candidate_revision": COMMITTED}),),
            requirement_traces=requirement_traces(spec),
        )
    with pytest.raises(PermissionError, match="not bound"):
        finalizer.finalize(
            "work-eng",
            local.attempt_id,
            external_observations=(VerificationObservation("performance", True, evidence=("perf",), metadata={"candidate_revision": "c" * 40}),),
            requirement_traces=requirement_traces(spec),
        )


def test_interrupted_verification_marks_recovery_required_without_losing_candidate(tmp_path: Path):
    runtime, store, provider, _ = build_runtime(tmp_path, prepare=False)
    runtime.owner_policy.update(mode="auto_fix")

    class InterruptedVerifier:
        def verify(self, session, *, revision):
            assert revision == COMMITTED
            raise RuntimeError("verification runner disappeared")

    executor = EngineeringWorkExecutor(
        runtime=runtime,
        models=EditModels(),
        verification_provider=InterruptedVerifier(),
        reviewer=ApprovingReviewer(),
    )
    with pytest.raises(RuntimeError, match="verification runner disappeared"):
        executor.execute("work-eng", runtime_epoch=8, base_revision=BASE)
    order = store.get_order("work-eng")
    assert order is not None and order.status is WorkOrderStatus.RECOVERY_REQUIRED
    assert latest_attempt_status(store, "work-eng") == "recovery_required"
    assert store.get_lease("work-eng") is None
    assert provider.revision == COMMITTED
    assert (provider.session.local_path / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"


def test_final_reviewer_outage_preserves_candidate_in_verifying_state(tmp_path: Path):
    runtime, store, provider, _ = build_runtime(tmp_path, prepare=False)
    runtime.owner_policy.update(mode="auto_fix")
    local = EngineeringWorkExecutor(runtime=runtime, models=EditModels(), verification_provider=PassingVerifier(), reviewer=ApprovingReviewer()).execute(
        "work-eng", runtime_epoch=9, base_revision=BASE
    )

    class OfflineReviewer:
        def review(self, **_kwargs):
            raise RuntimeError("review provider unavailable")

    spec = candidate_spec(runtime, local.attempt_id)
    final = EngineeringCandidateFinalizer(runtime=runtime, reviewer=OfflineReviewer()).finalize(
        "work-eng",
        local.attempt_id,
        external_observations=(performance_observation(),),
        requirement_traces=requirement_traces(spec),
    )
    assert final.candidate_revision == COMMITTED
    assert final.status == "verifying"
    assert final.review["decision"] == "pending"
    assert final.qualification.qualified is False
    assert any("review unavailable" in item for item in final.qualification.limitations)
    order = store.get_order("work-eng")
    assert order is not None and order.status is WorkOrderStatus.VERIFYING
    assert latest_attempt_status(store, "work-eng") == "succeeded"
    assert (provider.session.local_path / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
