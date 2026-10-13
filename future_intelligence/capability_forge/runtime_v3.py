from __future__ import annotations

from pathlib import Path

from integrations.discovery.generated_runtime_v3 import rehydrate_generated_capabilities_v3

from .canary_runner import CapabilityForgeCanaryRunner
from .governed_activation_v3 import GovernedCapabilityActivationServiceV3
from .oauth_durable import DurableCapabilityOAuthLifecycle
from .production_build import ProductionReadyCapabilityForgeBuildService
from .production_canary import ProductionCapabilityCanaryRollout
from .production_readiness import CapabilityForgeProductionReadiness
from .provenance import CapabilityPackageProvenance
from .provider_verification import CapabilityProviderVerifier


def install_capability_forge_v3(program, runtime: dict, *, data_root: str | Path) -> bool:
    """Extend the already-installed Forge V2 runtime without parallel authority."""
    catalog = getattr(program, "capability_catalog", None)
    lifecycle = getattr(program, "capability_forge_lifecycle", None)
    actions = getattr(program, "capability_forge_actions", None)
    previous_activation = getattr(program, "capability_forge_activation", None)
    tools = runtime.get("tools")
    vault = runtime.get("vault")
    approvals = getattr(previous_activation, "approvals", None)
    if catalog is None or lifecycle is None or tools is None or approvals is None or vault is None:
        return False
    root = Path(data_root)
    provenance = CapabilityPackageProvenance(vault)
    rollout = ProductionCapabilityCanaryRollout(
        path=root / "capability-forge.sqlite3",
        lifecycle=lifecycle,
        approvals=approvals,
        catalog=catalog,
        tools=tools,
        events=runtime.get("events"),
    )
    activation = GovernedCapabilityActivationServiceV3(
        catalog=catalog,
        approvals=approvals,
        tools=tools,
        data_root=root,
        lifecycle=lifecycle,
        events=runtime.get("events"),
        action_service=actions,
        provenance=provenance,
        rollout=rollout,
    )
    oauth_lifecycle = None
    if runtime.get("oauth") is not None and runtime.get("oauth_providers") is not None:
        oauth_lifecycle = DurableCapabilityOAuthLifecycle(
            oauth=runtime["oauth"],
            catalog=catalog,
            providers=dict(runtime.get("oauth_providers") or {}),
            events=runtime.get("events"),
            path=root / "capability-forge.sqlite3",
        )
    provider_verifier = CapabilityProviderVerifier(
        tools=tools,
        rollout=rollout,
        events=runtime.get("events"),
    )
    canary_runner = CapabilityForgeCanaryRunner(
        data_root=root,
        tools=tools,
        provenance=provenance,
        rollout=rollout,
        events=runtime.get("events"),
    )
    readiness = CapabilityForgeProductionReadiness()

    def build_factory():
        executor = runtime.get("engineering_executor")
        engineering = runtime.get("engineering")
        work_runtime = getattr(program.autonomy, "_work_bridge", None)
        work_store = getattr(work_runtime, "work", None)
        if executor is None or engineering is None or work_store is None:
            return None
        return ProductionReadyCapabilityForgeBuildService(
            work_store=work_store,
            engineering_runtime=engineering,
            engineering_executor=executor,
            package_builder=program.capability_forge_packages,
            output_root=Path(runtime.get("settings_data_dir") or engineering.evidence_root.parent) / "generated-capabilities",
            lifecycle=lifecycle,
            events=runtime.get("events"),
            provenance=provenance,
            rollout=rollout,
        )

    def invocation_observer(capability, _context):
        capability_id = str(capability.get("id") or "")
        version = str(capability.get("version") or "")
        def observe(*, ok, duration_ms, error_code=None):
            lifecycle.record_invocation(
                capability_id=capability_id,
                version=version,
                ok=bool(ok),
                duration_ms=float(duration_ms),
                error_code=error_code,
            )
        return observe

    rehydrated = tuple(rehydrate_generated_capabilities_v3(
        catalog,
        tools=tools,
        data_root=root,
        action_service=actions,
        provenance=provenance,
        invocation_observer=invocation_observer,
        events=runtime.get("events"),
    ))
    program.capability_forge_activation = activation
    program.rehydrated_generated_capabilities = rehydrated
    program.capability_forge_provenance = provenance
    program.capability_forge_rollout = rollout
    program.capability_forge_oauth = oauth_lifecycle
    program.capability_forge_provider_verifier = provider_verifier
    program.capability_forge_canary_runner = canary_runner
    program.capability_forge_production_readiness = readiness
    runtime.update({
        "capability_forge_activation": activation,
        "capability_forge_provenance": provenance,
        "capability_forge_rollout": rollout,
        "capability_forge_oauth": oauth_lifecycle,
        "capability_forge_provider_verifier": provider_verifier,
        "capability_forge_canary_runner": canary_runner,
        "capability_forge_production_readiness": readiness,
        "capability_forge_build_factory": build_factory,
        "generated_capabilities_rehydrated": rehydrated,
    })
    if runtime.get("events") is not None:
        runtime["events"].emit(
            "capability_forge.v3_runtime_ready",
            provenance=True,
            canary=True,
            provider_verification=True,
            capability_oauth=oauth_lifecycle is not None,
            production_activation_authority=False,
            rehydrated=list(rehydrated),
        )
    return True
