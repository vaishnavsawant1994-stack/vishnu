from __future__ import annotations

from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.automation_bridge import CapabilityForgeAutomationBridge
from future_intelligence.capability_forge.improvement import CapabilityImprovementService
from future_intelligence.capability_forge.ui_contract import GeneratedUIContractError, validate_generated_ui_contract


def test_declarative_generated_ui_contract_accepts_fields_and_rejects_executable_surface():
    ui = validate_generated_ui_contract({
        "schema_version": 1,
        "title": "Send supplier update",
        "description": "Review the exact parameters before staging the action.",
        "fields": [
            {"name":"supplier","label":"Supplier","type":"string","required":True},
            {"name":"priority","label":"Priority","type":"select","options":["normal","urgent"]},
            {"name":"notes","label":"Notes","type":"multiline"},
        ],
        "submit_label": "Stage action",
    })
    assert ui["title"] == "Send supplier update"
    assert ui["fields"][1]["options"] == ["normal", "urgent"]
    with pytest.raises(GeneratedUIContractError, match="unsupported generated UI keys"):
        validate_generated_ui_contract({"title":"Bad","fields":[],"script":"fetch('/secrets')"})
    with pytest.raises(GeneratedUIContractError, match="field keys"):
        validate_generated_ui_contract({"title":"Bad","fields":[{"name":"x","type":"string","onchange":"run()"}]})


class FakeCatalog:
    def __init__(self, item): self.item = item
    def get(self, capability_id): return dict(self.item) if capability_id == self.item.get("id") else None


class FakeAutomations:
    def __init__(self): self.created=[]; self.enabled=[]
    def create(self, title, prompt, next_run_at, interval_seconds=None, condition=None):
        self.created.append((title,prompt,next_run_at,interval_seconds,condition)); return "automation-1"
    def enable(self, automation_id, enabled=True): self.enabled.append((automation_id,enabled))


def test_background_generated_capability_uses_canonical_automation_and_never_auto_approves():
    catalog = FakeCatalog({
        "id":"generated.action.test","type":"generated_capability","state":"active","name":"Supplier monitor",
        "permissions":{"background_allowed":True},
    })
    engine=FakeAutomations(); bridge=CapabilityForgeAutomationBridge(engine,catalog)
    result=bridge.schedule("generated.action.test",{"supplier":"A"},next_run_at="2026-10-14T08:00:00+00:00",interval_seconds=3600)
    assert result["automation_id"] == "automation-1"
    assert result["side_effect_auto_approval"] is False
    assert "never approve or commit them automatically" in engine.created[0][1]
    with pytest.raises(ValueError, match="once per hour"):
        bridge.schedule("generated.action.test",{},next_run_at="2026-10-14T08:00:00+00:00",interval_seconds=60)


def test_background_schedule_requires_frozen_background_permission():
    catalog=FakeCatalog({"id":"generated.read","type":"generated_capability","state":"active","permissions":{"background_allowed":False}})
    with pytest.raises(PermissionError, match="not qualified"):
        CapabilityForgeAutomationBridge(FakeAutomations(),catalog).schedule("generated.read",{},next_run_at="2026-10-14T08:00:00+00:00")


class FakeHealth:
    state="rollback_recommended"; rollback_recommended=True; sufficient_evidence=True
    active_version="2.0.0"; reasons=("error rate regressed",)
    def to_dict(self): return {"state":self.state,"rollback_recommended":True,"sufficient_evidence":True,"reasons":list(self.reasons)}


class FakeEvaluator:
    def evaluate(self, _capability_id): return FakeHealth()


class FakeForge:
    def __init__(self): self.calls=[]
    def propose(self, source, payload, requirements=None):
        self.calls.append((source,payload,requirements))
        return (
            SimpleNamespace(id="gap-next",to_dict=lambda:{"id":"gap-next"}),
            SimpleNamespace(id="spec-next",to_dict=lambda:{"id":"spec-next"}),
            SimpleNamespace(id="plan-next",to_dict=lambda:{"id":"plan-next"}),
        )


def test_health_degradation_creates_proposal_only_with_lineage_and_no_activation():
    catalog=FakeCatalog({
        "id":"generated.action.test","type":"generated_capability","state":"active","name":"Action","version":"2.0.0",
        "runtime":"governed_action_v2","permissions":{"allowed_tools":["write.item"],"background_allowed":True,"ui_required":True},
        "ui":{"schema_version":1,"title":"Action","fields":[],"submit_label":"Stage"},
    })
    forge=FakeForge(); service=CapabilityImprovementService(forge,FakeEvaluator(),catalog)
    result=service.propose("generated.action.test")
    assert result["activation"] is False
    assert forge.calls[0][0] == "system"
    metadata=forge.calls[0][2]["metadata"]
    assert metadata["improvement_of"] == "generated.action.test"
    assert metadata["previous_version"] == "2.0.0"
    assert metadata["allowed_tools"] == ["write.item"]
