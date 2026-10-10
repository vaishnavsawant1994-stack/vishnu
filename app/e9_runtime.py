from __future__ import annotations

import os

from automation.work_bridge import AutomationWorkBridge
from evolution import ContinuousEvolutionRuntime
from future_intelligence.agent_workforce import AgentWorkforceService, AgentWorkforceStore
from future_intelligence.agent_workforce.evolution import AgentEvolutionRuntime
from future_intelligence.agent_workforce.learning_bridge import AgentLearningEventBridge
from identity import IdentityRuntime
from integrations.extension_contracts import ExtensionGrantStore
from integrations.provider_contracts import runtime_provider_inventory
from models.intelligence import IntelligenceEngine
from training import TrainingCandidateStore, TrainingCollector


def attach_e9_runtime(runtime: dict) -> dict:
    """Attach E9 convergence services after E1–E8 and P10 are fully constructed."""

    events = runtime["events"]
    trusted_release_revision = str(os.environ.get("VISHNU_TRUSTED_RELEASE_REVISION") or "").strip() or None
    trusted_release_activate = str(os.environ.get("VISHNU_TRUSTED_RELEASE_ACTIVATE") or "").strip().lower() in {"1", "true", "yes", "activate"}
    identity = IdentityRuntime(
        store=runtime["identity_store"],
        running_git_revision=runtime.get("running_git_revision"),
        events=events,
        trusted_release_revision=trusted_release_revision,
        allow_trusted_release_activation=trusted_release_activate,
    )
    runtime["identity_runtime"] = identity
    agent_executor = runtime.get("agent_executor")
    if agent_executor is not None and hasattr(agent_executor, "attach_identity_context"):
        agent_executor.attach_identity_context(identity.context_dict)

    code_body = runtime.get("code_body")
    authority = runtime.get("continuation_authority")
    if code_body is not None and authority is not None and hasattr(code_body, "attach_continuation_authority"):
        def body_mutation_guard():
            authority.assert_active()
            identity.assert_body_compatible()
        code_body.attach_continuation_authority(body_mutation_guard)

    # Advanced intelligence is an advisory layer over the canonical governed
    # router. STANDARD remains the default and preserves existing behavior.
    preferences = runtime.get("preferences")
    selected_mode = str(preferences.get("intelligence_mode", "standard") if preferences is not None else "standard")
    training_store = TrainingCandidateStore(runtime["settings"].data_dir / "training-candidates.sqlite3")
    training_collector = TrainingCollector(training_store)
    intelligence = IntelligenceEngine(
        runtime["models"],
        default_mode=selected_mode,
        capture_hook=training_collector.capture,
    )
    runtime["training_candidate_store"] = training_store
    runtime["training_collector"] = training_collector
    runtime["intelligence"] = intelligence
    worker_intelligence = runtime.get("worker_intelligence")
    if worker_intelligence is not None and hasattr(worker_intelligence, "attach_intelligence"):
        worker_intelligence.attach_intelligence(intelligence)

    continuous = ContinuousEvolutionRuntime(
        events=events,
        ingestor=runtime["evidence_ingestor"],
        evolution=runtime["evolution"],
        preferences=runtime.get("preferences"),
    )
    runtime["continuous_evolution"] = continuous

    work_bridge = getattr(runtime.get("advanced_autonomy"), "_work_bridge", None)
    if work_bridge is not None:
        runtime["automation_work_bridge"] = AutomationWorkBridge(
            engine=runtime["automations"],
            work_store=work_bridge.work,
            events=events,
        )
        runtime["canonical_work_store"] = work_bridge.work
        runtime["canonical_evidence_store"] = work_bridge.evidence
    else:
        runtime["automation_work_bridge"] = None
        runtime["canonical_work_store"] = None

    # The workforce is a coordination/intelligence layer over canonical Work.
    # It cannot execute tools, approve effects, manufacture evidence or decide
    # canonical completion. Runtime instances are bound to exactly one Project.
    workforce_store = AgentWorkforceStore(runtime["settings"].data_dir / "agent-workforce.sqlite3")
    workforce = AgentWorkforceService(
        workforce_store,
        worker_registry=getattr(runtime.get("advanced_autonomy"), "_worker_registry", None),
        work_store=runtime.get("canonical_work_store"),
        worker_intelligence=runtime.get("worker_intelligence"),
        models=runtime.get("models"),
        events=events,
    )
    runtime["agent_workforce_store"] = workforce_store
    runtime["agent_workforce"] = workforce
    runtime["agent_learning_bridge"] = AgentLearningEventBridge(workforce, events)
    runtime["agent_evolution"] = AgentEvolutionRuntime(workforce, events=events)

    extension_grants = ExtensionGrantStore(runtime["settings"].data_dir / "extension-grants.sqlite3")
    runtime["extension_grants"] = extension_grants
    for plugin in runtime.get("plugins").list() if runtime.get("plugins") is not None else ():
        from integrations.extension_contracts import ExtensionManifest
        extension_grants.install(
            ExtensionManifest(
                id=plugin.id,
                version=plugin.version,
                publisher="legacy-manifest",
                capabilities=(),
                requested_permissions=tuple(plugin.permissions),
                endpoint=plugin.endpoint,
                metadata={"name": plugin.name, "description": plugin.description, "legacy_enabled": plugin.enabled},
            )
        )

    runtime["provider_inventory"] = runtime_provider_inventory(runtime)
    events.emit(
        "e9.runtime_ready",
        identity_state=identity.status().bootstrap_state,
        work_authority=getattr(getattr(runtime.get("advanced_autonomy"), "_canonical_work_authority", None), "mode", "unavailable"),
        continuous_evolution=continuous.enabled,
        agent_evolution=runtime["agent_evolution"].enabled,
        agent_learning=True,
        intelligence_mode=selected_mode,
        training_candidates_governed=True,
        providers=len(runtime["provider_inventory"]),
        agent_types=workforce.summary()["total_agents"],
    )
    return runtime


def start_e9_services(runtime: dict) -> None:
    continuous = runtime.get("continuous_evolution")
    if continuous is not None:
        continuous.start()
    agent_evolution = runtime.get("agent_evolution")
    if agent_evolution is not None:
        agent_evolution.start()


def stop_e9_services(runtime: dict) -> None:
    agent_evolution = runtime.get("agent_evolution")
    if agent_evolution is not None:
        agent_evolution.stop()
    learning = runtime.get("agent_learning_bridge")
    if learning is not None:
        learning.close()
    continuous = runtime.get("continuous_evolution")
    if continuous is not None:
        continuous.stop()
    bridge = runtime.get("automation_work_bridge")
    if bridge is not None:
        bridge.close()
    workforce_store = runtime.get("agent_workforce_store")
    if workforce_store is not None:
        workforce_store.connection.close()
    training_store = runtime.get("training_candidate_store")
    if training_store is not None:
        training_store.close()
