from __future__ import annotations

from types import SimpleNamespace

import pytest

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.final_qualification import EngineeringCandidateFinalizer
from future_intelligence.engineering.qualification import VerificationObservation
from future_intelligence.engineering.regression_evidence import (
    build_regression_proof,
    failure_fingerprint,
    is_test_path,
)
from future_intelligence.engineering.workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    GitHubWorkflowEvidenceConfig,
    PhysicalDeviceWorkflowRun,
    WorkflowEvidenceError,
)


CANDIDATE = "b" * 40


def spec(*, surfaces=(), platforms=None):
    metadata = {"physical_device_required": True}
    if platforms is not None:
        metadata["physical_device_platforms"] = list(platforms)
    return EngineeringSpec(
        id="spec-evidence",
        work_order_id="work-evidence",
        attempt_id="attempt-evidence",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="Qualify physical-device evidence",
        affected_surfaces=tuple(surfaces),
        ui_required=True,
        metadata=metadata,
    )


class FakeWorkflowVerifier(GitHubPhysicalDeviceEvidenceVerifier):
    def __init__(self, runs, artifacts):
        super().__init__(GitHubWorkflowEvidenceConfig(repository="owner/repo", token="secret-token"))
        self.runs = dict(runs)
        self.artifacts = dict(artifacts)

    def _get_json(self, path, *, query=None):
        if path.endswith("/artifacts"):
            run_id = int(path.split("/")[-2])
            return {"artifacts": list(self.artifacts.get(run_id, ())) }
        run_id = int(path.rsplit("/", 1)[-1])
        return dict(self.runs[run_id])


def run_payload(*, platform="ios", sha=CANDIDATE, status="completed", conclusion="success", event="workflow_dispatch", path=None):
    workflow = path or (
        ".github/workflows/ios-physical-device.yml"
        if platform == "ios"
        else ".github/workflows/android-real-device.yml"
    )
    return {
        "repository": {"full_name": "owner/repo"},
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
        "event": event,
        "path": workflow,
        "html_url": f"https://github.com/owner/repo/actions/runs/{1 if platform == 'ios' else 2}",
    }


def artifact(name, *, expired=False):
    return {
        "name": name,
        "expired": expired,
        "archive_download_url": f"https://api.github.com/artifacts/{name}.zip",
    }


def healthy_verifier():
    return FakeWorkflowVerifier(
        {
            1: run_payload(platform="ios"),
            2: run_payload(platform="android"),
        },
        {
            1: (artifact("iphone-physical-evidence"),),
            2: (artifact("physical-android-evidence"),),
        },
    )


def test_physical_device_verifier_requires_exact_revision_and_all_required_platforms():
    verifier = healthy_verifier()
    observation = verifier.verify(
        spec=spec(platforms=("ios", "android")),
        candidate_revision=CANDIDATE,
        runs=(PhysicalDeviceWorkflowRun("ios", 1), PhysicalDeviceWorkflowRun("android", 2)),
    )
    assert observation.passed is True
    assert observation.gate == "physical_device"
    assert observation.metadata["candidate_revision"] == CANDIDATE
    assert observation.metadata["verified_platforms"] == ["ios", "android"]
    assert len(observation.evidence) == 4

    missing = verifier.verify(
        spec=spec(platforms=("ios", "android")),
        candidate_revision=CANDIDATE,
        runs=(PhysicalDeviceWorkflowRun("ios", 1),),
    )
    assert missing.passed is False
    assert "android" in missing.summary


def test_physical_device_verifier_rejects_wrong_sha_workflow_event_and_artifact():
    wrong_sha = FakeWorkflowVerifier(
        {1: run_payload(platform="ios", sha="c" * 40)},
        {1: (artifact("iphone-physical-evidence"),)},
    )
    with pytest.raises(WorkflowEvidenceError, match="candidate revision"):
        wrong_sha.verify(spec=spec(surfaces=("ios",)), candidate_revision=CANDIDATE, runs=(PhysicalDeviceWorkflowRun("ios", 1),))

    wrong_workflow = FakeWorkflowVerifier(
        {1: run_payload(platform="ios", path=".github/workflows/ci.yml")},
        {1: (artifact("iphone-physical-evidence"),)},
    )
    with pytest.raises(WorkflowEvidenceError, match="allowlisted"):
        wrong_workflow.verify(spec=spec(surfaces=("ios",)), candidate_revision=CANDIDATE, runs=(PhysicalDeviceWorkflowRun("ios", 1),))

    wrong_event = FakeWorkflowVerifier(
        {1: run_payload(platform="ios", event="push")},
        {1: (artifact("iphone-physical-evidence"),)},
    )
    with pytest.raises(WorkflowEvidenceError, match="dispatch-only"):
        wrong_event.verify(spec=spec(surfaces=("ios",)), candidate_revision=CANDIDATE, runs=(PhysicalDeviceWorkflowRun("ios", 1),))

    expired = FakeWorkflowVerifier(
        {1: run_payload(platform="ios")},
        {1: (artifact("iphone-physical-evidence", expired=True),)},
    )
    with pytest.raises(WorkflowEvidenceError, match="missing or expired"):
        expired.verify(spec=spec(surfaces=("ios",)), candidate_revision=CANDIDATE, runs=(PhysicalDeviceWorkflowRun("ios", 1),))


def test_physical_device_verifier_rejects_failed_runs_and_duplicate_platforms():
    failed = FakeWorkflowVerifier(
        {1: run_payload(platform="ios", conclusion="failure")},
        {1: (artifact("iphone-physical-evidence"),)},
    )
    with pytest.raises(WorkflowEvidenceError, match="did not complete successfully"):
        failed.verify(spec=spec(surfaces=("ios",)), candidate_revision=CANDIDATE, runs=(PhysicalDeviceWorkflowRun("ios", 1),))

    verifier = healthy_verifier()
    with pytest.raises(WorkflowEvidenceError, match="duplicate"):
        verifier.verify(
            spec=spec(surfaces=("ios",)),
            candidate_revision=CANDIDATE,
            runs=(PhysicalDeviceWorkflowRun("ios", 1), PhysicalDeviceWorkflowRun("ios", 1)),
        )


def test_workflow_evidence_token_is_not_exposed_in_repr():
    config = GitHubWorkflowEvidenceConfig(repository="owner/repo", token="super-secret-token")
    assert "super-secret-token" not in repr(config)


def test_reserved_qualification_gates_cannot_be_submitted_as_raw_external_claims():
    for gate in ("physical_device", "regression_test"):
        with pytest.raises(PermissionError, match="reserved qualification gate"):
            EngineeringCandidateFinalizer._validated_external(
                (
                    VerificationObservation(
                        gate=gate,
                        passed=True,
                        evidence=("claim://not-trusted",),
                        metadata={"candidate_revision": CANDIDATE},
                    ),
                ),
                candidate_revision=CANDIDATE,
            )


def test_regression_proof_requires_failure_fingerprint_changed_test_and_broad_passing_check():
    fingerprint = failure_fingerprint(("unit: assertion failed",))
    report = SimpleNamespace(
        passed=True,
        checks=(
            SimpleNamespace(name="compile", passed=True, output_hash="compile-hash"),
            SimpleNamespace(name="integration-full-suite", passed=True, output_hash="suite-hash"),
        ),
    )
    proof = build_regression_proof(
        candidate_revision=CANDIDATE,
        repair_cycles=1,
        failure_fingerprints=(fingerprint,),
        changed_test_paths=("tests/test_fixed_bug.py",),
        verification_report=report,
    )
    assert proof.passed is True
    observation = proof.observation()
    assert observation.passed is True
    assert observation.gate == "regression_test"
    assert observation.metadata["candidate_revision"] == CANDIDATE

    no_test = build_regression_proof(
        candidate_revision=CANDIDATE,
        repair_cycles=1,
        failure_fingerprints=(fingerprint,),
        changed_test_paths=("src/feature.py",),
        verification_report=report,
    )
    assert no_test.passed is False
    assert "changed regression test" in no_test.observation().summary

    compile_only = SimpleNamespace(
        passed=True,
        checks=(SimpleNamespace(name="compile", passed=True, output_hash="compile-hash"),),
    )
    no_broad_test = build_regression_proof(
        candidate_revision=CANDIDATE,
        repair_cycles=1,
        failure_fingerprints=(fingerprint,),
        changed_test_paths=("tests/test_fixed_bug.py",),
        verification_report=compile_only,
    )
    assert no_broad_test.passed is False
    assert "full-suite" in no_broad_test.observation().summary


def test_test_path_detection_covers_python_and_web_conventions():
    for path in (
        "tests/test_feature.py",
        "src/widget_test.py",
        "web/widget.test.tsx",
        "web/__tests__/widget.ts",
        "specs/widget.spec.js",
    ):
        assert is_test_path(path) is True
    assert is_test_path("src/widget.py") is False
