from __future__ import annotations

from types import SimpleNamespace

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.action_governance import GovernedGeneratedActionService
from future_intelligence.capability_forge.models import CapabilityPlan, CapabilityRisk, CapabilityRoute, CapabilitySpec, RiskAssessment
from future_intelligence.capability_forge.package import CapabilityPackageBuilder
from integrations.discovery.generated_runtime_v2 import attach_generated_capability, validate_generated_manifest_authority_v2
from security.approvals import ApprovalManager
from tools.registry import Risk, Tool, VerificationResult


class Registry:
    def __init__(self, tools=()): self._tools={tool.name:tool for tool in tools}
    def register(self, tool): self._tools[tool.name]=tool
    def get(self, name): return self._tools[name]
    def destination(self, parameters): return str(parameters.get("url") or parameters.get("path") or "")
    def effective_risk(self, tool, *, parameters=None, data_classification="internal"): return tool.risk
    def authorize(self, tool, confirmed=False, *, parameters=None, data_classification="internal"):
        return PermissionDecision(bool(tool.risk is Risk.READ_ONLY or confirmed), bool(tool.risk is not Risk.READ_ONLY and not confirmed), "policy")
    def dispatch(self, tool, parameters): return tool.handler(parameters)
    def verify_result(self, tool, parameters, result): return tool.verifier(parameters,result) if tool.verifier else VerificationResult(tool.risk is Risk.READ_ONLY,"read",{})


def test_governed_action_package_freezes_ui_background_scope_and_stages_without_world_dispatch(tmp_path):
    workspace=tmp_path/"workspace"; source=workspace/"generated-capabilities"/"action"; source.mkdir(parents=True)
    (source/"capability.py").write_text("def plan(payload):\n    return {'calls':[{'tool':'write.item','parameters':{'value':payload.get('value',0)}}]}\n",encoding="utf-8")
    spec=CapabilitySpec(
        id="spec-v2",gap_id="gap-v2",name="Generated writer",purpose="Stage a governed write",
        inputs={"type":"object"},outputs={"type":"object"},side_effects=("write item",),
        background_allowed=True,ui_required=True,acceptance_criteria=("owner approval required",),
        metadata={
            "runtime":"governed_action_v2","allowed_tools":["write.item"],"entrypoint":"capability.py:plan",
            "ui":{"schema_version":1,"title":"Write item","fields":[{"name":"value","label":"Value","type":"integer","required":True}],"submit_label":"Stage write"},
        },
    )
    plan=CapabilityPlan(
        id="plan-v2",spec_id=spec.id,route=CapabilityRoute.GENERATED,rationale="qualified governed action",
        risk=RiskAssessment(CapabilityRisk.WRITE,("side effect",),True,True),owner_review_required=True,
    )
    execution=SimpleNamespace(
        work_order_id="work-v2",attempt_id="attempt-v2",candidate_revision="candidate-v2",
        changed_paths=("generated-capabilities/action/capability.py",),status="qualified",qualified=True,
        qualification={"qualified":True},review={"decision":"approved"},
    )
    package=CapabilityPackageBuilder().build(
        spec=spec,plan=plan,execution_result=execution,workspace_root=workspace,source_root="generated-capabilities/action",
        output_root=tmp_path/"data"/"generated-capabilities",version="1.0.0",
    )
    assert package.manifest["runtime"] == "governed_action_v2"
    assert package.manifest["permissions"]["background_allowed"] is True
    assert package.manifest["ui"]["fields"][0]["name"] == "value"
    assert package.manifest["action_policy"]["automatic_commit"] is False
    validate_generated_manifest_authority_v2(package.manifest)

    effects=[]
    writer=Tool(
        name="write.item",description="write",risk=Risk.REVERSIBLE,
        handler=lambda p: effects.append(p["value"]) or {"written":p["value"]},
        verifier=lambda p,r: VerificationResult(r.get("written")==p["value"],"verified",{}),verification_required=True,
        rollback=lambda p,_r: effects.remove(p["value"]),
    )
    registry=Registry((writer,)); approvals=ApprovalManager(path=tmp_path/"data"/"trusted-actions.sqlite3")
    actions=GovernedGeneratedActionService(tmp_path/"data"/"capability-forge.sqlite3",tools=registry,approvals=approvals)
    payload=package.catalog_payload(package_ref=package.package_path.relative_to(tmp_path/"data").as_posix(),state="active")
    generated=attach_generated_capability(payload,tools=registry,data_root=tmp_path/"data",action_service=actions)
    result=generated.handler({"value":12})
    assert result["committed"] is False
    assert result["owner_approval_required"] is True
    assert effects == []
    proposal=actions.get(result["proposal_id"])
    assert proposal["calls"][0]["tool"] == "write.item"
