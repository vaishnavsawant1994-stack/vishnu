from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.action_governance import GovernedGeneratedActionService
from integrations.discovery.generated_runtime_v2 import ACTION_VERIFICATION_METHOD
from security.approvals import ApprovalManager
from server.capability_forge_ui import JS
from tools.registry import Risk, Tool, ToolRegistry, VerificationResult


class _Registry:
    def __init__(self, tool):
        self._tools = {tool.name: tool}

    def get(self, name):
        return self._tools[name]

    def destination(self, parameters):
        return str(parameters.get("destination") or "")

    def effective_risk(self, tool, *, parameters=None, data_classification="internal"):
        return tool.risk

    def authorize(self, tool, confirmed=False, *, parameters=None, data_classification="internal"):
        return PermissionDecision(bool(confirmed), not bool(confirmed), "approval required")

    def dispatch(self, tool, parameters):
        return tool.handler(parameters)

    def verify_result(self, tool, parameters, result):
        return VerificationResult(True, "verified", {})


def _manifest():
    return {
        "id": "generated.action.secure",
        "version": "1.0.0",
        "runtime": "governed_action_v2",
        "risk": "write",
        "permissions": {
            "allowed_tools": ["write.item"],
            "network_hosts": [],
            "filesystem_read": [],
            "filesystem_write": [],
            "connector_ids": [],
            "secret_names": [],
            "side_effects": ["write item"],
        },
        "forge": {"qualified": True, "review_decision": "approved"},
        "action_policy": {"owner_approval_required": True, "automatic_commit": False, "critical_actions_enabled": False},
    }


def test_governed_generated_action_service_rejects_non_internal_classification_before_ticket_creation(tmp_path):
    tool = Tool(
        name="write.item",
        description="write item",
        risk=Risk.REVERSIBLE,
        handler=lambda parameters: {"ok": True},
        verifier=lambda _parameters, _result: VerificationResult(True, "verified", {}),
        verification_required=True,
        rollback=lambda _parameters, _result: None,
    )
    approvals = ApprovalManager(path=tmp_path / "trusted-actions.sqlite3")
    service = GovernedGeneratedActionService(
        tmp_path / "generated-actions.sqlite3",
        tools=_Registry(tool),
        approvals=approvals,
    )
    for classification in ("sensitive", "secret", "restricted"):
        with pytest.raises(PermissionError, match="cannot receive sensitive"):
            service.stage(
                manifest=_manifest(),
                manifest_digest="digest",
                parameters={"value": 1},
                calls=[{"tool": "write.item", "parameters": {"value": 1}}],
                data_classification=classification,
            )
    assert approvals.list_pending() == []


def test_generated_action_tool_contract_blocks_sensitive_secret_and_restricted_data_classes():
    tool = Tool(
        name="generated.action.secure",
        description="generated action planner",
        handler=lambda _parameters: {"proposal_id": "proposal", "committed": False},
        risk=Risk.READ_ONLY,
        capability="generated.action.secure",
        verification_method=ACTION_VERIFICATION_METHOD,
        prohibited_data_classifications=("sensitive", "secret", "restricted"),
    )
    settings = SimpleNamespace(autonomy_mode="act", data_dir=None)
    registry = ToolRegistry(settings)
    registry.register(tool)
    for classification in ("sensitive", "secret", "restricted"):
        decision = registry.authorize(tool, parameters={}, data_classification=classification)
        assert decision.allowed is False
        assert "prohibited" in decision.reason


def test_v2_forge_console_surfaces_actions_schedules_ui_and_improvements_without_approval_authority():
    assert "api('/actions')" in JS
    assert "/actions/${encodeURIComponent(b.dataset.commitAction)}/commit" in JS
    assert "/actions/${encodeURIComponent(b.dataset.cancelAction)}/cancel" in JS
    assert "/schedule" in JS
    assert "/improve" in JS
    assert "/ui`" in JS
    assert "/invoke`" in JS
    assert "data-generated-form" in JS
    assert "data-generated-field" in JS
    assert "Generated action staged. No world side effect was committed." in JS
    assert "Approvals Center" in JS
    assert "Forge cannot approve its own ticket" in JS
    assert "Sensitive, secret and restricted inputs are blocked" in JS
    assert "/approvals/" not in JS
