from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.activation import CapabilityActivationService
from future_intelligence.capability_forge.lifecycle import CapabilityForgeLifecycle
from future_intelligence.capability_forge.models import (
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    RiskAssessment,
)
from future_intelligence.capability_forge.package import CapabilityPackageBuilder
from integrations.discovery.catalog_store import CapabilityCatalogStore
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


def _spec():
    return CapabilitySpec(
        id="spec-calc",
        gap_id="gap-calc",
        name="Normalized calculator",
        purpose="Normalize numeric values",
        inputs={"type": "object"},
        outputs={"type": "object"},
        acceptance_criteria=("returns normalized value",),
        metadata={"entrypoint": "capability.py:run"},
    )


def _plan(spec):
    return CapabilityPlan(
        id="plan-calc",
        spec_id=spec.id,
        route=CapabilityRoute.GENERATED,
        rationale="pure local calculation",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False),
        owner_review_required=True,
    )


def _execution(revision, changed):
    return SimpleNamespace(
        work_order_id="work-calc",
        attempt_id=f"attempt-{revision}",
        candidate_revision=revision,
        changed_paths=(changed,),
        status="qualified",
        qualified=True,
        qualification={"qualified": True, "gates": [{"gate": "tests", "status": "pass"}]},
        review={"decision": "approved", "reviewer": "independent"},
    )


def _approve(approvals, ticket_id, tool_name, parameters, *, destination):
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


def test_qualified_candidate_packages_and_requires_preexisting_owner_approval_before_activation(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "calc"
    source.mkdir(parents=True)
    (source / "capability.py").write_text(
        "def run(payload):\n    value = float(payload.get('value', 0))\n    return {'normalized': max(0.0, min(1.0, value))}\n",
        encoding="utf-8",
    )
    spec = _spec()
    plan = _plan(spec)
    execution = _execution("sha-v1", "generated-capabilities/calc/capability.py")
    data_root = tmp_path / "data"
    package = CapabilityPackageBuilder().build(
        spec=spec,
        plan=plan,
        execution_result=execution,
        workspace_root=workspace,
        source_root="generated-capabilities/calc",
        output_root=data_root / "generated-capabilities",
        version="1.0.0",
    )

    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    approvals = ApprovalManager()
    registry = Registry()
    lifecycle = CapabilityForgeLifecycle(data_root / "capability-forge.sqlite3")
    service = CapabilityActivationService(
        catalog=catalog,
        approvals=approvals,
        tools=registry,
        data_root=data_root,
        lifecycle=lifecycle,
    )

    decision = service.request_activation(package)
    with pytest.raises(PermissionError, match="owner approval"):
        service.activate(package, ticket_id=decision.ticket_id)

    _approve(
        approvals,
        decision.ticket_id,
        service.ACTIVATE_TOOL,
        decision.parameters(),
        destination=package.capability_id,
    )
    activated = service.activate(package, ticket_id=decision.ticket_id)

    assert activated["approved"] is True
    stored = catalog.get(package.capability_id)
    assert stored["type"] == "generated_capability"
    assert stored["state"] == "active"
    assert stored["version"] == "1.0.0"
    assert registry.get(package.capability_id).handler({"value": 1.7}) == {"normalized": 1.0}
    metrics = lifecycle.metrics(package.capability_id)
    assert metrics["samples"] == 1
    assert metrics["successes"] == 1


def test_generated_capability_version_upgrade_and_owner_approved_rollback(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "calc"
    source.mkdir(parents=True)
    spec = _spec()
    plan = _plan(spec)
    data_root = tmp_path / "data"
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    approvals = ApprovalManager()
    registry = Registry()
    lifecycle = CapabilityForgeLifecycle(data_root / "capability-forge.sqlite3")
    service = CapabilityActivationService(
        catalog=catalog,
        approvals=approvals,
        tools=registry,
        data_root=data_root,
        lifecycle=lifecycle,
    )

    def build(version, revision, increment):
        (source / "capability.py").write_text(
            f"def run(payload):\n    return {{'value': int(payload.get('value', 0)) + {increment}}}\n",
            encoding="utf-8",
        )
        return CapabilityPackageBuilder().build(
            spec=spec,
            plan=plan,
            execution_result=_execution(revision, "generated-capabilities/calc/capability.py"),
            workspace_root=workspace,
            source_root="generated-capabilities/calc",
            output_root=data_root / "generated-capabilities",
            version=version,
        )

    p1 = build("1.0.0", "sha-v1", 1)
    d1 = service.request_activation(p1)
    _approve(approvals, d1.ticket_id, service.ACTIVATE_TOOL, d1.parameters(), destination=p1.capability_id)
    a1 = service.activate(p1, ticket_id=d1.ticket_id)

    p2 = build("1.1.0", "sha-v2", 2)
    d2 = service.request_activation(p2)
    _approve(approvals, d2.ticket_id, service.ACTIVATE_TOOL, d2.parameters(), destination=p2.capability_id)
    service.activate(p2, ticket_id=d2.ticket_id)
    assert registry.get(p2.capability_id).handler({"value": 5}) == {"value": 7}

    rollback_ticket, target = service.request_rollback(p2.capability_id)
    assert target["version"] == "1.0.0"
    parameters = {
        "capability_id": p2.capability_id,
        "target_activation_id": target["id"],
        "target_version": target["version"],
        "manifest_digest": target["manifest_digest"],
    }
    _approve(
        approvals,
        rollback_ticket,
        service.ROLLBACK_TOOL,
        parameters,
        destination=p2.capability_id,
    )
    rolled = service.rollback(
        p2.capability_id,
        ticket_id=rollback_ticket,
        target_activation_id=target["id"],
    )
    assert rolled["capability"]["version"] == "1.0.0"
    assert catalog.get(p2.capability_id)["version"] == "1.0.0"
    assert registry.get(p2.capability_id).handler({"value": 5}) == {"value": 6}
    assert lifecycle.active_activation(p2.capability_id)["id"] == a1["activation_id"]
