from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from future_intelligence.capability_forge.action_runtime import GeneratedActionService
from security.request_context import current_trusted_request
from tools.registry import Risk, Tool, VerificationResult

from .generated_runtime import (
    GeneratedCapabilitySecurityError,
    _GENERATED_VERIFICATION_METHODS,
    _entrypoint,
    _invoke_isolated,
    attach_approved_generated_capability as attach_v1,
    detach_generated_capability as detach_v1,
    load_generated_manifest,
    resolve_generated_package,
    validate_generated_manifest_authority as validate_v1,
)


ACTION_VERIFICATION_METHOD = "qualified_generated_action_planner"


def validate_generated_manifest_authority_v2(manifest: dict[str, Any]) -> None:
    runtime = str(manifest.get("runtime") or "")
    if runtime != "governed_action_v2":
        validate_v1(manifest)
        return
    if str(manifest.get("risk") or "") not in {"write", "destructive"}:
        raise GeneratedCapabilitySecurityError("governed generated action requires write or destructive risk classification")
    permissions = dict(manifest.get("permissions") or {})
    allowed_tools = permissions.get("allowed_tools") or []
    if not isinstance(allowed_tools, list) or not allowed_tools or len(allowed_tools) > 32:
        raise GeneratedCapabilitySecurityError("governed generated action requires an explicit bounded tool allowlist")
    if permissions.get("secret_names"):
        raise GeneratedCapabilitySecurityError("generated action cannot receive raw secret authority")
    forge = dict(manifest.get("forge") or {})
    if not forge.get("qualified") or forge.get("review_decision") != "approved":
        raise GeneratedCapabilitySecurityError("generated action is not independently qualified and approved")
    policy = dict(manifest.get("action_policy") or {})
    if not policy.get("owner_approval_required") or policy.get("automatic_commit") is not False:
        raise GeneratedCapabilitySecurityError("generated action must require owner approval and disable automatic commit")
    if policy.get("critical_actions_enabled"):
        raise GeneratedCapabilitySecurityError("critical generated actions remain disabled")


class GovernedActionGeneratedCapability:
    """Isolated generated planner that can stage, but never commit, world changes."""

    def __init__(
        self,
        package_path: str | Path,
        *,
        expected_digest: str,
        action_service: GeneratedActionService,
        timeout_seconds: int = 10,
        on_invocation: Callable[..., None] | None = None,
    ) -> None:
        self.package_path = Path(package_path).resolve()
        self.manifest_digest = str(expected_digest)
        self.manifest = load_generated_manifest(self.package_path, expected_digest=self.manifest_digest)
        validate_generated_manifest_authority_v2(self.manifest)
        if self.manifest.get("runtime") != "governed_action_v2":
            raise GeneratedCapabilitySecurityError("manifest is not a governed generated action")
        self.source_path, self.function, _ = _entrypoint(
            self.package_path, dict(self.manifest.get("entrypoint") or {}), label="entrypoint"
        )
        self.action_service = action_service
        self.timeout_seconds = max(1, min(int(timeout_seconds), 30))
        self.on_invocation = on_invocation

    def invoke(self, parameters: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(parameters, dict):
            raise ValueError("generated action parameters must be an object")
        started = time.perf_counter()
        ok = False
        error_code = None
        try:
            plan = _invoke_isolated(
                self.source_path,
                self.function,
                parameters,
                package_path=self.package_path,
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list):
                raise ValueError("governed generated action must return an object with a calls array")
            context = current_trusted_request()
            staged = self.action_service.stage(
                manifest=self.manifest,
                manifest_digest=self.manifest_digest,
                parameters=parameters,
                calls=plan["calls"],
                owner_id="owner",
                device_id=getattr(context, "device_id", None) if context is not None else None,
                session_id=getattr(context, "session_id", None) if context is not None else None,
                data_classification="internal",
            )
            ok = True
            return {
                "proposal_id": staged["id"],
                "state": staged["state"],
                "capability_id": staged["capability_id"],
                "approval_ids": [item["approval_id"] for item in (staged.get("approvals") or [])],
                "calls": len(staged.get("calls") or []),
                "committed": False,
                "owner_approval_required": True,
            }
        except PermissionError:
            error_code = "generated_policy_denied"
            raise
        except Exception:
            error_code = "generated_runtime_failed"
            raise
        finally:
            if self.on_invocation is not None:
                duration_ms = (time.perf_counter() - started) * 1000.0
                try:
                    self.on_invocation(ok=ok, duration_ms=duration_ms, error_code=error_code)
                except Exception:
                    pass


def attach_generated_capability(
    capability: dict[str, Any],
    *,
    tools,
    data_root: str | Path,
    action_service: GeneratedActionService | None = None,
    on_invocation: Callable[..., None] | None = None,
):
    if capability.get("type") != "generated_capability" or capability.get("state") != "active":
        raise ValueError("generated capability is not active")
    package_path = resolve_generated_package(data_root, str(capability.get("package_ref") or ""))
    manifest = load_generated_manifest(package_path, expected_digest=str(capability.get("manifest_digest") or ""))
    runtime_name = str(manifest.get("runtime") or "")
    if runtime_name != "governed_action_v2":
        return attach_v1(capability, tools=tools, data_root=data_root, on_invocation=on_invocation)
    if action_service is None:
        raise RuntimeError("generated action service is unavailable")
    validate_generated_manifest_authority_v2(manifest)
    runtime = GovernedActionGeneratedCapability(
        package_path,
        expected_digest=str(capability.get("manifest_digest") or ""),
        action_service=action_service,
        on_invocation=on_invocation,
    )
    if str(manifest.get("id")) != str(capability.get("id")) or str(manifest.get("version")) != str(capability.get("version")):
        raise GeneratedCapabilitySecurityError("catalog identity does not match generated action package")
    tool = Tool(
        name=str(capability["id"]),
        description=f"Generated governed action planner: {capability.get('name') or capability['id']}",
        handler=runtime.invoke,
        # Staging creates no external world effect. Exact delegated effects require
        # separate canonical ApprovalManager decisions and commit.
        risk=Risk.READ_ONLY,
        verifier=lambda _parameters, result: VerificationResult(
            bool(isinstance(result, dict) and result.get("proposal_id") and result.get("committed") is False),
            "generated action produced a staged owner-review proposal without dispatching side effects",
            {"manifest_digest": str(capability.get("manifest_digest") or ""), "runtime": runtime_name},
        ),
        verification_required=True,
        capability=str(capability["id"]),
        input_schema=dict(capability.get("input_schema") or {}),
        output_schema=None,
        prohibited_data_classifications=("sensitive", "secret", "restricted"),
        verification_method=ACTION_VERIFICATION_METHOD,
    )
    existing = getattr(tools, "_tools", {}).get(tool.name)
    generated_methods = set(_GENERATED_VERIFICATION_METHODS) | {ACTION_VERIFICATION_METHOD}
    if existing is None:
        tools.register(tool)
    elif getattr(existing, "verification_method", None) in generated_methods and getattr(existing, "capability", None) == tool.capability:
        tools._tools[tool.name] = tool
    else:
        raise ValueError(f"tool name collision for generated capability {tool.name}")
    return tool


def detach_generated_capability_v2(tools, capability_id: str) -> bool:
    name = str(capability_id)
    existing = getattr(tools, "_tools", {}).get(name)
    if existing is None:
        return False
    if getattr(existing, "verification_method", None) == ACTION_VERIFICATION_METHOD and getattr(existing, "capability", None) == name:
        del tools._tools[name]
        return True
    return detach_v1(tools, name)


def rehydrate_generated_capabilities_v2(
    catalog,
    *,
    tools,
    data_root: str | Path,
    action_service: GeneratedActionService,
    invocation_observer=None,
) -> list[str]:
    attached: list[str] = []
    for capability in catalog.all():
        if capability.get("type") != "generated_capability" or capability.get("state") != "active":
            continue
        observer = invocation_observer(capability, {}) if invocation_observer is not None else None
        try:
            attach_generated_capability(
                capability,
                tools=tools,
                data_root=data_root,
                action_service=action_service,
                on_invocation=observer,
            )
            attached.append(str(capability["id"]))
        except (ValueError, KeyError, TypeError, OSError, GeneratedCapabilitySecurityError, RuntimeError):
            continue
    return attached
