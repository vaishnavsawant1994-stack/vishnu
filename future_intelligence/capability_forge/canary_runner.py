from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from integrations.discovery.generated_runtime import (
    GovernedToolchainGeneratedCapability,
    PurePythonGeneratedCapability,
    _entrypoint,
    _invoke_isolated,
    load_generated_manifest,
    resolve_generated_package,
)
from integrations.discovery.generated_runtime_v2 import validate_generated_manifest_authority_v2


class CapabilityForgeCanaryRunner:
    """Run signed packages before activation without registering them as tools."""

    def __init__(self, *, data_root: str | Path, tools, provenance, rollout, events=None):
        self.data_root = Path(data_root)
        self.tools = tools
        self.provenance = provenance
        self.rollout = rollout
        self.events = events

    def invoke(self, *, package_ref: str, manifest_digest: str, parameters: dict[str, Any],
               stage: str = "internal") -> dict[str, Any]:
        if stage not in {"internal", "limited"}:
            raise ValueError("pre-activation canary stage must be internal or limited")
        package_path = resolve_generated_package(self.data_root, package_ref)
        evidence = self.provenance.verify(package_path, expected_manifest_digest=manifest_digest)
        manifest = load_generated_manifest(package_path, expected_digest=manifest_digest)
        validate_generated_manifest_authority_v2(manifest)
        capability_id = str(manifest["id"])
        version = str(manifest["version"])
        rollout = self.rollout.get(capability_id, version)
        if rollout.get("stage") != stage:
            raise PermissionError("canary invocation stage does not match current Forge rollout stage")
        started = time.perf_counter()
        ok = False
        error_code = None
        try:
            runtime_name = str(manifest.get("runtime") or "")
            if runtime_name == "pure_python_v1":
                result = PurePythonGeneratedCapability(
                    package_path,
                    expected_digest=manifest_digest,
                ).invoke(dict(parameters))
                summary = {"kind": "pure", "output_type": type(result).__name__}
            elif runtime_name == "governed_toolchain_v1":
                result = GovernedToolchainGeneratedCapability(
                    package_path,
                    expected_digest=manifest_digest,
                    tools=self.tools,
                    capability_id=capability_id,
                ).invoke(dict(parameters))
                summary = {"kind": "toolchain", "output_type": type(result).__name__}
            elif runtime_name == "governed_action_v2":
                source_path, function, _ = _entrypoint(
                    package_path,
                    dict(manifest.get("entrypoint") or {}),
                    label="entrypoint",
                )
                plan = _invoke_isolated(
                    source_path,
                    function,
                    dict(parameters),
                    package_path=package_path,
                    timeout_seconds=10,
                )
                if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list):
                    raise ValueError("governed generated action canary must return a calls array")
                if len(plan["calls"]) > 16:
                    raise PermissionError("governed generated action canary exceeds bounded call count")
                # Pre-activation action canary validates the isolated planner only.
                # It deliberately does not create approvals or dispatch effects.
                summary = {"kind": "action_plan", "planned_calls": len(plan["calls"]), "committed": False}
            else:
                raise PermissionError("unsupported generated capability canary runtime")
            ok = True
            return {
                "verified": True,
                "capability_id": capability_id,
                "version": version,
                "stage": stage,
                "provenance_key_id": evidence["key_id"],
                **summary,
            }
        except PermissionError:
            error_code = "canary_policy_denied"
            raise
        except Exception:
            error_code = "canary_runtime_failed"
            raise
        finally:
            duration_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
            self.rollout.record_sample(
                capability_id,
                version,
                ok=ok,
                duration_ms=duration_ms,
                source=stage,
            )
            if self.events is not None:
                self.events.emit(
                    "capability_forge.canary_invoked",
                    capability_id=capability_id,
                    version=version,
                    stage=stage,
                    ok=ok,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
