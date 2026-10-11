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
    """Project Canonical Work into a bounded engineering contract.

    Overrides may tune verification/qualification detail but cannot broaden the
    repository/path authority granted by Canonical Work. Authority-sensitive
    source changes additionally require an explicit Work approval policy flag.
    This projection never prepares a workspace, approves, merges or deploys.
    """
    data = dict(overrides or {})
    resources = work_order.resource_scope
    allowed_repositories = tuple(str(item) for item in resources.allowed_repositories if str(item))
    if repository not in allowed_repositories:
        raise PermissionError("repository is outside canonical Work resource scope")

    canonical_paths = tuple(str(item) for item in resources.allowed_paths if str(item))
    requested_paths = tuple(str(item) for item in _tuple_value(data.pop("allowed_paths", canonical_paths)))
    if not canonical_paths:
        raise PermissionError("canonical Work has no engineering path authority")
    if any(item not in canonical_paths for item in requested_paths):
        raise PermissionError("engineering allowed_paths override cannot broaden canonical Work resource scope")
    if not requested_paths:
        raise PermissionError("engineering path scope cannot be empty")
    allowed_paths = requested_paths

    canonical_authority = bool(dict(work_order.approval_policy or {}).get("allow_authority_paths", False))
    allow_authority_paths = bool(data.pop("allow_authority_paths", canonical_authority))
    if allow_authority_paths and not canonical_authority:
        raise PermissionError("authority-sensitive engineering paths require explicit canonical Work approval policy")

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
    devices = tuple(item if isinstance(item, DeviceProfile) else DeviceProfile.from_dict(item) for item in devices_raw)
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
        "allow_authority_paths": allow_authority_paths,
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