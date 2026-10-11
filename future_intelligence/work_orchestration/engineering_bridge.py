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


def _merge_required(canonical, requested) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in (*_tuple_value(canonical), *_tuple_value(requested)) if str(item)))


def _scope_rule_within(requested: str, canonical: str) -> bool:
    req = str(requested or "").strip().replace("\\", "/")
    can = str(canonical or "").strip().replace("\\", "/")
    if not req or not can:
        return False
    if req == can:
        return True
    if can in {".", "./", "*", "**", "**/*"}:
        return True
    # Proving subset relationships between arbitrary glob patterns is error-prone;
    # only exact glob matches are accepted. Plain directory/path scopes can narrow.
    if any(char in req for char in "*?[") or any(char in can for char in "*?["):
        return False
    req = req.lstrip("./").rstrip("/")
    can = can.lstrip("./").rstrip("/")
    return bool(req and can and (req == can or req.startswith(can + "/")))


def _device_profiles(value) -> tuple[DeviceProfile, ...]:
    return tuple(item if isinstance(item, DeviceProfile) else DeviceProfile.from_dict(item) for item in _tuple_value(value))


def engineering_spec_from_work_order(
    work_order: WorkOrder,
    *,
    attempt_id: str,
    repository: str,
    base_revision: str,
    overrides: Mapping[str, object] | None = None,
) -> EngineeringSpec:
    """Project Canonical Work into a bounded, monotonic engineering contract.

    Overrides may narrow repository/path authority or add requirements and
    qualification gates. They cannot remove Canonical Work success criteria,
    tests, review, browser coverage, UI gates, or security classification.
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
    if not requested_paths:
        raise PermissionError("engineering path scope cannot be empty")
    if any(not any(_scope_rule_within(item, canonical) for canonical in canonical_paths) for item in requested_paths):
        raise PermissionError("engineering allowed_paths override cannot broaden canonical Work resource scope")
    allowed_paths = requested_paths

    canonical_authority = bool(dict(work_order.approval_policy or {}).get("allow_authority_paths", False))
    allow_authority_paths = bool(data.pop("allow_authority_paths", canonical_authority))
    if allow_authority_paths and not canonical_authority:
        raise PermissionError("authority-sensitive engineering paths require explicit canonical Work approval policy")

    seed = f"{work_order.id}:{attempt_id}:{repository}:{base_revision}".encode("utf-8")
    spec_id = str(data.pop("id", f"eng-{hashlib.sha256(seed).hexdigest()[:24]}"))
    verification = dict(work_order.verification_strategy or {})

    canonical_surfaces = _tuple_value(verification.get("affected_surfaces", ()))
    requested_surfaces = _tuple_value(data.pop("affected_surfaces", ()))
    surfaces = _merge_required(canonical_surfaces, requested_surfaces)
    canonical_ui_required = bool("ui" in canonical_surfaces or verification.get("ui_required", False))
    requested_ui_required = bool(data.pop("ui_required", False))
    ui_required = bool(canonical_ui_required or requested_ui_required or "ui" in surfaces)

    canonical_browsers_raw = _tuple_value(verification.get("browsers", ("chromium",)))
    requested_browsers_raw = _tuple_value(data.pop("browsers", ()))
    canonical_browsers = tuple(item if isinstance(item, BrowserEngine) else BrowserEngine(str(item)) for item in canonical_browsers_raw)
    requested_browsers = tuple(item if isinstance(item, BrowserEngine) else BrowserEngine(str(item)) for item in requested_browsers_raw)
    browsers = tuple(dict.fromkeys((*canonical_browsers, *requested_browsers))) or (BrowserEngine.CHROMIUM,)

    canonical_security_raw = verification.get("security_class", SecurityClass.ORDINARY.value)
    canonical_security = canonical_security_raw if isinstance(canonical_security_raw, SecurityClass) else SecurityClass(str(canonical_security_raw))
    requested_security_raw = data.pop("security_class", canonical_security.value)
    requested_security = requested_security_raw if isinstance(requested_security_raw, SecurityClass) else SecurityClass(str(requested_security_raw))
    security_rank = {SecurityClass.ORDINARY: 0, SecurityClass.SENSITIVE: 1, SecurityClass.AUTHORITY: 2}
    if security_rank[requested_security] < security_rank[canonical_security]:
        raise PermissionError("engineering security_class override cannot weaken canonical Work verification")
    security_class = requested_security

    budget_data = data.pop("budget", {})
    if isinstance(budget_data, EngineeringBudget):
        budget = budget_data
    else:
        merged_budget = dict(budget_data or {})
        if work_order.retry_policy.get("max_attempts") is not None and "max_repair_cycles" not in merged_budget:
            merged_budget["max_repair_cycles"] = min(3, max(0, int(work_order.retry_policy["max_attempts"]) - 1))
        budget = EngineeringBudget.from_dict(merged_budget)

    canonical_devices = _device_profiles(verification.get("devices", ()))
    requested_devices = _device_profiles(data.pop("devices", ()))
    devices = tuple(dict.fromkeys((*canonical_devices, *requested_devices)))

    canonical_prohibited = _tuple_value(dict(resources.metadata or {}).get("prohibited_paths", ()))
    requested_prohibited = _tuple_value(data.pop("prohibited_paths", ()))
    prohibited_paths = _merge_required(canonical_prohibited, requested_prohibited)

    canonical_requirements = (work_order.objective,)
    requirements = _merge_required(canonical_requirements, data.pop("requirements", ()))
    success_criteria = _merge_required(work_order.success_criteria, data.pop("success_criteria", ()))
    required_tests = _merge_required(verification.get("tests", ()), data.pop("required_tests", ()))
    required_states = _merge_required(verification.get("states", ()), data.pop("required_states", ()))
    reference_designs = _merge_required(verification.get("reference_designs", ()), data.pop("reference_designs", ()))
    api_impacts = _merge_required(verification.get("api_impacts", ()), data.pop("api_impacts", ()))
    schema_impacts = _merge_required(verification.get("schema_impacts", ()), data.pop("schema_impacts", ()))

    canonical_accessibility = bool(verification.get("accessibility_required", canonical_ui_required))
    requested_accessibility = bool(data.pop("accessibility_required", False))
    accessibility_required = bool(ui_required or canonical_accessibility or requested_accessibility)

    canonical_visual = bool(verification.get("visual_review_required", canonical_ui_required))
    requested_visual = bool(data.pop("visual_review_required", False))
    visual_review_required = bool(ui_required or canonical_visual or requested_visual)

    canonical_review = bool(work_order.evidence_contract.require_review)
    requested_review = bool(data.pop("review_required", canonical_review))
    review_required = bool(canonical_review or requested_review)

    known = {
        "requirements": requirements,
        "non_requirements": tuple(str(item) for item in _tuple_value(data.pop("non_requirements", ())) if str(item)),
        "prohibited_paths": prohibited_paths,
        "affected_surfaces": surfaces,
        "api_impacts": api_impacts,
        "schema_impacts": schema_impacts,
        "success_criteria": success_criteria,
        "required_tests": required_tests,
        "required_states": required_states,
        "reference_designs": reference_designs,
        "devices": devices,
        "accessibility_required": accessibility_required,
        "visual_review_required": visual_review_required,
        "review_required": review_required,
        "allow_authority_paths": allow_authority_paths,
    }
    if data:
        raise ValueError(f"unsupported engineering override keys: {sorted(data)}")

    failure_fingerprint = str(verification.get("failure_fingerprint") or "").strip()
    regression_required = bool(verification.get("regression_test_required", False) or failure_fingerprint)
    metadata = {
        "plan_id": work_order.plan_id,
        "project_id": work_order.project_id,
        "worker_type": work_order.worker_type,
        "regression_test_required": regression_required,
    }
    if failure_fingerprint:
        metadata["failure_fingerprint"] = failure_fingerprint

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
        ui_required=ui_required,
        budget=budget,
        metadata=metadata,
        **known,
    )
