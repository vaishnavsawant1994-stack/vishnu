from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.environment_qualification import (
    HttpQualificationProbe,
    ReadOnlyHttpQualificationProvider,
)
from future_intelligence.engineering.qualification import EngineeringQualification
from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult
from future_intelligence.engineering.trusted_qualification import (
    EngineeringTrustedQualificationIntake,
    PhysicalDeviceQualificationEvidence,
    RegressionTestEvidence,
    preview_observation,
)
from future_intelligence.work_orchestration import (
    DurableWorkStore,
    GoalSpec,
    ResourceScope,
    WorkOrder,
    WorkOrderStatus,
    WorkPlan,
)
from future_intelligence.work_orchestration.engineering_bridge import engineering_spec_from_work_order


class _Response:
    status_code = 200
    encoding = "utf-8"

    def iter_content(self, chunk_size=65536):
        yield b"healthy preview"


class _Session:
    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        return _Response()


class _EventStore:
    def __init__(self):
        self.events = []

    def append_work_event(self, work_order_id, event_type, payload, *, attempt_id=None):
        self.events.append((work_order_id, event_type, dict(payload), attempt_id))


class _Finalizer:
    def __init__(self, spec, revision="b" * 40):
        self.spec = spec
        self.revision = revision
        self.runtime = SimpleNamespace(work_store=_EventStore())
        self.finalize_calls = []

    def _workspace_and_spec(self, work_order_id, attempt_id):
        assert work_order_id == self.spec.work_order_id
        assert attempt_id == self.spec.attempt_id
        return object(), object(), self.spec, object(), self.revision, ("src/app.py",)

    def finalize(self, work_order_id, attempt_id, **kwargs):
        self.finalize_calls.append((work_order_id, attempt_id, kwargs))
        return "qualified-result"


def _spec(**metadata):
    return EngineeringSpec(
        id="eng-trusted",
        work_order_id="work-trusted",
        attempt_id="attempt-trusted",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="repair a reproducible defect",
        requirements=("repair the defect",),
        allowed_paths=("src/",),
        metadata=metadata,
    )


def test_preview_probe_is_bound_to_spec_and_exact_candidate_revision():
    revision = "b" * 40
    provider = ReadOnlyHttpQualificationProvider(
        (HttpQualificationProbe("health", "/health", required_text="healthy"),),
        allowed_hosts=("preview.example",),
        session=_Session(),
    )
    result = provider.qualify_preview(
        target="https://preview.example",
        spec_id="eng-trusted",
        candidate_revision=revision,
    )
    assert result.passed
    assert f"binding=spec:eng-trusted;revision:{revision}" in result.evidence
    observation = preview_observation(result, candidate_revision=revision, spec_id="eng-trusted")
    assert observation.gate == "preview" and observation.passed
    assert observation.metadata["candidate_revision"] == revision


def test_preview_observation_rejects_wrong_revision_or_production_result():
    revision = "b" * 40
    preview = EnvironmentQualificationResult(
        "preview", "https://preview.example", True, {"health": True},
        ("health:sha256=abc", f"binding=spec:eng-trusted;revision:{revision}"),
    )
    with pytest.raises(PermissionError, match="not bound"):
        preview_observation(preview, candidate_revision="c" * 40, spec_id="eng-trusted")
    production = EnvironmentQualificationResult(
        "production", "https://prod.example", True, {"health": True},
        (f"binding=spec:eng-trusted;revision:{revision}",),
    )
    with pytest.raises(ValueError, match="preview environment"):
        preview_observation(production, candidate_revision=revision, spec_id="eng-trusted")


def test_physical_device_gate_rejects_simulator_even_when_checks_pass():
    revision = "b" * 40
    simulated = PhysicalDeviceQualificationEvidence(
        revision, "ios", "iPhone Simulator", False,
        {"launch": True, "keyboard": True, "safe_area": True},
        ("device-run:sim-1",),
    ).to_observation()
    assert simulated.gate == "physical_device"
    assert not simulated.passed
    physical = PhysicalDeviceQualificationEvidence(
        revision, "ios", "iPhone 15", True,
        {"launch": True, "keyboard": True, "safe_area": True},
        ("device-run:physical-1",),
    ).to_observation()
    assert physical.passed
    assert physical.metadata["physical"] is True


def test_regression_test_becomes_blocking_gate_and_must_match_failure_fingerprint():
    revision = "b" * 40
    spec = _spec(regression_test_required=True, failure_fingerprint="failure-123")
    report = EngineeringQualification().report(spec=spec, candidate_revision=revision, observations=())
    statuses = {gate.gate: gate.status.value for gate in report.gates}
    assert statuses["regression_test"] == "pending"

    evidence = RegressionTestEvidence(
        revision, "failure-123", "tests/test_bug.py::test_original_failure", True,
        ("pytest:tests/test_bug.py::test_original_failure",),
    )
    observation = evidence.to_observation()
    assert observation.gate == "regression_test" and observation.passed

    intake = EngineeringTrustedQualificationIntake(_Finalizer(spec, revision))
    wrong = RegressionTestEvidence(
        revision, "other-failure", "tests/test_bug.py::test_wrong", True, ("pytest:wrong",)
    )
    with pytest.raises(PermissionError, match="failure fingerprint"):
        intake.finalize(
            spec.work_order_id,
            spec.attempt_id,
            requirement_traces=(),
            regression_test_evidence=wrong,
        )


def test_preview_request_is_revision_bound_and_has_no_release_authority():
    revision = "b" * 40
    spec = _spec(preview_enabled=True)
    finalizer = _Finalizer(spec, revision)
    intake = EngineeringTrustedQualificationIntake(finalizer)
    request = intake.prepare_preview_request(spec.work_order_id, spec.attempt_id)
    payload = request.to_dict()
    assert payload["candidate_revision"] == revision
    assert payload["deployment_authority"] is False
    assert payload["push_authority"] is False
    assert payload["merge_authority"] is False
    assert finalizer.runtime.work_store.events[-1][1] == "engineering.preview.requested"


def test_canonical_work_regression_metadata_projects_monotonically():
    goal = GoalSpec(id="goal-regression", title="Repair bug", objective="Repair bug", desired_outcome="Fixed")
    order = WorkOrder(
        id="work-regression",
        plan_id="plan-regression",
        title="Repair bug",
        objective="Repair bug",
        worker_type="software_engineer",
        status=WorkOrderStatus.QUEUED,
        resource_scope=ResourceScope(allowed_repositories=("owner/repo",), allowed_paths=("src/",)),
        verification_strategy={"failure_fingerprint": "failure-abc", "regression_test_required": True},
    )
    spec = engineering_spec_from_work_order(
        order,
        attempt_id="attempt-regression",
        repository="owner/repo",
        base_revision="a" * 40,
    )
    assert spec.metadata["failure_fingerprint"] == "failure-abc"
    assert spec.metadata["regression_test_required"] is True
    assert "regression_test" in EngineeringQualification().required_gates(spec)


def test_canonical_work_store_can_be_read_from_server_thread(tmp_path):
    store = DurableWorkStore(tmp_path / "work.sqlite3")
    goal = GoalSpec(id="goal-thread", title="Thread safe Work", objective="Read from API thread", desired_outcome="Readable")
    store.upsert_goal(goal)
    order = WorkOrder(
        id="work-thread",
        plan_id="plan-thread",
        title="Thread safe Work",
        objective="Read from API thread",
        worker_type="reviewer",
        status=WorkOrderStatus.QUEUED,
    )
    store.save_plan(WorkPlan(id="plan-thread", goal_id=goal.id, version=1, summary="Thread test", work_orders=(order,)))
    result = []
    errors = []

    def read_from_server_thread():
        try:
            result.append(store.get_order(order.id))
        except Exception as exc:  # pragma: no cover - assertion below exposes it
            errors.append(exc)

    thread = threading.Thread(target=read_from_server_thread)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert result and result[0].id == order.id
