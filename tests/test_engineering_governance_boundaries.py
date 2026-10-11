from __future__ import annotations

import pytest

from core.permissions import PermissionEngine
from future_intelligence.work_orchestration import EvidenceContract, ResourceScope, WorkOrder
from future_intelligence.work_orchestration.engineering_bridge import engineering_spec_from_work_order
from tools import engineering_work
from tools.registry import Risk


def make_order(
    *,
    paths=("src/",),
    approval_policy=None,
    verification_strategy=None,
    success_criteria=("authorized source is changed",),
    require_review=True,
):
    return WorkOrder(
        id="work-gov",
        plan_id="plan-gov",
        title="Governed code change",
        objective="Change only the authorized source",
        worker_type="coding",
        resource_scope=ResourceScope(
            allowed_repositories=("owner/repo",),
            allowed_paths=tuple(paths),
        ),
        success_criteria=tuple(success_criteria),
        evidence_contract=EvidenceContract(require_review=bool(require_review)),
        verification_strategy=dict(verification_strategy or {}),
        approval_policy=dict(approval_policy or {}),
    )


def test_engineering_projection_rejects_repository_and_path_scope_broadening():
    order = make_order()
    with pytest.raises(PermissionError):
        engineering_spec_from_work_order(
            order,
            attempt_id="attempt-1",
            repository="other/repo",
            base_revision="a" * 40,
        )
    with pytest.raises(PermissionError):
        engineering_spec_from_work_order(
            order,
            attempt_id="attempt-1",
            repository="owner/repo",
            base_revision="a" * 40,
            overrides={"allowed_paths": ("src/", "security/")},
        )
    narrowed = engineering_spec_from_work_order(
        WorkOrder.from_dict({
            **order.to_dict(),
            "resource_scope": ResourceScope(
                allowed_repositories=("owner/repo",),
                allowed_paths=("src/", "tests/"),
            ).to_dict(),
        }),
        attempt_id="attempt-1",
        repository="owner/repo",
        base_revision="a" * 40,
        overrides={"allowed_paths": ("src/",)},
    )
    assert narrowed.allowed_paths == ("src/",)


def test_engineering_projection_allows_true_subpath_narrowing():
    order = make_order(paths=("src/",))
    narrowed = engineering_spec_from_work_order(
        order,
        attempt_id="attempt-1",
        repository="owner/repo",
        base_revision="a" * 40,
        overrides={"allowed_paths": ("src/components/",)},
    )
    assert narrowed.allowed_paths == ("src/components/",)
    with pytest.raises(PermissionError, match="cannot broaden"):
        engineering_spec_from_work_order(
            order,
            attempt_id="attempt-1",
            repository="owner/repo",
            base_revision="a" * 40,
            overrides={"allowed_paths": ("tests/",)},
        )


def test_authority_sensitive_scope_requires_canonical_work_policy():
    with pytest.raises(PermissionError):
        engineering_spec_from_work_order(
            make_order(paths=("security/",)),
            attempt_id="attempt-1",
            repository="owner/repo",
            base_revision="a" * 40,
            overrides={"allow_authority_paths": True},
        )
    approved = engineering_spec_from_work_order(
        make_order(paths=("security/",), approval_policy={"allow_authority_paths": True}),
        attempt_id="attempt-1",
        repository="owner/repo",
        base_revision="a" * 40,
    )
    assert approved.allow_authority_paths is True


def test_engineering_projection_cannot_weaken_canonical_verification_contract():
    order = make_order(
        verification_strategy={
            "tests": ["canonical-test"],
            "affected_surfaces": ["ui"],
            "browsers": ["chromium", "webkit"],
            "security_class": "sensitive",
        },
        success_criteria=("canonical criterion",),
        require_review=True,
    )
    spec = engineering_spec_from_work_order(
        order,
        attempt_id="attempt-1",
        repository="owner/repo",
        base_revision="a" * 40,
        overrides={
            "requirements": ("extra requirement",),
            "success_criteria": ("extra criterion",),
            "required_tests": ("extra-test",),
            "browsers": ("firefox",),
            "review_required": False,
            "ui_required": False,
            "accessibility_required": False,
            "visual_review_required": False,
        },
    )
    assert order.objective in spec.requirements
    assert "extra requirement" in spec.requirements
    assert spec.success_criteria == ("canonical criterion", "extra criterion")
    assert spec.required_tests == ("canonical-test", "extra-test")
    assert {item.value for item in spec.browsers} == {"chromium", "webkit", "firefox"}
    assert spec.review_required is True
    assert spec.ui_required is True
    assert spec.accessibility_required is True
    assert spec.visual_review_required is True
    assert spec.security_class.value == "sensitive"

    with pytest.raises(PermissionError, match="cannot weaken"):
        engineering_spec_from_work_order(
            order,
            attempt_id="attempt-1",
            repository="owner/repo",
            base_revision="a" * 40,
            overrides={"security_class": "ordinary"},
        )


def test_engineering_execute_work_is_critical_and_owner_confirmation_gated():
    class Registry:
        def __init__(self): self.tool = None
        def register(self, tool): self.tool = tool

    class Result:
        def to_dict(self):
            return {
                "candidate_revision": "b" * 40,
                "status": "verifying",
                "push_authority": False,
                "merge_authority": False,
                "deploy_authority": False,
                "activation_authority": False,
            }

    class Executor:
        def __init__(self): self.calls = []
        def execute(self, work_order_id, **kwargs):
            self.calls.append((work_order_id, kwargs))
            return Result()

    registry = Registry()
    executor = Executor()
    engineering_work.register(registry, executor, runtime_epoch_provider=lambda: 42)
    tool = registry.tool
    assert tool is not None
    assert tool.risk is Risk.CRITICAL
    assert tool.requires_reauth is True
    result = tool.handler({"work_order_id": "work-gov"})
    assert executor.calls[0][1]["runtime_epoch"] == 42
    assert tool.verifier({}, result).verified is True

    permissions = PermissionEngine("act")
    rules = dict(PermissionEngine.DEFAULT_RULES)
    rules["execute_actions"] = "allow"
    permissions.set_rules(rules)
    decision = permissions.decide(int(Risk.CRITICAL), operation="execute_actions")
    assert decision.allowed is False
    assert decision.requires_confirmation is True
