from __future__ import annotations

from types import SimpleNamespace

import pytest

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.physical_device_automation import (
    GitHubPhysicalDeviceWorkflowCoordinator,
)
from future_intelligence.engineering.workflow_evidence import (
    PhysicalDeviceWorkflowRun,
    WorkflowEvidenceError,
)


CANDIDATE = "b" * 40


def spec(*, platforms=("ios", "android")):
    return EngineeringSpec(
        id="spec-device-auto",
        work_order_id="work-device-auto",
        attempt_id="attempt-device-auto",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="Automate exact-revision physical-device qualification",
        affected_surfaces=("ios", "android"),
        ui_required=True,
        metadata={
            "physical_device_required": True,
            "physical_device_platforms": list(platforms),
        },
    )


class FakeVerifier:
    _WORKFLOWS = {
        "ios": (".github/workflows/ios-physical-device.yml", "iphone-physical-evidence"),
        "android": (".github/workflows/android-real-device.yml", "physical-android-evidence"),
    }

    def __init__(self, *, token="secret"):
        self.config = SimpleNamespace(
            repository="owner/repo",
            token=token,
            timeout_seconds=1.0,
            max_response_bytes=100_000,
        )
        self.verified = []

    @staticmethod
    def required_platforms(engineering_spec):
        return tuple(engineering_spec.metadata["physical_device_platforms"])

    def verify(self, *, spec, candidate_revision, runs):
        runs = tuple(runs)
        self.verified.append((candidate_revision, runs))
        required = self.required_platforms(spec)
        passed = tuple(item.platform for item in runs) == required
        return SimpleNamespace(passed=passed, summary="verified" if passed else "missing platform")


class FakeCoordinator(GitHubPhysicalDeviceWorkflowCoordinator):
    def __init__(self, verifier, responses):
        super().__init__(
            verifier,
            poll_interval_seconds=0.001,
            dispatch_timeout_seconds=0.2,
            sleep_fn=lambda _seconds: None,
        )
        self.responses = list(responses)
        self.calls = []

    def _request_json(self, method, path, *, query=None, body=None):
        self.calls.append((method, path, dict(query or {}), dict(body or {})))
        if not self.responses:
            raise AssertionError(f"unexpected GitHub request: {method} {path}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def run(run_id, platform, *, status="completed", conclusion="success"):
    path = FakeVerifier._WORKFLOWS[platform][0]
    return {
        "id": run_id,
        "repository": {"full_name": "owner/repo"},
        "head_sha": CANDIDATE,
        "event": "workflow_dispatch",
        "path": path,
        "status": status,
        "conclusion": conclusion,
    }


def test_discovery_selects_successful_exact_revision_runs_and_reverifies_them():
    verifier = FakeVerifier()
    coordinator = FakeCoordinator(
        verifier,
        responses=[
            {
                "workflow_runs": [
                    run(10, "ios"),
                    run(11, "android"),
                    {**run(12, "ios"), "head_sha": "c" * 40},
                    {**run(13, "android"), "event": "push"},
                ]
            }
        ],
    )
    runs = coordinator.discover_runs(spec=spec(), candidate_revision=CANDIDATE)
    assert runs == (
        PhysicalDeviceWorkflowRun("ios", 10),
        PhysicalDeviceWorkflowRun("android", 11),
    )
    assert verifier.verified[-1][0] == CANDIDATE


def test_dispatch_fails_closed_when_remote_branch_does_not_match_candidate():
    verifier = FakeVerifier()
    coordinator = FakeCoordinator(
        verifier,
        responses=[{"object": {"type": "commit", "sha": "c" * 40}}],
    )
    with pytest.raises(WorkflowEvidenceError, match="exact candidate revision"):
        coordinator.dispatch_and_wait(
            spec=spec(platforms=("ios",)),
            candidate_revision=CANDIDATE,
            remote_branch="engineering/device-candidate",
        )
    assert not any(call[0] == "POST" for call in coordinator.calls)


def test_dispatch_uses_only_allowlisted_workflows_and_ignores_preexisting_runs():
    verifier = FakeVerifier()
    coordinator = FakeCoordinator(
        verifier,
        responses=[
            {"object": {"type": "commit", "sha": CANDIDATE}},
            {"workflow_runs": [run(20, "ios"), run(21, "android")]},
            {},
            {},
            {
                "workflow_runs": [
                    run(20, "ios"),
                    run(21, "android"),
                    run(30, "ios", status="in_progress", conclusion=""),
                    run(31, "android", status="queued", conclusion=""),
                ]
            },
            {
                "workflow_runs": [
                    run(20, "ios"),
                    run(21, "android"),
                    run(30, "ios"),
                    run(31, "android"),
                ]
            },
        ],
    )
    result = coordinator.dispatch_and_wait(
        spec=spec(),
        candidate_revision=CANDIDATE,
        remote_branch="refs/heads/engineering/device-candidate",
    )
    assert result.dispatched is True
    assert result.remote_branch == "engineering/device-candidate"
    assert result.runs == (
        PhysicalDeviceWorkflowRun("ios", 30),
        PhysicalDeviceWorkflowRun("android", 31),
    )
    posts = [call for call in coordinator.calls if call[0] == "POST"]
    assert len(posts) == 2
    assert posts[0][1].endswith("/actions/workflows/ios-physical-device.yml/dispatches")
    assert posts[1][1].endswith("/actions/workflows/android-real-device.yml/dispatches")
    assert all(call[3] == {"ref": "engineering/device-candidate"} for call in posts)
    assert verifier.verified[-1][0] == CANDIDATE


def test_dispatch_requires_a_token_and_valid_branch_name():
    verifier = FakeVerifier(token="")
    coordinator = FakeCoordinator(
        verifier,
        responses=[
            {"object": {"type": "commit", "sha": CANDIDATE}},
            {"workflow_runs": []},
        ],
    )
    with pytest.raises(WorkflowEvidenceError, match="token is required"):
        coordinator.dispatch_and_wait(
            spec=spec(platforms=("ios",)),
            candidate_revision=CANDIDATE,
            remote_branch="engineering/device-candidate",
        )

    with pytest.raises(WorkflowEvidenceError, match="valid Git branch"):
        coordinator.require_exact_remote_branch(
            remote_branch="bad branch",
            candidate_revision=CANDIDATE,
        )
