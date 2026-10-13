from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge import CapabilityForgeService, CapabilityForgeStore
from future_intelligence.capability_forge.execution_bridge import CapabilityForgeExecutionBridge
from future_intelligence.capability_forge.governed_activation import GovernedCapabilityActivationService
from future_intelligence.capability_forge.lifecycle import CapabilityForgeLifecycle
from future_intelligence.capability_forge.package import CapabilityPackageBuilder
from future_intelligence.capability_forge.work_bridge import CapabilityForgeWorkBridge
from future_intelligence.work_orchestration.models import ReadinessStatus, WorkOrder, WorkOrderStatus, WorkPlan, WorkPlanStatus
from future_intelligence.work_orchestration.store import WorkStore
from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.generated_runtime import rehydrate_generated_capabilities
from security.approvals import ApprovalManager


class Registry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError("duplicate")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools[name]


class QualifiedEngineeringExecutor:
    def __init__(self, changed_path):
        self.changed_path = changed_path
        self.calls = []
        self.revision = "candidate-v1"

    def execute(self, work_order_id, **kwargs):
        self.calls.append((work_order_id, kwargs))
        return SimpleNamespace(
            work_order_id=work_order_id,
            attempt_id=f"attempt-{self.revision}",
            candidate_revision=self.revision,
            changed_paths=(self.changed_path,),
            qualification={"qualified": True, "gates": [{"gate": "tests", "status": "pass"}]},
            review={"decision": "approved", "reviewer": "independent"},
            status="qualified",
        )


def _approve(approvals, ticket_id, tool_name, parameters, destination):
    record = approvals.record(ticket_id)
    ticket = record["ticket"]
    approvals.approve(
        ticket_id,
        ticket.execution_id,
        tool_name,
        parameters,
        owner_id="owner",
        destination=destination,
        data_classification="internal",
    )


def _queue_projection(work_store, projection):
    queued = WorkOrder.from_dict({**projection.work_order.to_dict(), "status": WorkOrderStatus.QUEUED.value})
    ready = WorkPlan.from_dict(
        {
            **projection.work_plan.to_dict(),
            "status": WorkPlanStatus.READY.value,
            "readiness": ReadinessStatus.READY.value,
            "work_orders": [queued.to_dict()],
        }
    )
    work_store.save_plan(ready)
    return queued


def _record_packaged(lifecycle, package, spec, plan, candidate, data_root):
    package_ref = package.package_path.relative_to(data_root).as_posix()
    lifecycle.record_build(
        build_id=package.build_id,
        spec_id=spec.id,
        plan_id=plan.id,
        work_order_id=candidate.work_order_id,
        attempt_id=candidate.attempt_id,
        candidate_revision=candidate.candidate_revision,
        status="packaged",
        payload={
            **candidate.to_dict(),
            "package_ref": package_ref,
            "capability_id": package.capability_id,
            "version": package.version,
            "manifest_digest": package.manifest_digest,
        },
    )


def test_gap_to_generated_use_restart_upgrade_and_owner_approved_rollback(tmp_path):
    forge_store = CapabilityForgeStore(tmp_path / "forge.sqlite3")
    forge = CapabilityForgeService(forge_store)
    proposed = forge.propose(
        "project",
        {
            "capability_gap": True,
            "capability_name": "Normalization helper",
            "requested_outcome": "Normalize an integer into a deterministic generated result",
            "required_operations": ["normalize integer"],
        },
        requirements={
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "acceptance_criteria": ["Returns the expected normalized value."],
            "metadata": {"entrypoint": "capability.py:run"},
        },
    )
    assert proposed is not None
    gap, spec, plan = proposed
    assert gap.id and spec.id and plan.id

    work_store = WorkStore(tmp_path / "work.sqlite3")
    projection = CapabilityForgeWorkBridge(work_store).prepare_draft_work(
        spec,
        plan,
        repository="vaishnavsawant1994-stack/vishnu",
        allowed_paths=("generated-capabilities/normalization-helper",),
        project_id="project-forge-e2e",
    )
    assert projection.work_order.status is WorkOrderStatus.DRAFT
    queued = _queue_projection(work_store, projection)
    assert work_store.get_order(queued.id).status is WorkOrderStatus.QUEUED

    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "normalization-helper"
    source.mkdir(parents=True)
    capability_file = source / "capability.py"
    capability_file.write_text(
        "def run(payload):\n    return {'value': max(0, min(100, int(payload.get('value', 0))))}\n",
        encoding="utf-8",
    )

    executor = QualifiedEngineeringExecutor("generated-capabilities/normalization-helper/capability.py")
    execution = CapabilityForgeExecutionBridge(work_store, executor)
    candidate_v1 = execution.execute_candidate(spec, plan, work_order_id=queued.id, runtime_epoch=1)
    assert candidate_v1.qualified is True
    assert executor.calls and executor.calls[0][0] == queued.id

    data_root = tmp_path / "data"
    builder = CapabilityPackageBuilder()
    package_v1 = builder.build(
        spec=spec,
        plan=plan,
        execution_result=candidate_v1,
        workspace_root=workspace,
        source_root="generated-capabilities/normalization-helper",
        output_root=data_root / "generated-capabilities",
        version="1.0.0",
    )

    lifecycle = CapabilityForgeLifecycle(data_root / "capability-forge.sqlite3")
    _record_packaged(lifecycle, package_v1, spec, plan, candidate_v1, data_root)
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    approvals = ApprovalManager(path=data_root / "trusted-actions.sqlite3")
    registry = Registry()
    activation = GovernedCapabilityActivationService(
        catalog=catalog,
        approvals=approvals,
        tools=registry,
        data_root=data_root,
        lifecycle=lifecycle,
    )

    decision_v1 = activation.request_activation(package_v1)
    with pytest.raises(PermissionError, match="owner approval"):
        activation.activate(package_v1, ticket_id=decision_v1.ticket_id)
    _approve(approvals, decision_v1.ticket_id, activation.ACTIVATE_TOOL, decision_v1.parameters(), package_v1.capability_id)
    active_v1 = activation.activate(package_v1, ticket_id=decision_v1.ticket_id)
    assert active_v1["approved"] is True
    assert registry.get(package_v1.capability_id).handler({"value": 140}) == {"value": 100}
    assert lifecycle.metrics(package_v1.capability_id)["successes"] == 1

    restarted = Registry()
    attached = rehydrate_generated_capabilities(catalog, tools=restarted, data_root=data_root)
    assert package_v1.capability_id in attached
    assert restarted.get(package_v1.capability_id).handler({"value": -3}) == {"value": 0}

    capability_file.write_text(
        "def run(payload):\n    return {'value': max(0, min(200, int(payload.get('value', 0))))}\n",
        encoding="utf-8",
    )
    executor.revision = "candidate-v2"
    candidate_v2 = execution.execute_candidate(spec, plan, work_order_id=queued.id, runtime_epoch=2)
    package_v2 = builder.build(
        spec=spec,
        plan=plan,
        execution_result=candidate_v2,
        workspace_root=workspace,
        source_root="generated-capabilities/normalization-helper",
        output_root=data_root / "generated-capabilities",
        version="1.1.0",
    )
    _record_packaged(lifecycle, package_v2, spec, plan, candidate_v2, data_root)
    decision_v2 = activation.request_activation(package_v2)
    _approve(approvals, decision_v2.ticket_id, activation.ACTIVATE_TOOL, decision_v2.parameters(), package_v2.capability_id)
    activation.activate(package_v2, ticket_id=decision_v2.ticket_id)
    assert registry.get(package_v2.capability_id).handler({"value": 140}) == {"value": 140}

    rollback_ticket, target = activation.request_rollback(package_v2.capability_id)
    assert target["version"] == "1.0.0"
    rollback_parameters = {
        "capability_id": package_v2.capability_id,
        "target_activation_id": target["id"],
        "target_version": target["version"],
        "manifest_digest": target["manifest_digest"],
    }
    _approve(approvals, rollback_ticket, activation.ROLLBACK_TOOL, rollback_parameters, package_v2.capability_id)
    rolled = activation.rollback(
        package_v2.capability_id,
        ticket_id=rollback_ticket,
        target_activation_id=target["id"],
    )
    assert rolled["capability"]["version"] == "1.0.0"
    assert catalog.get(package_v2.capability_id)["version"] == "1.0.0"
    assert registry.get(package_v2.capability_id).handler({"value": 140}) == {"value": 100}
