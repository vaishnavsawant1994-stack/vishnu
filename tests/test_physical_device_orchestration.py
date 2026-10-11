from __future__ import annotations

import pytest

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.owner_policy import EngineeringOwnerPolicy
from future_intelligence.engineering.workflow_evidence import WorkflowEvidenceError
from future_intelligence.engineering.workflow_orchestration import (
    GitHubPhysicalDeviceOrchestrationConfig,
    GitHubPhysicalDeviceWorkflowOrchestrator,
)


CANDIDATE = "b" * 40


def spec(*, platforms=("ios", "android")) -> EngineeringSpec:
    return EngineeringSpec(
        id="spec-device-orchestration",
        work_order_id="work-device-orchestration",
        attempt_id="attempt-device-orchestration",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="Qualify exact candidate on physical devices",
        affected_surfaces=("ios", "android", "ui"),
        ui_required=True,
        metadata={
            "physical_device_required": True,
            "physical_device_platforms": list(platforms),
        },
    )


class FakeOrchestrator(GitHubPhysicalDeviceWorkflowOrchestrator):
    def __init__(self, *, published=True, candidate=CANDIDATE):
        super().__init__(
            GitHubPhysicalDeviceOrchestrationConfig(
                repository="owner/repo",
                token="dispatch-secret",
                poll_interval_seconds=1,
                timeout_seconds=30,
            )
        )
        self.published = published
        self.candidate = candidate
        self.dispatched: list[str] = []
        self.requests: list[tuple[str, str, object]] = []

    def _request_json(self, method, path, *, query=None, body=None, allow_empty=False):
        self.requests.append((method, path, body))
        if path.endswith("/branches"):
            if not self.published:
                return []
            return [
                {"name": "feature/other", "commit": {"sha": "c" * 40}},
                {"name": "vishnu/work/exact-candidate", "commit": {"sha": self.candidate}},
            ]
        if path.endswith("/dispatches"):
            if "ios-physical-device.yml" in path:
                self.dispatched.append("ios")
            elif "android-real-device.yml" in path:
                self.dispatched.append("android")
            else:  # pragma: no cover - defensive
                raise AssertionError(path)
            assert body == {"ref": "vishnu/work/exact-candidate"}
            return None
        if path.endswith("/runs"):
            if "ios-physical-device.yml" in path:
                platform, run_id = "ios", 101
            elif "android-real-device.yml" in path:
                platform, run_id = "android", 202
            else:  # pragma: no cover - defensive
                raise AssertionError(path)
            rows = []
            if platform in self.dispatched:
                rows.append(
                    {
                        "id": run_id,
                        "event": "workflow_dispatch",
                        "head_sha": self.candidate,
                        "status": "completed",
                        "conclusion": "success",
                    }
                )
            return {"workflow_runs": rows}
        raise AssertionError((method, path, query, body, allow_empty))


def test_orchestrator_dispatches_only_allowlisted_device_workflows_for_exact_remote_tip():
    orchestrator = FakeOrchestrator()
    runs = orchestrator.dispatch_required(
        spec=spec(),
        candidate_revision=CANDIDATE,
        preferred_ref="refs/heads/vishnu/work/exact-candidate",
    )
    assert [(item.platform, item.run_id) for item in runs] == [("ios", 101), ("android", 202)]
    assert orchestrator.dispatched == ["ios", "android"]
    dispatch_paths = [path for method, path, _body in orchestrator.requests if method == "POST"]
    assert len(dispatch_paths) == 2
    assert any("ios-physical-device.yml" in path for path in dispatch_paths)
    assert any("android-real-device.yml" in path for path in dispatch_paths)
    assert all("ci.yml" not in path and "release-autonomy.yml" not in path for path in dispatch_paths)


def test_orchestrator_refuses_unpublished_candidate_instead_of_pushing_or_creating_ref():
    orchestrator = FakeOrchestrator(published=False)
    with pytest.raises(WorkflowEvidenceError, match="already be published as a remote branch tip"):
        orchestrator.dispatch_required(spec=spec(platforms=("ios",)), candidate_revision=CANDIDATE)
    assert orchestrator.dispatched == []
    assert not any(method in {"POST", "PATCH", "PUT"} for method, _path, _body in orchestrator.requests)


def test_orchestrator_rejects_non_full_candidate_sha_before_remote_calls():
    orchestrator = FakeOrchestrator()
    with pytest.raises(WorkflowEvidenceError, match="full 40-character"):
        orchestrator.dispatch_required(spec=spec(platforms=("ios",)), candidate_revision="b" * 12)
    assert orchestrator.requests == []


def test_orchestration_secret_is_not_exposed_and_policy_defaults_fail_closed():
    config = GitHubPhysicalDeviceOrchestrationConfig(repository="owner/repo", token="dispatch-secret")
    assert "dispatch-secret" not in repr(config)

    policy = EngineeringOwnerPolicy()
    assert policy.physical_device_auto_dispatch is False
    assert policy.public()["physical_device_auto_dispatch"] is False
    assert policy.public()["remote_push_authority"] is False
    assert policy.public()["merge_authority"] is False
    assert policy.public()["deploy_authority"] is False


def test_auto_dispatch_is_projected_only_when_owner_requires_physical_ui_qualification():
    requested = spec()
    enabled = EngineeringOwnerPolicy(
        physical_device_required=True,
        physical_device_auto_dispatch=True,
    ).constrain_spec(requested)
    assert enabled.metadata["physical_device_required"] is True
    assert enabled.metadata["physical_device_auto_dispatch"] is True

    no_device_requirement = EngineeringOwnerPolicy(
        physical_device_required=False,
        physical_device_auto_dispatch=True,
    ).constrain_spec(requested)
    assert no_device_requirement.metadata["physical_device_required"] is False
    assert no_device_requirement.metadata["physical_device_auto_dispatch"] is False
