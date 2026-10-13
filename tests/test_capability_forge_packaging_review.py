from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.models import (
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    RiskAssessment,
)
from future_intelligence.capability_forge.package import CapabilityPackageBuilder


def test_packaging_requires_explicit_independent_review_approval(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "calc"
    source.mkdir(parents=True)
    (source / "capability.py").write_text(
        "def run(payload):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    spec = CapabilitySpec(
        id="spec-review-gate",
        gap_id="gap-review-gate",
        name="Review gate",
        purpose="Prove packaging cannot infer an approval",
        inputs={"type": "object"},
        outputs={"type": "object"},
    )
    plan = CapabilityPlan(
        id="plan-review-gate",
        spec_id=spec.id,
        route=CapabilityRoute.GENERATED,
        rationale="qualification regression",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False),
    )
    result = SimpleNamespace(
        work_order_id="work-review-gate",
        attempt_id="attempt-review-gate",
        candidate_revision="candidate-review-gate",
        changed_paths=("generated-capabilities/calc/capability.py",),
        status="qualified",
        qualified=True,
        qualification={"qualified": True},
        review={},
    )

    with pytest.raises(PermissionError, match="independently reviewed"):
        CapabilityPackageBuilder().build(
            spec=spec,
            plan=plan,
            execution_result=result,
            workspace_root=workspace,
            source_root="generated-capabilities/calc",
            output_root=tmp_path / "packages",
        )
