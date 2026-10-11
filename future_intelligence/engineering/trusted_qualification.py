from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .final_qualification import EngineeringCandidateFinalizer, EngineeringFinalQualificationResult
from .qualification import VerificationObservation
from .release_qualification import EnvironmentQualificationResult, PreviewQualificationRequest
from .traceability import RequirementTrace


@dataclass(frozen=True)
class PhysicalDeviceQualificationEvidence:
    """Revision-bound evidence emitted by a trusted native/device qualification lane."""

    candidate_revision: str
    platform: str
    device: str
    physical: bool
    checks: Mapping[str, bool]
    evidence: tuple[str, ...]
    summary: str = ""

    def __post_init__(self) -> None:
        if not str(self.candidate_revision).strip():
            raise ValueError("physical-device evidence requires candidate_revision")
        if not str(self.platform).strip() or not str(self.device).strip():
            raise ValueError("physical-device evidence requires platform and device")
        if not self.checks:
            raise ValueError("physical-device evidence requires at least one check")
        if not self.evidence:
            raise ValueError("physical-device evidence requires evidence references")

    def to_observation(self) -> VerificationObservation:
        passed = bool(self.physical) and all(bool(value) for value in self.checks.values())
        summary = self.summary or (
            f"physical {self.platform} qualification passed on {self.device}"
            if passed
            else f"physical-device qualification did not pass on {self.device}"
        )
        return VerificationObservation(
            "physical_device",
            passed,
            summary,
            tuple(str(item) for item in self.evidence if str(item)),
            metadata={
                "candidate_revision": str(self.candidate_revision),
                "platform": str(self.platform),
                "device": str(self.device),
                "physical": bool(self.physical),
                "checks": {str(key): bool(value) for key, value in self.checks.items()},
            },
        )


@dataclass(frozen=True)
class RegressionTestEvidence:
    """Evidence that a reproducible defect gained a permanent passing regression test."""

    candidate_revision: str
    failure_fingerprint: str
    test_id: str
    passed: bool
    evidence: tuple[str, ...]
    summary: str = ""

    def __post_init__(self) -> None:
        if not str(self.candidate_revision).strip():
            raise ValueError("regression-test evidence requires candidate_revision")
        if not str(self.failure_fingerprint).strip():
            raise ValueError("regression-test evidence requires failure_fingerprint")
        if not str(self.test_id).strip():
            raise ValueError("regression-test evidence requires test_id")
        if not self.evidence:
            raise ValueError("regression-test evidence requires evidence references")

    def to_observation(self) -> VerificationObservation:
        return VerificationObservation(
            "regression_test",
            bool(self.passed),
            self.summary or (
                f"permanent regression test passed: {self.test_id}"
                if self.passed
                else f"permanent regression test failed: {self.test_id}"
            ),
            tuple(str(item) for item in self.evidence if str(item)),
            metadata={
                "candidate_revision": str(self.candidate_revision),
                "failure_fingerprint": str(self.failure_fingerprint),
                "test_id": str(self.test_id),
            },
        )


def preview_observation(
    result: EnvironmentQualificationResult,
    *,
    candidate_revision: str,
    spec_id: str,
) -> VerificationObservation:
    """Convert an exact-revision preview observation into a finalizer gate."""

    revision = str(candidate_revision or "").strip()
    spec_key = str(spec_id or "").strip()
    if result.environment != "preview":
        raise ValueError("only preview environment results can satisfy the preview gate")
    if not revision or not spec_key:
        raise ValueError("preview observation requires candidate_revision and spec_id")
    required_binding = f"binding=spec:{spec_key};revision:{revision}"
    if required_binding not in set(result.evidence):
        raise PermissionError("preview qualification result is not bound to this spec and candidate revision")
    return VerificationObservation(
        "preview",
        result.passed,
        result.summary or ("deployed preview qualification passed" if result.passed else "deployed preview qualification failed"),
        tuple(result.evidence),
        metadata={
            "candidate_revision": revision,
            "spec_id": spec_key,
            "environment": "preview",
            "target": result.target,
            "checks": dict(result.checks),
        },
    )


class EngineeringTrustedQualificationIntake:
    """Trusted release/device evidence handoff into final Engineering qualification.

    This service cannot edit code, create a Git commit, push, merge, deploy,
    approve owner actions, or activate a Body. It prepares revision-bound preview
    requests and converts trusted external evidence into observations accepted by
    EngineeringCandidateFinalizer.
    """

    def __init__(self, finalizer: EngineeringCandidateFinalizer) -> None:
        self.finalizer = finalizer
        self.runtime = finalizer.runtime

    def prepare_preview_request(self, work_order_id: str, attempt_id: str) -> PreviewQualificationRequest:
        _attempt, _workspace, spec, _session, revision, _changed_paths = self.finalizer._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        if not bool(dict(spec.metadata).get("preview_enabled", False)):
            raise PermissionError("EngineeringSpec does not permit preview qualification")
        request = PreviewQualificationRequest(
            work_order_id=spec.work_order_id,
            attempt_id=spec.attempt_id,
            spec_id=spec.id,
            repository=spec.repository,
            candidate_revision=revision,
        )
        self.runtime.work_store.append_work_event(
            spec.work_order_id,
            "engineering.preview.requested",
            request.to_dict(),
            attempt_id=spec.attempt_id,
        )
        return request

    def finalize(
        self,
        work_order_id: str,
        attempt_id: str,
        *,
        requirement_traces: Iterable[RequirementTrace],
        preview_result: EnvironmentQualificationResult | None = None,
        physical_device_evidence: Iterable[PhysicalDeviceQualificationEvidence] = (),
        regression_test_evidence: RegressionTestEvidence | None = None,
        external_observations: Iterable[VerificationObservation] = (),
    ) -> EngineeringFinalQualificationResult:
        _attempt, _workspace, spec, _session, revision, _changed_paths = self.finalizer._workspace_and_spec(
            str(work_order_id), str(attempt_id)
        )
        observations = list(external_observations)
        if preview_result is not None:
            observations.append(preview_observation(preview_result, candidate_revision=revision, spec_id=spec.id))
        for item in physical_device_evidence:
            if str(item.candidate_revision) != revision:
                raise PermissionError("physical-device evidence is not bound to candidate revision")
            observations.append(item.to_observation())
        if regression_test_evidence is not None:
            if str(regression_test_evidence.candidate_revision) != revision:
                raise PermissionError("regression-test evidence is not bound to candidate revision")
            expected_fingerprint = str(dict(spec.metadata).get("failure_fingerprint") or "").strip()
            if expected_fingerprint and regression_test_evidence.failure_fingerprint != expected_fingerprint:
                raise PermissionError("regression-test evidence does not match EngineeringSpec failure fingerprint")
            observations.append(regression_test_evidence.to_observation())
        return self.finalizer.finalize(
            spec.work_order_id,
            spec.attempt_id,
            external_observations=tuple(observations),
            requirement_traces=tuple(requirement_traces),
        )
