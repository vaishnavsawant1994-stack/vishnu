from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Mapping

from future_intelligence.engineering.contracts import (
    BrowserEngine,
    DeviceProfile,
    EngineeringBudget,
    EngineeringSpec,
    SecurityClass,
)

from .models import WorkOrder


def _tuple_value(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return value
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def engineering_spec_from_work_order(
    work_order: WorkOrder,
    *,
    attempt_id: str,
    repository: str,
    base_revision: str,
    overrides: Mapping[str, object] | None = None,
) -> EngineeringSpec:
    """Project canonical Work into a bounded engineering contract.

    This is a projection only: it does not create a second Work authority, mutate
    Work state, prepare a workspace, approve, review, merge, deploy, or activate.
    """
    data = dict(overrides or {})
    resources = work_order.resource_scope
    allowed_repositories = tuple(resources.allowed_repositories)
    if allowed_repositories and repository not in allowed_repositories:
        raise PermissionError("repository is outside canonical Work resource scope")
    allowed_paths = tuple(str(item) for item in _tuple_value(data.pop("allowed_paths", resources.allowed_paths)))
    seed = f"{work_order.id}:{attempt_id}:{repository}:{base_revision}".encode("utf-8")
    spec_id = str(data.pop("id", f"eng-{hashlib.sha256(seed).hexdigest()[:24]}"))
    verification = dict(work_order.verification_strategy)
    surfaces = tuple(str(item) for item in _tuple_value(data.pop("affected_surfaces", verification.get("affected_surfaces", ()))))
    ui_required = bool(data.pop("ui_required", "ui" in surfaces or verification.get("ui_required", False)))
    browsers_raw = _tuple_value(data.pop("browsers", verification.get("browsers", ("chromium",))))
    browsers = tuple(item if isinstance(item, BrowserEngine) else BrowserEngine(str(item)) for item in browsers_raw)
    if not browsers:
        browsers = (BrowserEngine.CHROMIUM,)
    security_raw = data.pop("security_class", verification.get("security_class", SecurityClass.ORDINARY.value))
    security_class = security_raw if isinstance(security_raw, SecurityClass) else SecurityClass(str(security_raw))
    budget_data = data.pop("budget", {})
    if isinstance(budget_data, EngineeringBudget):
        budget = budget_data
    else:
        merged_budget = dict(budget_data or {})
        if work_order.retry_policy.get("max_attempts") is not None and "max_repair_cycles" not in merged_budget:
            merged_budget["max_repair_cycles"] = min(3, max(0, int(work_order.retry_policy["max_attempts"]) - 1))
        budget = EngineeringBudget.from_dict(merged_budget)
    devices_raw = _tuple_value(data.pop("devices", ()))
    devices = tuple(
        item if isinstance(item, DeviceProfile) else DeviceProfile.from_dict(item)
        for item in devices_raw
    )
    known = {
        "requirements": tuple(str(item) for item in _tuple_value(data.pop("requirements", (work_order.objective,)))),
        "non_requirements": tuple(str(item) for item in _tuple_value(data.pop("non_requirements", ()))),
        "prohibited_paths": tuple(str(item) for item in _tuple_value(data.pop("prohibited_paths", ()))),
        "affected_surfaces": surfaces,
        "api_impacts": tuple(str(item) for item in _tuple_value(data.pop("api_impacts", ()))),
        "schema_impacts": tuple(str(item) for item in _tuple_value(data.pop("schema_impacts", ()))),
        "success_criteria": tuple(str(item) for item in _tuple_value(data.pop("success_criteria", work_order.success_criteria))),
        "required_tests": tuple(str(item) for item in _tuple_value(data.pop("required_tests", verification.get("tests", ())))),
        "required_states": tuple(str(item) for item in _tuple_value(data.pop("required_states", verification.get("states", ())))),
        "reference_designs": tuple(str(item) for item in _tuple_value(data.pop("reference_designs", verification.get("reference_designs", ())))),
        "devices": devices,
        "accessibility_required": bool(data.pop("accessibility_required", verification.get("accessibility_required", ui_required))),
        "visual_review_required": bool(data.pop("visual_review_required", verification.get("visual_review_required", ui_required))),
        "review_required": bool(data.pop("review_required", work_order.evidence_contract.require_review)),
        "allow_authority_paths": bool(data.pop("allow_authority_paths", False)),
    }
    if data:
        raise ValueError(f"unsupported engineering override keys: {sorted(data)}")
    return EngineeringSpec(
        id=spec_id,
        work_order_id=work_order.id,
        attempt_id=str(attempt_id),
        repository=str(repository),
        base_revision=str(base_revision),
        objective=work_order.objective,
        allowed_paths=allowed_paths,
        browsers=browsers,
        security_class=security_class,
        budget=budget,
        metadata={"plan_id": work_order.plan_id, "project_id": work_order.project_id, "worker_type": work_order.worker_type},
        **known,
    )