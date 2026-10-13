from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.governed_activation import GovernedCapabilityActivationService
from future_intelligence.capability_forge.lifecycle import CapabilityForgeLifecycle
from security.approvals import ApprovalManager


class Catalog:
    def get(self, _capability_id):
        return None


class Registry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        self._tools[tool.name] = tool


def _package(tmp_path):
    package_path = tmp_path / "generated-capabilities" / "generated.test" / "1.0.0"
    package_path.mkdir(parents=True)
    return SimpleNamespace(
        capability_id="generated.test",
        version="1.0.0",
        package_path=package_path,
        manifest_digest="digest-1",
        build_id="build:attempt-1",
        manifest={
            "type": "generated_capability",
            "runtime": "pure_python_v1",
            "risk": "read",
            "permissions": {
                "network_hosts": [], "filesystem_read": [], "filesystem_write": [],
                "secret_names": [], "connector_ids": [], "side_effects": [],
                "background_allowed": False, "ui_required": False,
            },
            "forge": {
                "qualified": True,
                "review_decision": "approved",
                "spec_id": "spec-1",
                "plan_id": "plan-1",
            },
        },
    )


def test_governed_activation_rejects_manifest_without_server_build_lineage(tmp_path):
    lifecycle = CapabilityForgeLifecycle(tmp_path / "capability-forge.sqlite3")
    service = GovernedCapabilityActivationService(
        catalog=Catalog(),
        approvals=ApprovalManager(),
        tools=Registry(),
        data_root=tmp_path,
        lifecycle=lifecycle,
    )
    package = _package(tmp_path)

    with pytest.raises(PermissionError, match="server-recorded packaged build"):
        service.request_activation(package)


def test_governed_activation_accepts_exact_packaged_lineage_for_ticket_creation(tmp_path):
    lifecycle = CapabilityForgeLifecycle(tmp_path / "capability-forge.sqlite3")
    service = GovernedCapabilityActivationService(
        catalog=Catalog(),
        approvals=ApprovalManager(),
        tools=Registry(),
        data_root=tmp_path,
        lifecycle=lifecycle,
    )
    package = _package(tmp_path)
    lifecycle.record_build(
        build_id=package.build_id,
        spec_id="spec-1",
        plan_id="plan-1",
        work_order_id="work-1",
        attempt_id="attempt-1",
        candidate_revision="candidate-1",
        status="packaged",
        payload={
            "capability_id": package.capability_id,
            "version": package.version,
            "manifest_digest": package.manifest_digest,
        },
    )

    decision = service.request_activation(package)

    assert decision.capability_id == package.capability_id
    assert decision.ticket_id
    assert service.approvals.record(decision.ticket_id)["status"] == "pending"
