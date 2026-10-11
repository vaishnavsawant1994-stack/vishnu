from __future__ import annotations

from typing import Iterable

from .final_qualification import EngineeringCandidateFinalizer, EngineeringFinalQualificationResult
from .qualification import VerificationObservation
from .traceability import RequirementTrace
from .workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    PhysicalDeviceWorkflowRun,
    load_trusted_external_observations,
    record_trusted_external_observation,
)


class EvidenceAwareEngineeringFinalizer(EngineeringCandidateFinalizer):
    """Finalizer that accepts only independently verified reserved evidence.

    `physical_device` and `regression_test` are authority-bearing qualification
    gates. Callers cannot satisfy them by constructing raw VerificationObservation
    objects. Physical-device proof must first pass the GitHub workflow verifier
    and is durably stored as a Work event; regression proof comes from the local
    repair runtime and is persisted in the attempt metadata/observations.
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
        super().__init__(runtime=runtime, models=models, reviewer=reviewer)
        self.physical_device_verifier = physical_device_verifier

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
        raw_external = tuple(external_observations)
        forbidden = tuple(sorted({item.gate for item in raw_external if item.gate in self._RESERVED_EXTERNAL_GATES}))
        if forbidden:
            raise PermissionError(
                "reserved qualification gates require trusted persisted evidence: " + ", ".join(forbidden)
            )
        _attempt, _workspace, _spec, _session, candidate_revision, _changed = self._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        trusted = load_trusted_external_observations(
            work_store=self.runtime.work_store,
            work_order_id=str(work_order_id),
            attempt_id=str(attempt_id),
            candidate_revision=candidate_revision,
        )
        return super().finalize(
            str(work_order_id),
            str(attempt_id),
            external_observations=(*raw_external, *trusted),
            requirement_traces=requirement_traces,
        )
