from types import SimpleNamespace

import pytest

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.models import (
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    RiskAssessment,
)
from future_intelligence.capability_forge.package import CapabilityPackageBuilder
from integrations.discovery.generated_runtime import (
    GeneratedCapabilitySecurityError,
    attach_approved_generated_capability,
)
from tools.registry import Risk, Tool, VerificationResult


class Registry:
    def __init__(self, tools=(), *, allow=True):
        self._tools = {tool.name: tool for tool in tools}
        self.allow = allow

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError("duplicate")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools[name]

    def effective_risk(self, tool, *, parameters=None, data_classification="internal"):
        return tool.minimum_risk or tool.risk

    def authorize(self, tool, confirmed=False, *, parameters=None, data_classification="internal"):
        if not self.allow:
            return PermissionDecision(False, False, "blocked by owner permission rule")
        return PermissionDecision(True, False, "read-only action")

    def dispatch(self, tool, parameters):
        return tool.handler(parameters)

    def verify_result(self, tool, parameters, result):
        if tool.verifier:
            return tool.verifier(parameters, result)
        return VerificationResult(True, "read-only", {})


def _execution(changed):
    return SimpleNamespace(
        work_order_id="work-toolchain",
        attempt_id="attempt-toolchain",
        candidate_revision="candidate-toolchain",
        changed_paths=(changed,),
        status="qualified",
        qualified=True,
        qualification={"qualified": True},
        review={"decision": "approved", "reviewer": "independent"},
    )


def _spec(*, allowed_tools=("source.read",), side_effects=(), secret_names=()):
    return CapabilitySpec(
        id="spec-toolchain",
        gap_id="gap-toolchain",
        name="Governed reader",
        purpose="Read through an already-approved Vishnu capability and normalize the result",
        inputs={"type": "object"},
        outputs={"type": "object"},
        side_effects=tuple(side_effects),
        secret_names=tuple(secret_names),
        acceptance_criteria=("returns normalized verified data",),
        metadata={
            "runtime": "governed_toolchain_v1",
            "allowed_tools": list(allowed_tools),
            "entrypoint": "capability.py:plan",
            "reducer": "capability.py:reduce",
        },
    )


def _plan(spec):
    return CapabilityPlan(
        id="plan-toolchain",
        spec_id=spec.id,
        route=CapabilityRoute.GENERATED,
        rationale="requires safe composition of an existing read-only tool",
        risk=RiskAssessment(CapabilityRisk.READ, (), True, False),
        owner_review_required=True,
    )


def _package(tmp_path, source_text, *, spec=None):
    spec = spec or _spec()
    workspace = tmp_path / "workspace"
    source = workspace / "generated-capabilities" / "reader"
    source.mkdir(parents=True)
    (source / "capability.py").write_text(source_text, encoding="utf-8")
    package = CapabilityPackageBuilder().build(
        spec=spec,
        plan=_plan(spec),
        execution_result=_execution("generated-capabilities/reader/capability.py"),
        workspace_root=workspace,
        source_root="generated-capabilities/reader",
        output_root=tmp_path / "data" / "generated-capabilities",
        version="1.0.0",
    )
    return package


def _payload(package, tmp_path):
    return package.catalog_payload(
        package_ref=package.package_path.relative_to(tmp_path / "data").as_posix(),
        state="active",
    )


def test_governed_toolchain_brokers_only_allowlisted_verified_read_only_tool(tmp_path):
    package = _package(
        tmp_path,
        "def plan(payload):\n"
        "    return {'calls': [{'tool': 'source.read', 'parameters': {'value': payload.get('value', 0)}}]}\n"
        "def reduce(payload):\n"
        "    row = payload['results'][0]['result']\n"
        "    return {'normalized': int(row['value']) * 2}\n",
    )
    read_tool = Tool(
        name="source.read",
        description="read source value",
        risk=Risk.READ_ONLY,
        handler=lambda parameters: {"value": int(parameters.get("value", 0)) + 1},
        verifier=lambda _parameters, result: VerificationResult(result.get("value") is not None, "observed", {}),
        verification_required=True,
    )
    registry = Registry((read_tool,))
    generated = attach_approved_generated_capability(
        _payload(package, tmp_path),
        tools=registry,
        data_root=tmp_path / "data",
    )

    assert generated.verification_method == "qualified_generated_toolchain_runtime"
    assert generated.handler({"value": 4}) == {"normalized": 10}


def test_governed_toolchain_blocks_unlisted_and_side_effecting_tools(tmp_path):
    package = _package(
        tmp_path,
        "def plan(payload):\n"
        "    return {'calls': [{'tool': 'writer.send', 'parameters': {'value': 1}}]}\n"
        "def reduce(payload):\n"
        "    return {'ok': True}\n",
    )
    writer = Tool(
        name="writer.send",
        description="send external write",
        risk=Risk.EXTERNAL_SIDE_EFFECT,
        handler=lambda parameters: {"sent": True},
    )
    registry = Registry((writer,))
    generated = attach_approved_generated_capability(
        _payload(package, tmp_path),
        tools=registry,
        data_root=tmp_path / "data",
    )
    with pytest.raises(GeneratedCapabilitySecurityError, match="outside its immutable allowlist"):
        generated.handler({})

    package2 = _package(
        tmp_path / "second",
        "def plan(payload):\n"
        "    return {'calls': [{'tool': 'writer.send', 'parameters': {'value': 1}}]}\n"
        "def reduce(payload):\n"
        "    return {'ok': True}\n",
        spec=_spec(allowed_tools=("writer.send",)),
    )
    registry2 = Registry((writer,))
    generated2 = attach_approved_generated_capability(
        _payload(package2, tmp_path / "second"),
        tools=registry2,
        data_root=tmp_path / "second" / "data",
    )
    with pytest.raises(GeneratedCapabilitySecurityError, match="read-only"):
        generated2.handler({})


def test_governed_toolchain_respects_owner_policy_denial(tmp_path):
    package = _package(
        tmp_path,
        "def plan(payload):\n"
        "    return {'calls': [{'tool': 'source.read', 'parameters': {}}]}\n"
        "def reduce(payload):\n"
        "    return {'ok': True}\n",
    )
    read_tool = Tool(name="source.read", description="read", risk=Risk.READ_ONLY, handler=lambda _p: {"ok": True})
    registry = Registry((read_tool,), allow=False)
    generated = attach_approved_generated_capability(
        _payload(package, tmp_path),
        tools=registry,
        data_root=tmp_path / "data",
    )
    with pytest.raises(PermissionError, match="owner permission"):
        generated.handler({})


def test_governed_toolchain_package_rejects_raw_secret_or_side_effect_authority(tmp_path):
    source = (
        "def plan(payload):\n    return {'calls': []}\n"
        "def reduce(payload):\n    return {'ok': True}\n"
    )
    with pytest.raises(PermissionError, match="raw secrets"):
        _package(tmp_path / "secret", source, spec=_spec(secret_names=("provider-token",)))
    with pytest.raises(PermissionError, match="side effects"):
        _package(tmp_path / "effect", source, spec=_spec(side_effects=("send message",)))
