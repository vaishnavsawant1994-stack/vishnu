from __future__ import annotations

import pytest

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.action_runtime import GeneratedActionService
from security.approvals import ApprovalManager
from tools.registry import Risk, Tool, VerificationResult


class Registry:
    def __init__(self, tools=()):
        self._tools = {tool.name: tool for tool in tools}
        self.dispatched = []

    def get(self, name):
        return self._tools[name]

    def destination(self, parameters):
        for key in ("url", "domain", "path", "file_path", "destination"):
            if parameters.get(key):
                return str(parameters[key])
        return ""

    def effective_risk(self, tool, *, parameters=None, data_classification="internal"):
        return tool.minimum_risk if tool.minimum_risk is not None else tool.risk

    def authorize(self, tool, confirmed=False, *, parameters=None, data_classification="internal"):
        if tool.risk is Risk.READ_ONLY or confirmed:
            return PermissionDecision(True, False, "allowed")
        return PermissionDecision(False, True, "owner confirmation required")

    def dispatch(self, tool, parameters):
        self.dispatched.append((tool.name, dict(parameters)))
        return tool.handler(parameters)

    def verify_result(self, tool, parameters, result):
        if tool.verifier:
            verdict = tool.verifier(parameters, result)
            if isinstance(verdict, VerificationResult):
                return verdict
        return VerificationResult(tool.risk is Risk.READ_ONLY, "read-only", {})


def manifest(*, tools=("write.item",), risk="write", network=(), read=(), write=(), connectors=(), secrets=()):
    return {
        "schema_version": 2,
        "id": "generated.action.test",
        "name": "Generated action",
        "version": "1.0.0",
        "type": "generated_capability",
        "runtime": "governed_action_v2",
        "risk": risk,
        "permissions": {
            "allowed_tools": list(tools),
            "network_hosts": list(network),
            "filesystem_read": list(read),
            "filesystem_write": list(write),
            "connector_ids": list(connectors),
            "secret_names": list(secrets),
            "side_effects": ["qualified write"],
        },
        "forge": {"qualified": True, "review_decision": "approved"},
        "action_policy": {"owner_approval_required": True, "automatic_commit": False, "critical_actions_enabled": False},
    }


def service(tmp_path, registry):
    approvals = ApprovalManager(path=tmp_path / "trusted-actions.sqlite3")
    return GeneratedActionService(tmp_path / "capability-forge.sqlite3", tools=registry, approvals=approvals), approvals


def test_generated_action_stages_exact_ticket_and_never_dispatches_before_separate_commit(tmp_path):
    effects = []
    writer = Tool(
        name="write.item",
        description="write item",
        risk=Risk.REVERSIBLE,
        handler=lambda p: effects.append(p["value"]) or {"written": p["value"]},
        verifier=lambda p, r: VerificationResult(r.get("written") == p["value"], "observed", {}),
        verification_required=True,
        rollback=lambda p, _r: effects.remove(p["value"]),
        rollback_description="remove written value",
    )
    registry = Registry((writer,))
    forge, approvals = service(tmp_path, registry)
    staged = forge.stage(
        manifest=manifest(), manifest_digest="digest-1", parameters={"value": 7},
        calls=[{"tool": "write.item", "parameters": {"value": 7}}],
        owner_id="owner", device_id="device-a", session_id="session-a",
    )
    assert staged["state"] == "waiting_approval"
    assert effects == [] and registry.dispatched == []
    ticket = staged["approvals"][0]["approval_id"]
    forge.approve_ticket(ticket, owner_id="owner", device_id="device-a", session_id="session-a")
    assert effects == [] and approvals.record(ticket)["status"] == "approved"
    completed = forge.commit(
        staged["id"], manifest=manifest(), manifest_digest="digest-1",
        owner_id="owner", device_id="device-a", session_id="session-a",
    )
    assert completed["state"] == "completed"
    assert effects == [7]
    assert approvals.record(ticket)["status"] == "completed"


def test_generated_action_blocks_raw_secret_connector_network_and_write_path_scope(tmp_path):
    connector = Tool(
        name="write.item", description="connector write", risk=Risk.EXTERNAL_SIDE_EFFECT,
        connector_id="provider-x", handler=lambda p: {"ok": True},
        verifier=lambda _p, _r: VerificationResult(True, "verified", {}), verification_required=True,
    )
    forge, _ = service(tmp_path, Registry((connector,)))
    with pytest.raises(PermissionError, match="raw secret"):
        forge.stage(manifest=manifest(connectors=("provider-x",), secrets=("token",)), manifest_digest="d", parameters={}, calls=[{"tool":"write.item","parameters":{}}])
    with pytest.raises(PermissionError, match="connector"):
        forge.stage(manifest=manifest(), manifest_digest="d", parameters={}, calls=[{"tool":"write.item","parameters":{}}])
    with pytest.raises(PermissionError, match="network destination"):
        forge.stage(manifest=manifest(connectors=("provider-x",), network=("allowed.example",)), manifest_digest="d", parameters={}, calls=[{"tool":"write.item","parameters":{"url":"https://evil.example/x"}}])
    with pytest.raises(PermissionError, match="write scope"):
        forge.stage(manifest=manifest(connectors=("provider-x",), write=("safe/output",)), manifest_digest="d", parameters={}, calls=[{"tool":"write.item","parameters":{"path":"private/x.txt"}}])


def test_generated_action_rolls_back_prior_verified_effect_and_marks_uncertain_failed_dispatch_for_recovery(tmp_path):
    effects = []
    first = Tool(
        name="write.item", description="first write", risk=Risk.REVERSIBLE,
        handler=lambda p: effects.append(p["value"]) or {"written": p["value"]},
        verifier=lambda p, r: VerificationResult(r.get("written") == p["value"], "verified", {}),
        verification_required=True,
        rollback=lambda p, _r: effects.remove(p["value"]),
    )
    second = Tool(
        name="write.fail", description="uncertain write", risk=Risk.EXTERNAL_SIDE_EFFECT,
        handler=lambda _p: (_ for _ in ()).throw(RuntimeError("provider failure after dispatch boundary")),
        verifier=lambda _p, _r: VerificationResult(True, "verified", {}), verification_required=True,
    )
    registry = Registry((first, second))
    forge, approvals = service(tmp_path, registry)
    m = manifest(tools=("write.item", "write.fail"))
    staged = forge.stage(manifest=m, manifest_digest="d2", parameters={}, calls=[
        {"tool":"write.item","parameters":{"value":9}},
        {"tool":"write.fail","parameters":{}},
    ])
    for item in staged["approvals"]:
        forge.approve_ticket(item["approval_id"], owner_id="owner", device_id=None, session_id=None)
    with pytest.raises(RuntimeError):
        forge.commit(staged["id"], manifest=m, manifest_digest="d2", owner_id="owner", device_id=None, session_id=None)
    latest = forge.get(staged["id"])
    assert latest["state"] == "recovery_required"
    assert effects == []
    second_ticket = staged["approvals"][1]["approval_id"]
    assert approvals.record(second_ticket)["status"] == "recovery_required"


def test_generated_action_refuses_parameter_or_security_epoch_drift(tmp_path):
    writer = Tool(
        name="write.item", description="write", risk=Risk.REVERSIBLE, handler=lambda p: {"written": p["value"]},
        verifier=lambda _p, _r: VerificationResult(True, "verified", {}), verification_required=True,
        rollback=lambda _p, _r: None,
    )
    forge, approvals = service(tmp_path, Registry((writer,)))
    staged = forge.stage(manifest=manifest(), manifest_digest="d3", parameters={}, calls=[{"tool":"write.item","parameters":{"value":1}}])
    ticket = staged["approvals"][0]["approval_id"]
    forge.approve_ticket(ticket, owner_id="owner", device_id=None, session_id=None)
    approvals.advance_security_epoch()
    with pytest.raises(PermissionError, match="security epoch"):
        from future_intelligence.capability_forge.action_governance import GovernedGeneratedActionService
        secure = GovernedGeneratedActionService(tmp_path / "capability-forge.sqlite3", tools=forge.tools, approvals=approvals)
        secure.commit(staged["id"], manifest=manifest(), manifest_digest="d3", owner_id="owner", device_id=None, session_id=None)
