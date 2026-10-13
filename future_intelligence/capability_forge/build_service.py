from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .execution_bridge import CapabilityForgeExecutionBridge, ForgeCandidateResult
from .models import CapabilityPlan, CapabilitySpec
from .package import CapabilityPackageBuilder, PackagedCapability


class CapabilityForgeBuildService:
    """Execute queued Forge engineering work and package only qualified candidates.

    Canonical Work remains authoritative for queuing/claimability. This service
    never queues work, approves a review, activates a capability, pushes a Git
    branch, merges, or deploys. It resolves packaging inputs from durable
    Engineering workspace state rather than client-provided qualification claims.
    """

    def __init__(
        self,
        *,
        work_store,
        engineering_runtime,
        engineering_executor,
        package_builder: CapabilityPackageBuilder,
        output_root: str | Path,
        lifecycle=None,
        events=None,
    ) -> None:
        self.work_store = work_store
        self.engineering_runtime = engineering_runtime
        self.engineering_executor = engineering_executor
        self.package_builder = package_builder
        self.output_root = Path(output_root)
        self.lifecycle = lifecycle
        self.events = events
        self.execution = CapabilityForgeExecutionBridge(
            work_store,
            engineering_executor,
            events=events,
            lifecycle=lifecycle,
        )

    @staticmethod
    def _normalize_source_root(source_root: str) -> str:
        value = str(source_root or "").strip().replace("\\", "/").strip("/")
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise ValueError("source_root must be a safe repository-relative path")
        return path.as_posix()

    @staticmethod
    def _within_allowed(source_root: str, allowed_paths) -> bool:
        source = PurePosixPath(source_root)
        for raw in allowed_paths or ():
            allowed = str(raw or "").strip().replace("\\", "/").strip("/")
            if not allowed or any(char in allowed for char in "*?["):
                continue
            base = PurePosixPath(allowed)
            if source == base or base in source.parents:
                return True
        return False

    def _workspace_session(self, work_order_id: str, attempt_id: str):
        row = self.work_store.connection.execute(
            """
            SELECT id FROM work_workspaces
            WHERE work_order_id=? AND attempt_id=?
            ORDER BY updated_at DESC,id DESC LIMIT 1
            """,
            (str(work_order_id), str(attempt_id)),
        ).fetchone()
        if row is None:
            raise RuntimeError("qualified Forge attempt has no durable engineering workspace")
        workspace = self.work_store.get_workspace(str(row["id"]))
        if workspace is None:
            raise RuntimeError("qualified Forge engineering workspace is unavailable")
        return self.engineering_runtime.repository_provider.resume(
            repository=workspace.repository,
            work_order_id=workspace.work_order_id,
            attempt_id=str(workspace.attempt_id),
            base_revision=workspace.base_revision,
            branch_ref=str(workspace.branch_ref or ""),
        )

    def execute_and_package(
        self,
        spec: CapabilitySpec,
        plan: CapabilityPlan,
        *,
        work_order_id: str,
        runtime_epoch: int,
        source_root: str,
        version: str = "1.0.0",
        worker_id: str = "vishnu-capability-forge",
        base_revision: str = "HEAD",
        lease_seconds: int = 3600,
        overrides: Mapping[str, object] | None = None,
    ) -> tuple[ForgeCandidateResult, PackagedCapability | None]:
        source_root = self._normalize_source_root(source_root)
        order = self.work_store.get_order(str(work_order_id))
        if order is None:
            raise KeyError(work_order_id)
        if not self._within_allowed(source_root, order.resource_scope.allowed_paths):
            raise PermissionError("source_root is outside Canonical Work allowed_paths")

        candidate = self.execution.execute_candidate(
            spec,
            plan,
            work_order_id=str(work_order_id),
            runtime_epoch=int(runtime_epoch),
            worker_id=str(worker_id),
            base_revision=str(base_revision),
            lease_seconds=int(lease_seconds),
            overrides=overrides,
        )
        if not candidate.qualified:
            return candidate, None

        session = self._workspace_session(candidate.work_order_id, candidate.attempt_id)
        package = self.package_builder.build(
            spec=spec,
            plan=plan,
            execution_result=candidate,
            workspace_root=session.local_path,
            source_root=source_root,
            output_root=self.output_root,
            version=str(version),
        )
        if self.lifecycle is not None:
            payload: dict[str, Any] = candidate.to_dict()
            payload.update({
                "package_path": str(package.package_path),
                "package_ref": package.package_path.relative_to(self.output_root.parent).as_posix(),
                "capability_id": package.capability_id,
                "version": package.version,
                "manifest_digest": package.manifest_digest,
            })
            self.lifecycle.record_build(
                build_id=package.build_id,
                spec_id=spec.id,
                plan_id=plan.id,
                work_order_id=candidate.work_order_id,
                attempt_id=candidate.attempt_id,
                candidate_revision=candidate.candidate_revision,
                status="packaged",
                payload=payload,
            )
        if self.events is not None:
            self.events.emit(
                "capability_forge.packaged",
                spec_id=spec.id,
                plan_id=plan.id,
                work_order_id=candidate.work_order_id,
                attempt_id=candidate.attempt_id,
                capability_id=package.capability_id,
                version=package.version,
                manifest_digest=package.manifest_digest,
            )
        return candidate, package
