from __future__ import annotations

import pytest

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.action_governance import GovernedGeneratedActionService
from security.approvals import ApprovalManager
from tools.registry import Risk, Tool, VerificationResult


class Registry:
    def __init__(self, tool): self._tools={tool.name:tool}
    def get(self,name): return self._tools[name]
    def destination(self,parameters): return str(parameters.get("endpoint") or parameters.get("base_url") or parameters.get("uri") or "")
    def effective_risk(self,tool,*,parameters=None,data_classification="internal"): return tool.risk
    def authorize(self,tool,confirmed=False,*,parameters=None,data_classification="internal"):
        return PermissionDecision(bool(confirmed),not bool(confirmed),"approval required")
    def dispatch(self,tool,parameters): return tool.handler(parameters)
    def verify_result(self,tool,parameters,result): return VerificationResult(True,"verified",{})


def manifest():
    return {
        "id":"generated.action.endpoint","version":"1.0.0","runtime":"governed_action_v2","risk":"write",
        "permissions":{
            "allowed_tools":["write.remote"],"network_hosts":["allowed.example"],"filesystem_read":[],
            "filesystem_write":[],"connector_ids":[],"secret_names":[],"side_effects":["remote write"],
        },
        "forge":{"qualified":True,"review_decision":"approved"},
        "action_policy":{"owner_approval_required":True,"automatic_commit":False,"critical_actions_enabled":False},
    }


@pytest.mark.parametrize("key",["endpoint","endpoint_url","base_url","uri","webhook_url","callback_url","redirect_uri"])
def test_generated_action_rejects_nested_network_endpoint_alias_outside_frozen_host_scope(tmp_path,key):
    tool=Tool(
        name="write.remote",description="remote write",risk=Risk.EXTERNAL_SIDE_EFFECT,
        handler=lambda _p:{"ok":True},verifier=lambda _p,_r:VerificationResult(True,"verified",{}),
        verification_required=True,
    )
    service=GovernedGeneratedActionService(
        tmp_path/"capability-forge.sqlite3",tools=Registry(tool),
        approvals=ApprovalManager(path=tmp_path/"trusted-actions.sqlite3"),
    )
    with pytest.raises(PermissionError,match="network destination"):
        service.stage(
            manifest=manifest(),manifest_digest="digest",parameters={},
            calls=[{"tool":"write.remote","parameters":{"nested":{key:"https://evil.example/write"}}}],
        )


def test_generated_action_accepts_scoped_subdomain_endpoint_alias_and_only_stages_ticket(tmp_path):
    effects=[]
    tool=Tool(
        name="write.remote",description="remote write",risk=Risk.EXTERNAL_SIDE_EFFECT,
        handler=lambda p:effects.append(p) or {"ok":True},
        verifier=lambda _p,_r:VerificationResult(True,"verified",{}),verification_required=True,
    )
    approvals=ApprovalManager(path=tmp_path/"trusted-actions.sqlite3")
    service=GovernedGeneratedActionService(tmp_path/"capability-forge.sqlite3",tools=Registry(tool),approvals=approvals)
    staged=service.stage(
        manifest=manifest(),manifest_digest="digest",parameters={},
        calls=[{"tool":"write.remote","parameters":{"endpoint":"https://api.allowed.example/write"}}],
    )
    assert staged["state"]=="waiting_approval"
    assert effects==[]
    assert len(staged["approvals"])==1
