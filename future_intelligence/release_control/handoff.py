from __future__ import annotations

from typing import Iterable

from future_intelligence.engineering.evidence_finalizer import EvidenceAwareEngineeringFinalizer
from future_intelligence.engineering.final_qualification import EngineeringFinalQualificationResult
from future_intelligence.engineering.traceability import RequirementTrace
from future_intelligence.engineering.verification import VerificationObservation
from future_intelligence.engineering.workflow_evidence import GitHubPhysicalDeviceEvidenceVerifier

from .automation import ReleaseAutomationService


class ReleaseAwareEngineeringFinalizer(EvidenceAwareEngineeringFinalizer):
    """Trusted engineering finalizer with a one-way release-control handoff.

    The evidence-aware base keeps reserved qualification gates fail-closed:
    physical-device proof must be independently verified against GitHub Actions,
    and regression-test proof must come from the governed repair runtime. Release
    plan creation remains a separate authority domain and is never exposed as an
    arbitrary API.
    """

    def __init__(
        self,
        *,
        runtime,
        release_automation: ReleaseAutomationService,
        models=None,
        reviewer=None,
        physical_device_verifier: GitHubPhysicalDeviceEvidenceVerifier | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            models=models,
            reviewer=reviewer,
            physical_device_verifier=physical_device_verifier,
        )
        self.release_automation = release_automation

    def finalize(
        self,
        work_order_id: str,
        attempt_id: str,
        *,
        external_observations: Iterable[VerificationObservation] = (),
        requirement_traces: Iterable[RequirementTrace] = (),
    ) -> EngineeringFinalQualificationResult:
        result = super().finalize(
            work_order_id,
            attempt_id,
            external_observations=external_observations,
            requirement_traces=requirement_traces,
        )
        if not result.qualification.qualified:
            return result

        try:
            _attempt, _workspace, spec, _session, candidate_revision, _paths = self._workspace_and_spec(
                work_order_id, attempt_id
            )
            if candidate_revision != result.candidate_revision:
                raise RuntimeError("candidate revision changed before release handoff")
            handoff = self.release_automation.handoff(spec=spec, report=result.qualification)
            self.runtime.work_store.append_work_event(
                str(work_order_id),
                "engineering.release_handoff",
                {
                    "candidate_revision": result.candidate_revision,
                    "release_created": handoff.created,
                    "release_id": handoff.release_id,
                    "automatic_execution_started": handoff.automatic_execution_started,
                    "reason": handoff.reason[:500],
                    "release_authority_domain": "governed-release-control",
                },
                attempt_id=str(attempt_id),
            )
        except Exception as exc:
            self.runtime.work_store.append_work_event(
                str(work_order_id),
                "engineering.release_handoff_unavailable",
                {
                    "candidate_revision": result.candidate_revision,
                    "error_type": type(exc).__name__,
                    "engineering_qualification_preserved": True,
                },
                attempt_id=str(attempt_id),
            )
        return result
