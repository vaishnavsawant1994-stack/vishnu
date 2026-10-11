from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

from future_intelligence.work_orchestration.attempts import WorkAttemptStatus
from future_intelligence.work_orchestration.workspace import WorkspaceState

from .contracts import EngineeringSpec, QualificationReport
from .evidence import EngineeringEvidenceLedger
from .qualification import EngineeringQualification, VerificationObservation
from .repository_editor import GovernedRepositoryEditor
from .reviewer_adapter import EngineeringReviewDecision, ModelEngineeringReviewer
from .traceability import RequirementTrace
from .verification import collapse_observations, observation_from_dict, observation_to_dict
from .workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    PhysicalDeviceWorkflowRun,
    load_trusted_external_observations,
    record_trusted_external_observation,
)


@dataclass(frozen=True)
class EngineeringFinalQualificationResult:
    work_order_id: str
    attempt_id: str
    spec_id: str
    candidate_revision: str
    changed_paths: tuple[str, ...]
    qualification: QualificationReport
    review: Mapping[str, object]
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "spec_id": self.spec_id,
            "candidate_revision": self.candidate_revision,
            "changed_paths": list(self.changed_paths),
            "qualification": self.qualification.to_dict(),
            "review": dict(self.review),
            "status": self.status,
            "push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "activation_authority": False,
        }


class EngineeringCandidateFinalizer:
    """Read-only second-stage qualification for an already committed candidate.

    The finalizer cannot edit source, create commits, push, merge, deploy, approve
    owner actions, or activate a Vishnu Body. It only combines persisted local
    verification with trusted revision-bound external evidence and exact
    requirement traces, then invokes independent review when every gate is ready.

    Physical-device and regression-test gates are reserved. Callers cannot satisfy
    them with raw observations. Physical-device evidence must be independently
    verified against GitHub Actions and durably recorded for this exact Work,
    Attempt and candidate revision. Regression evidence is produced only by the
    governed repair executor and persisted with the attempt.
    """

    _RESERVED_EXTERNAL_GATES = {"physical_device", "regression_test"}

    def __init__(
        self,
        *,
        runtime,
        models=None,
        reviewer=None,
        physical_device_verifier: GitHubPhysicalDeviceEvidenceVerifier | None = None,
    ) -> None:
        self.runtime = runtime
        self.reviewer = reviewer or (ModelEngineeringReviewer(models) if models is not None else None)
        self.qualification = EngineeringQualification()
        self.physical_device_verifier = physical_device_verifier or getattr(
            runtime, "physical_device_verifier", None
        )

    @staticmethod
    def _review_payload(decision: EngineeringReviewDecision) -> dict[str, object]:
        return {
            "decision": decision.decision,
            "reviewer": decision.reviewer,
            "summary": decision.summary,
            "findings": list(decision.findings),
        }

    @staticmethod
    def _pending_review(summary: str, findings: Iterable[str] = ()) -> dict[str, object]:
        return {
            "decision": "pending",
            "reviewer": "",
            "summary": str(summary)[:4000],
            "findings": [str(item)[:2000] for item in findings],
        }

    @staticmethod
    def _with_attempt_requirements(spec: EngineeringSpec, attempt_metadata: Mapping[str, object]) -> EngineeringSpec:
        """Strengthen final qualification from durable execution facts only.

        A repair cycle means Vishnu encountered a reproducible verification
        defect and changed the candidate again. Regardless of whether the
        original WorkOrder was labelled as a bug, that candidate must carry a
        permanent regression-test gate before independent final review.
        """
        raw_cycles = attempt_metadata.get("repair_cycles", 0)
        try:
            repair_cycles = max(0, int(raw_cycles or 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("engineering attempt repair cycle metadata is malformed") from exc
        if repair_cycles <= 0:
            return spec
        metadata = dict(spec.metadata)
        metadata["repair_cycles"] = repair_cycles
        metadata["regression_test_required"] = True
        return replace(spec, metadata=metadata)

    def _workspace_and_spec(self, work_order_id: str, attempt_id: str):
        attempt = self.runtime.work_store.get_attempt(str(attempt_id))
        if attempt is None or attempt.work_order_id != str(work_order_id):
            raise PermissionError("engineering finalization attempt does not belong to WorkOrder")
        if attempt.status is not WorkAttemptStatus.SUCCEEDED:
            raise PermissionError("engineering finalization requires a successfully completed local engineering attempt")
        workspace = self.runtime._workspace_for(str(work_order_id), str(attempt_id))
        if workspace.state in {WorkspaceState.DIRTY, WorkspaceState.CLOSED, WorkspaceState.ABANDONED}:
            raise PermissionError("engineering candidate workspace is not a clean reviewable candidate")
        raw_spec = dict(workspace.metadata or {}).get("engineering_spec")
        if not isinstance(raw_spec, Mapping):
            raise RuntimeError("engineering workspace is missing its persisted EngineeringSpec")
        spec = EngineeringSpec.from_dict(raw_spec)
        if spec.work_order_id != str(work_order_id) or spec.attempt_id != str(attempt_id):
            raise RuntimeError("persisted EngineeringSpec does not match candidate identity")
        spec = self._with_attempt_requirements(spec, attempt.metadata)
        candidate_revision = str(workspace.working_revision or attempt.metadata.get("candidate_revision") or "").strip()
        if not candidate_revision:
            raise RuntimeError("engineering candidate has no committed revision")
        metadata_revision = str(attempt.metadata.get("candidate_revision") or "").strip()
        if metadata_revision and metadata_revision != candidate_revision:
            raise RuntimeError("engineering candidate revision disagrees with durable attempt metadata")
        session = self.runtime.repository_provider.resume(
            repository=workspace.repository,
            work_order_id=workspace.work_order_id,
            attempt_id=str(workspace.attempt_id),
            base_revision=workspace.base_revision,
            branch_ref=str(workspace.branch_ref or ""),
        )
        status = self.runtime.repository_provider.status(session)
        if status.dirty:
            raise PermissionError("engineering candidate workspace became dirty after local verification")
        if str(status.revision) != candidate_revision:
            raise PermissionError("engineering candidate workspace revision changed after local verification")
        changed_paths = self.runtime.repository_provider.changed_paths(
            base_revision=workspace.base_revision,
            working_revision=candidate_revision,
        )
        if not changed_paths:
            raise RuntimeError("engineering candidate contains no base-to-candidate source changes")
        return attempt, workspace, spec, session, candidate_revision, tuple(changed_paths)

    @staticmethod
    def _requirements_observation(spec: EngineeringSpec, traces: Iterable[RequirementTrace]) -> VerificationObservation:
        expected = tuple(dict.fromkeys((*spec.requirements, *spec.success_criteria)))
        supplied: dict[str, RequirementTrace] = {}
        for trace in traces:
            if trace.requirement in supplied:
                raise ValueError(f"duplicate requirement trace: {trace.requirement}")
            supplied[trace.requirement] = trace
        missing = [item for item in expected if item not in supplied]
        failed = [item for item in expected if item in supplied and (not supplied[item].passed or not supplied[item].evidence_refs)]
        evidence = tuple(dict.fromkeys(ref for item in expected if item in supplied for ref in supplied[item].evidence_refs if ref))
        passed = bool(expected) and not missing and not failed
        summary = "all EngineeringSpec requirements have evidence" if passed else "requirements missing or not evidenced: " + ", ".join((*missing, *failed))[:3000]
        return VerificationObservation(
            "requirements",
            passed,
            summary,
            evidence,
            metadata={"expected": len(expected), "supplied": len(supplied), "missing": missing, "failed": failed},
        )

    @staticmethod
    def _validated_external(
        observations: Iterable[VerificationObservation], *, candidate_revision: str
    ) -> tuple[VerificationObservation, ...]:
        result = []
        for item in observations:
            if item.gate == "requirements":
                raise ValueError("requirements gate must come from exact RequirementTrace evidence")
            if item.gate in EngineeringCandidateFinalizer._RESERVED_EXTERNAL_GATES:
                raise PermissionError(
                    f"reserved qualification gate requires trusted persisted evidence: {item.gate}"
                )
            if item.passed and not item.evidence:
                raise ValueError(f"passing external qualification gate requires evidence: {item.gate}")
            metadata = dict(item.metadata or {})
            bound_revision = str(metadata.get("candidate_revision") or "").strip()
            if bound_revision != candidate_revision:
                raise PermissionError(f"external qualification evidence is not bound to candidate revision: {item.gate}")
            result.append(item)
        return tuple(result)

    def verify_and_record_physical_device_evidence(
        self,
        work_order_id: str,
        attempt_id: str,
        *,
        runs: Iterable[PhysicalDeviceWorkflowRun],
    ) -> VerificationObservation:
        if self.physical_device_verifier is None:
            raise RuntimeError("trusted physical-device workflow verifier is unavailable")
        _attempt, _workspace, spec, _session, candidate_revision, _changed = self._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        if not (spec.ui_required and bool(dict(spec.metadata).get("physical_device_required", False))):
            raise PermissionError("EngineeringSpec does not require physical-device qualification")
        observation = self.physical_device_verifier.verify(
            spec=spec,
            candidate_revision=candidate_revision,
            runs=tuple(runs),
        )
        if not observation.passed:
            raise PermissionError(observation.summary or "physical-device qualification did not pass")
        record_trusted_external_observation(
            work_store=self.runtime.work_store,
            work_order_id=str(work_order_id),
            attempt_id=str(attempt_id),
            observation=observation,
        )
        return observation

    def finalize(
        self,
        work_order_id: str,
        attempt_id: str,
        *,
        external_observations: Iterable[VerificationObservation] = (),
        requirement_traces: Iterable[RequirementTrace] = (),
    ) -> EngineeringFinalQualificationResult:
        attempt, workspace, spec, session, candidate_revision, changed_paths = self._workspace_and_spec(
            work_order_id, attempt_id
        )
        raw_local = attempt.metadata.get("engineering_local_observations") or ()
        if not isinstance(raw_local, (list, tuple)):
            raise RuntimeError("engineering attempt local observations are malformed")
        local_observations = tuple(
            observation_from_dict(item) for item in raw_local if isinstance(item, Mapping)
        )
        external = self._validated_external(external_observations, candidate_revision=candidate_revision)
        trusted_external = load_trusted_external_observations(
            work_store=self.runtime.work_store,
            work_order_id=str(work_order_id),
            attempt_id=str(attempt_id),
            candidate_revision=candidate_revision,
        )
        requirements = self._requirements_observation(spec, requirement_traces)
        combined = collapse_observations((*local_observations, *external, *trusted_external, requirements))
        ledger = EngineeringEvidenceLedger(
            self.runtime.evidence_root,
            work_order_id=spec.work_order_id,
            attempt_id=spec.attempt_id,
        )
        ledger.append("engineering.external_qualification", {
            "candidate_revision": candidate_revision,
            "observations": [observation_to_dict(item) for item in external],
            "trusted_persisted_observations": [observation_to_dict(item) for item in trusted_external],
            "requirements": observation_to_dict(requirements),
        })
        preliminary = self.qualification.report(
            spec=spec,
            candidate_revision=candidate_revision,
            observations=combined,
            review_decision="pending",
        )
        blockers = tuple(gate.gate for gate in preliminary.gates if gate.blocking)
        if blockers:
            review_payload = self._pending_review(
                "Independent review remains deferred until all required qualification gates pass.",
                blockers,
            )
            ledger.append("engineering.final_qualification_pending", {
                "candidate_revision": candidate_revision,
                "pending_or_failed_gates": list(blockers),
            })
            self.runtime.work_store.append_work_event(
                spec.work_order_id,
                "engineering.final_qualification_pending",
                {"candidate_revision": candidate_revision, "gates": list(blockers), "review_decision": "pending"},
                attempt_id=spec.attempt_id,
            )
            return EngineeringFinalQualificationResult(
                spec.work_order_id, spec.attempt_id, spec.id, candidate_revision, changed_paths,
                preliminary, review_payload, "verifying",
            )

        editor = GovernedRepositoryEditor(provider=self.runtime.repository_provider, session=session, spec=spec)
        diff = "\n".join(editor.diff(path) for path in changed_paths)
        limitations: list[str] = []
        if spec.review_required:
            if self.reviewer is None:
                limitations.append("independent reviewer is unavailable")
                review_payload = self._pending_review("Independent reviewer is unavailable; candidate remains verifying.")
                final_report = self.qualification.report(
                    spec=spec,
                    candidate_revision=candidate_revision,
                    observations=combined,
                    review_decision="pending",
                    limitations=limitations,
                )
            else:
                try:
                    decision = self.reviewer.review(
                        spec=spec,
                        report=preliminary,
                        diff=diff,
                        evidence={
                            "candidate_revision": candidate_revision,
                            "changed_paths": list(changed_paths),
                            "observations": [observation_to_dict(item) for item in combined],
                            "workspace_id": workspace.id,
                        },
                    )
                    review_payload = self._review_payload(decision)
                    final_report = self.qualification.report(
                        spec=spec,
                        candidate_revision=candidate_revision,
                        observations=combined,
                        reviewer=decision.reviewer,
                        review_decision=decision.decision,
                    )
                except Exception as exc:
                    limitations.append("independent review unavailable; retry final qualification")
                    review_payload = self._pending_review(
                        f"Independent review unavailable: {type(exc).__name__}",
                        ("Retry independent review before release consideration.",),
                    )
                    ledger.append("engineering.review_unavailable", {
                        "candidate_revision": candidate_revision,
                        "error_type": type(exc).__name__,
                    })
                    final_report = self.qualification.report(
                        spec=spec,
                        candidate_revision=candidate_revision,
                        observations=combined,
                        review_decision="pending",
                        limitations=limitations,
                    )
        else:
            review_payload = {
                "decision": "approved",
                "reviewer": "review-not-required",
                "summary": "EngineeringSpec does not require independent review.",
                "findings": [],
            }
            final_report = self.qualification.report(
                spec=spec,
                candidate_revision=candidate_revision,
                observations=combined,
                reviewer="review-not-required",
                review_decision="approved",
            )

        event_type = "engineering.candidate.qualified" if final_report.qualified else (
            "engineering.candidate.review_rejected" if final_report.review_decision == "rejected" else "engineering.final_qualification_pending"
        )
        payload = {
            "candidate_revision": candidate_revision,
            "qualified": final_report.qualified,
            "review_decision": final_report.review_decision,
            "reviewer": final_report.reviewer,
            "changed_paths": list(changed_paths),
            "push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "activation_authority": False,
        }
        ledger.append("engineering.final_qualification", {**payload, "report": final_report.to_dict(), "review": dict(review_payload)})
        self.runtime.work_store.append_work_event(
            spec.work_order_id,
            event_type,
            payload,
            attempt_id=spec.attempt_id,
        )
        return EngineeringFinalQualificationResult(
            spec.work_order_id,
            spec.attempt_id,
            spec.id,
            candidate_revision,
            changed_paths,
            final_report,
            review_payload,
            "qualified" if final_report.qualified else "verifying",
        )
