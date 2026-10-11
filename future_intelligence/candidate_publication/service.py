from __future__ import annotations

import hashlib
import re
from typing import Mapping

from future_intelligence.engineering.final_qualification import EngineeringCandidateFinalizer

from .contracts import CandidatePublicationPlan, CandidatePublicationResult
from .provider import CandidatePublicationError, GitHubDraftCandidatePublisher


_CONFIRMATION = "publish-qualified-candidate-as-draft-pr"
_SLUG = re.compile(r"[^a-z0-9-]+")


class GovernedCandidatePublicationService:
    """Owner-approved handoff from exact engineering qualification to a draft PR.

    Publication is intentionally not part of the engineering repository provider
    or release controller. The service can only derive a plan from a persisted,
    clean, exact candidate that already has a durable
    `engineering.candidate.qualified` event. It cannot select a repository/SHA,
    force-push, merge, tag, release, deploy, or activate a Body revision.
    """

    confirmation_phrase = _CONFIRMATION

    def __init__(
        self,
        *,
        finalizer: EngineeringCandidateFinalizer,
        publisher: GitHubDraftCandidatePublisher,
    ) -> None:
        self.finalizer = finalizer
        self.runtime = finalizer.runtime
        self.publisher = publisher

    @staticmethod
    def _slug(value: str) -> str:
        normalized = _SLUG.sub("-", str(value or "").lower()).strip("-")
        return normalized[:48] or "candidate"

    @staticmethod
    def _digest(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()

    def _qualified_event(self, work_order_id: str, attempt_id: str, candidate_revision: str):
        matches = []
        for event in self.runtime.work_store.list_work_events(str(work_order_id)):
            if event.attempt_id != str(attempt_id) or event.event_type != "engineering.candidate.qualified":
                continue
            payload = dict(event.payload or {})
            if (
                payload.get("qualified") is True
                and str(payload.get("review_decision") or "") == "approved"
                and str(payload.get("candidate_revision") or "") == candidate_revision
            ):
                matches.append(event)
        if not matches:
            raise PermissionError("candidate publication requires durable exact-revision final qualification")
        return matches[-1]

    def plan(self, work_order_id: str, attempt_id: str) -> tuple[CandidatePublicationPlan, object, object]:
        attempt, workspace, spec, session, candidate_revision, changed_paths = self.finalizer._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        self._qualified_event(str(work_order_id), str(attempt_id), candidate_revision)
        if workspace.repository != self.publisher.config.repository or spec.repository != self.publisher.config.repository:
            raise PermissionError("candidate publication repository is outside the configured publication authority")
        branch_hash = self._digest(str(work_order_id), str(attempt_id), candidate_revision)[:16]
        remote_branch = f"vishnu/candidate/{self._slug(spec.objective)}-{branch_hash}"
        plan = CandidatePublicationPlan(
            id=f"publication-{self._digest(spec.id, candidate_revision)[:24]}",
            work_order_id=spec.work_order_id,
            attempt_id=spec.attempt_id,
            engineering_spec_id=spec.id,
            repository=spec.repository,
            base_revision=spec.base_revision,
            candidate_revision=candidate_revision,
            local_branch=str(workspace.branch_ref or session.branch_ref),
            remote_branch=remote_branch,
            base_branch=self.publisher.config.base_branch,
            changed_paths=tuple(changed_paths),
            metadata={
                "created_from": "engineering.candidate.qualified",
                "owner_approval_required": True,
                "draft_pull_request_only": True,
            },
        )
        return plan, spec, session

    def preview(self, work_order_id: str, attempt_id: str) -> CandidatePublicationPlan:
        plan, _spec, _session = self.plan(work_order_id, attempt_id)
        return plan

    @staticmethod
    def _pr_body(plan: CandidatePublicationPlan, spec, qualification_event) -> str:
        payload = dict(getattr(qualification_event, "payload", {}) or {})
        changed = "\n".join(f"- `{path}`" for path in plan.changed_paths[:200])
        return (
            "## Vishnu governed engineering candidate\n\n"
            "This draft pull request was published only after exact candidate qualification and explicit owner confirmation.\n\n"
            f"- WorkOrder: `{plan.work_order_id}`\n"
            f"- Attempt: `{plan.attempt_id}`\n"
            f"- EngineeringSpec: `{plan.engineering_spec_id}`\n"
            f"- Base revision: `{plan.base_revision}`\n"
            f"- Qualified candidate: `{plan.candidate_revision}`\n"
            f"- Independent review: `{payload.get('review_decision', 'approved')}`\n"
            "- Remote publication authority: exact candidate branch only\n"
            "- Merge authority: **none**\n"
            "- Deploy/release authority: **none**\n\n"
            "### Objective\n\n"
            f"{str(spec.objective)[:4000]}\n\n"
            "### Changed paths\n\n"
            f"{changed or '- unavailable'}\n"
        )

    def publish(
        self,
        work_order_id: str,
        attempt_id: str,
        *,
        confirmation: str,
        explicitly_owner_approved: bool,
    ) -> CandidatePublicationResult:
        if not explicitly_owner_approved or str(confirmation or "").strip() != self.confirmation_phrase:
            raise PermissionError("candidate publication requires explicit owner confirmation")
        plan, spec, session = self.plan(work_order_id, attempt_id)
        qualification_event = self._qualified_event(plan.work_order_id, plan.attempt_id, plan.candidate_revision)
        self.runtime.work_store.append_work_event(
            plan.work_order_id,
            "engineering.candidate.publication_requested",
            {
                "publication_id": plan.id,
                "candidate_revision": plan.candidate_revision,
                "remote_branch": plan.remote_branch,
                "base_branch": plan.base_branch,
                "explicit_owner_approval": True,
                "force_push": False,
                "merge_authority": False,
                "deploy_authority": False,
            },
            attempt_id=plan.attempt_id,
        )
        try:
            result = self.publisher.publish(
                plan,
                session=session,
                title=f"Vishnu candidate: {str(spec.objective)[:180]}",
                body=self._pr_body(plan, spec, qualification_event),
            )
        except Exception as exc:
            self.runtime.work_store.append_work_event(
                plan.work_order_id,
                "engineering.candidate.publication_failed",
                {
                    "publication_id": plan.id,
                    "candidate_revision": plan.candidate_revision,
                    "error_type": type(exc).__name__,
                    "retry_requires_owner_confirmation": True,
                },
                attempt_id=plan.attempt_id,
            )
            raise
        self.runtime.work_store.append_work_event(
            plan.work_order_id,
            "engineering.candidate.draft_pr_published",
            {
                "publication_id": plan.id,
                "candidate_revision": result.remote_revision,
                "remote_branch": plan.remote_branch,
                "pull_request_number": result.pull_request_number,
                "pull_request_url": result.pull_request_url,
                "draft": result.draft,
                "reused_branch": result.reused_branch,
                "reused_pull_request": result.reused_pull_request,
                "merge_authority": False,
                "deploy_authority": False,
            },
            attempt_id=plan.attempt_id,
        )
        return result


__all__ = [
    "CandidatePublicationError",
    "GovernedCandidatePublicationService",
]
