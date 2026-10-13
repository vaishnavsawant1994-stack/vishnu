from __future__ import annotations

from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.models import CapabilityPlan, CapabilityRisk, CapabilityRoute, CapabilitySpec, RiskAssessment
from future_intelligence.capability_forge.package import CapabilityPackageBuilder


def _execution():
    return SimpleNamespace(
        work_order_id="work", attempt_id="attempt", candidate_revision="candidate",
        changed_paths=("generated-capabilities/demo/capability.py",), status="qualified", qualified=True,
        qualification={"qualified": True}, review={"decision": "approved"},
    )


def _plan(spec_id: str):
    return CapabilityPlan(
        id="plan", spec_id=spec_id, route=CapabilityRoute.GENERATED, rationale="qualified",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False), owner_review_required=True,
    )


def test_v1_generated_runtime_cannot_claim_v2_ui_or_background_wrappers(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "demo"
    source.mkdir(parents=True)
    (source / "capability.py").write_text("def run(payload):\n    return payload\n", encoding="utf-8")
    for kwargs in ({"ui_required": True}, {"background_allowed": True}):
        spec = CapabilitySpec(
            id="spec-" + next(iter(kwargs)), gap_id="gap", name="Demo", purpose="Demo",
            inputs={"type": "object"}, outputs={"type": "object"}, acceptance_criteria=("works",),
            metadata={"runtime": "pure_python_v1", "entrypoint": "capability.py:run"}, **kwargs,
        )
        with pytest.raises(PermissionError, match="require governed_action_v2"):
            CapabilityPackageBuilder().build(
                spec=spec, plan=_plan(spec.id), execution_result=_execution(), workspace_root=workspace,
                source_root="generated-capabilities/demo", output_root=tmp_path / "packages" / spec.id,
                version="1.0.0",
            )
