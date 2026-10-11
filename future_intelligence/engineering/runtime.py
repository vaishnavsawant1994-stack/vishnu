from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from future_intelligence.work_orchestration.attempts import WorkAttemptStatus
from future_intelligence.work_orchestration.engineering_bridge import engineering_spec_from_work_order
from future_intelligence.work_orchestration.failure_policy import FailureClass, WorkFailure
from future_intelligence.work_orchestration.workspace import WorkWorkspace, WorkspaceState

from .contracts import EngineeringSpec
from .owner_policy import EngineeringOwnerPolicyStore
from .service import EngineeringCandidateCoordinator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class EngineeringRuntime:
    """Governed coding runtime over Canonical Work and isolated Git workspaces.

    This runtime is deliberately narrower than a shell or generic filesystem
    authority. It can prepare/resume an isolated workspace for a claimed
    WorkOrder, expose the governed source editor, and make local commits. It has
    no push, merge, deploy, approval, verification-completion, or Body-activation
    operation.
    """

    MUTATING_OPERATIONS = {"create", "replace", "replace_exact", "delete", "rename", "restore"}

    def __init__(
        self,
        *,
        repository_provider,
        work_store,
        evidence_root: str | Path,
        continuation_authority_guard: Callable[[], object] | None = None,
        owner_policy_store: EngineeringOwnerPolicyStore | None = None,
    ) -> None:
        self.repository_provider = repository_provider
        self.work_store = work_store
        self.evidence_root = Path(evidence_root)
        self.owner_policy = owner_policy_store or EngineeringOwnerPolicyStore(
            self.evidence_root.parent / "engineering-owner-policy.json"
        )
        self._continuation_authority_guard = continuation_authority_guard

    def _assert_continuation_authority(self) -> None:
        if self._continuation_authority_guard is not None:
            self._continuation_authority_guard()

    def _assert_workspace_mutation_allowed(self) -> None:
        if not self.owner_policy.snapshot().allows_workspace_mutation():
            raise PermissionError(
                "Engineering Autonomy must be Workspace, Auto-Fix, or Review Candidate for source mutations"
            )

    def _workspace_for(self, work_order_id: str, attempt_id: str):
        row = self.work_store.connection.execute(
            """
            SELECT id FROM work_workspaces
            WHERE work_order_id = ? AND attempt_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (str(work_order_id), str(attempt_id)),
        ).fetchone()
        if row is None:
            raise PermissionError("engineering workspace is not registered for this Work/Attempt")
        workspace = self.work_store.get_workspace(str(row["id"]))
        if workspace is None:
            raise RuntimeError("registered engineering workspace is unavailable")
        return workspace

    def _validate_live_attempt(self, work_order_id: str, attempt_id: str) -> None:
        attempt = self.work_store.get_attempt(str(attempt_id))
        if attempt is None or attempt.work_order_id != str(work_order_id):
            raise PermissionError("engineering attempt does not belong to WorkOrder")
        if attempt.status is not WorkAttemptStatus.RUNNING:
            raise PermissionError("engineering attempt is not running")
        lease = self.work_store.get_lease(str(work_order_id))
        if lease is None or lease.attempt_id != str(attempt_id):
            raise PermissionError("engineering Work/Attempt does not hold the active lease")

    def prepare(
        self,
        work_order_id: str,
        *,
        worker_id: str,
        runtime_epoch: int,
        base_revision: str = "HEAD",
        lease_seconds: int = 900,
        overrides: Mapping[str, object] | None = None,
    ) -> EngineeringCandidateCoordinator:
        """Claim explicitly scoped Canonical Work and prepare one isolated workspace."""
        self._assert_continuation_authority()
        order = self.work_store.get_order(str(work_order_id))
        if order is None:
            raise KeyError(work_order_id)
        if not self.work_store.dependencies_ready(order.id):
            raise PermissionError("engineering WorkOrder dependencies are not ready")
        repository = self.repository_provider.repository
        allowed_repositories = tuple(str(item) for item in order.resource_scope.allowed_repositories if str(item))
        allowed_paths = tuple(str(item) for item in order.resource_scope.allowed_paths if str(item))
        if not allowed_repositories:
            raise PermissionError("engineering WorkOrder requires an explicit repository resource scope")
        if repository not in allowed_repositories:
            raise PermissionError("configured engineering repository is outside WorkOrder resource scope")
        if not allowed_paths:
            raise PermissionError("engineering WorkOrder requires an explicit path resource scope")
        resolved_base = self.repository_provider.resolve_revision(str(base_revision))
        claim = self.work_store.claim_work_order(
            order.id,
            worker_id=str(worker_id),
            runtime_epoch=int(runtime_epoch),
            lease_seconds=int(lease_seconds),
            execution_id=f"engineering:{order.id}",
        )
        if claim is None:
            raise RuntimeError("engineering WorkOrder is not claimable")
        try:
            projected = engineering_spec_from_work_order(
                order,
                attempt_id=claim.attempt.id,
                repository=repository,
                base_revision=resolved_base,
                overrides=overrides,
            )
            spec = self.owner_policy.snapshot().constrain_spec(projected)
            branch_ref = f"vishnu/work/{_digest(order.id, claim.attempt.id)[:24]}-a{claim.attempt.attempt_number}"
            session = self.repository_provider.prepare(
                repository=repository,
                work_order_id=order.id,
                attempt_id=claim.attempt.id,
                base_revision=resolved_base,
                branch_ref=branch_ref,
            )
            stamp = _now()
            workspace = WorkWorkspace(
                id=f"ws-eng-{_digest(order.id, claim.attempt.id)[:24]}",
                work_order_id=order.id,
                attempt_id=claim.attempt.id,
                repository=session.repository,
                base_revision=session.base_revision,
                branch_ref=session.branch_ref,
                state=WorkspaceState.ACTIVE,
                metadata={
                    "engineering_spec": spec.to_dict(),
                    "authority": "canonical_work",
                    "portable": True,
                    "owner_engineering_mode": self.owner_policy.snapshot().mode.value,
                    "push_authority": False,
                    "merge_authority": False,
                    "deploy_authority": False,
                },
                created_at=stamp,
                updated_at=stamp,
            )
            self.work_store.register_workspace(workspace)
            self.work_store.append_work_event(
                order.id,
                "engineering.workspace.prepared",
                {
                    "workspace_id": workspace.id,
                    "branch_ref": session.branch_ref,
                    "base_revision": session.base_revision,
                    "spec_id": spec.id,
                    "owner_engineering_mode": self.owner_policy.snapshot().mode.value,
                },
                attempt_id=claim.attempt.id,
            )
            return self._coordinator(session=session, spec=spec)
        except Exception as exc:
            max_attempts = max(1, int(dict(order.retry_policy or {}).get("max_attempts", 1)))
            self.work_store.finish_attempt(
                claim.attempt.id,
                lease_token=claim.lease.lease_token,
                status=WorkAttemptStatus.FAILED,
                failure=WorkFailure(
                    failure_class=FailureClass.VALIDATION,
                    code="engineering_workspace_prepare_failed",
                    message=type(exc).__name__,
                ),
                max_attempts=max_attempts,
            )
            raise

    def open(self, work_order_id: str, attempt_id: str) -> EngineeringCandidateCoordinator:
        """Resume a persisted active engineering workspace by Canonical Work identity."""
        self._assert_continuation_authority()
        self._validate_live_attempt(work_order_id, attempt_id)
        workspace = self._workspace_for(work_order_id, attempt_id)
        if workspace.state in {WorkspaceState.CLOSED, WorkspaceState.ABANDONED}:
            raise PermissionError("engineering workspace is closed")
        metadata = dict(workspace.metadata or {})
        raw_spec = metadata.get("engineering_spec")
        if not isinstance(raw_spec, Mapping):
            raise RuntimeError("engineering workspace is missing its persisted EngineeringSpec")
        spec = EngineeringSpec.from_dict(raw_spec)
        if spec.work_order_id != str(work_order_id) or spec.attempt_id != str(attempt_id):
            raise RuntimeError("persisted EngineeringSpec does not match workspace identity")
        session = self.repository_provider.resume(
            repository=workspace.repository,
            work_order_id=workspace.work_order_id,
            attempt_id=str(workspace.attempt_id),
            base_revision=workspace.base_revision,
            branch_ref=str(workspace.branch_ref or ""),
        )
        return self._coordinator(session=session, spec=spec)

    def _coordinator(self, *, session, spec: EngineeringSpec) -> EngineeringCandidateCoordinator:
        return EngineeringCandidateCoordinator(
            repository_provider=self.repository_provider,
            session=session,
            spec=spec,
            evidence_root=self.evidence_root,
        )

    def _mark_dirty(self, work_order_id: str, attempt_id: str) -> None:
        stamp = _now()
        with self.work_store.connection:
            self.work_store.connection.execute(
                """
                UPDATE work_workspaces SET state = ?, updated_at = ?
                WHERE work_order_id = ? AND attempt_id = ?
                """,
                (WorkspaceState.DIRTY.value, stamp, str(work_order_id), str(attempt_id)),
            )
        self.work_store.append_work_event(
            str(work_order_id), "engineering.workspace.dirty", {}, attempt_id=str(attempt_id)
        )

    def execute(self, work_order_id: str, attempt_id: str, operation: str, parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Execute one typed repository operation inside the bound isolated workspace."""
        self._assert_continuation_authority()
        coordinator = self.open(work_order_id, attempt_id)
        editor = coordinator.editor
        params = dict(parameters or {})
        op = str(operation or "").strip().lower()

        if op == "read":
            path = str(params["path"])
            content, digest = editor.read_text(path)
            return {"operation": op, "path": path, "content": content, "sha256": digest}
        if op == "search":
            results = editor.search_text(
                str(params["query"]),
                paths=tuple(params.get("paths") or ()),
                case_sensitive=bool(params.get("case_sensitive", False)),
            )
            return {"operation": op, "results": list(results), "count": len(results)}
        if op == "diff":
            path = str(params["path"])
            return {"operation": op, "path": path, "diff": editor.diff(path)}
        if op == "status":
            repository_status = self.repository_provider.status(coordinator.session)
            return {
                "operation": op,
                "repository": coordinator.spec.repository,
                "base_revision": coordinator.spec.base_revision,
                "revision": repository_status.revision,
                "dirty": repository_status.dirty,
                "changes": list(repository_status.changes),
                "mutated_paths": list(editor.mutated_paths),
                "push_authority": False,
                "merge_authority": False,
                "deploy_authority": False,
            }
        if op in self.MUTATING_OPERATIONS:
            self._assert_workspace_mutation_allowed()

        evidence: Any
        if op == "create":
            evidence = editor.create_text(str(params["path"]), str(params["content"]))
        elif op == "replace":
            evidence = editor.replace_text(
                str(params["path"]), str(params["content"]), expected_sha256=str(params["expected_sha256"])
            )
        elif op == "replace_exact":
            evidence = editor.replace_exact(
                str(params["path"]), str(params["old"]), str(params["new"]),
                expected_sha256=str(params["expected_sha256"]),
            )
        elif op == "delete":
            evidence = editor.delete(str(params["path"]), expected_sha256=str(params["expected_sha256"]))
        elif op == "rename":
            evidence = editor.rename(
                str(params["source"]), str(params["destination"]),
                expected_sha256=str(params["expected_sha256"]),
            )
        elif op == "restore":
            evidence = editor.restore_from_base(str(params["path"]))
        else:
            raise ValueError(f"unsupported engineering repository operation: {op}")

        items = evidence if isinstance(evidence, tuple) else (evidence,)
        for item in items:
            coordinator.evidence.append("engineering.mutation", item.to_dict())
        self._mark_dirty(work_order_id, attempt_id)
        return {
            "operation": op,
            "mutations": [item.to_dict() for item in items],
            "mutated_paths": list(editor.mutated_paths),
            "verified_scope": True,
        }

    def commit(self, work_order_id: str, attempt_id: str, *, message: str) -> dict[str, Any]:
        """Create a local candidate commit only; no remote or release authority."""
        self._assert_continuation_authority()
        self._assert_workspace_mutation_allowed()
        coordinator = self.open(work_order_id, attempt_id)
        before = self.repository_provider.status(coordinator.session)
        if not before.dirty:
            raise ValueError("engineering workspace has no changes to commit")
        result = self.repository_provider.commit_all(coordinator.session, message=str(message)[:500])
        changed_paths = self.repository_provider.changed_paths(
            base_revision=coordinator.session.base_revision,
            working_revision=result.revision,
        )
        if not changed_paths:
            raise RuntimeError("candidate commit has no base-to-candidate changes")
        stamp = _now()
        with self.work_store.connection:
            self.work_store.connection.execute(
                """
                UPDATE work_workspaces SET working_revision = ?, state = ?, updated_at = ?
                WHERE work_order_id = ? AND attempt_id = ?
                """,
                (result.revision, WorkspaceState.ACTIVE.value, stamp, str(work_order_id), str(attempt_id)),
            )
        self.work_store.append_work_event(
            str(work_order_id),
            "engineering.workspace.committed",
            {"working_revision": result.revision, "changed_paths": list(changed_paths)},
            attempt_id=str(attempt_id),
        )
        coordinator.evidence.append(
            "engineering.commit",
            {"revision": result.revision, "changes": list(changed_paths), "remote_mutation": False},
        )
        return {
            "revision": result.revision,
            "dirty": result.dirty,
            "changes": list(changed_paths),
            "push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
        }
