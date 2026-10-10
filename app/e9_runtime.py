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
from models.intelligence_settings import IntelligenceSettingsService
from models.performance import ModelPerformanceTracker
from training import TrainingCandidateStore, TrainingCollector, TrainingDatasetExporter


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

    # Advanced intelligence is one advisory facade over the already-governed
    # model router. Keeping the original router separately is important: it
    # remains the single authority for providers, credentials, privacy, quotas,
    # budgets, resilience and embeddings. STANDARD still follows that router's
    # historical chat/json path exactly.
    preferences = runtime.get("preferences")
    intelligence_settings = IntelligenceSettingsService(preferences, events=events)
    settings_snapshot = intelligence_settings.snapshot()
    base_router = runtime.get("model_router") or runtime["models"]
    training_store = TrainingCandidateStore(runtime["settings"].data_dir / "training-candidates.sqlite3")
    training_collector = TrainingCollector(training_store)
    training_exporter = TrainingDatasetExporter(
        training_store,
        runtime["settings"].data_dir / "training-exports",
    )
    model_performance = ModelPerformanceTracker(
        path=runtime["settings"].data_dir / "model-performance.sqlite3"
    )
    intelligence = IntelligenceEngine(
        base_router,
        default_mode=settings_snapshot.mode,
        performance=model_performance,
        capture_hook=training_collector.capture,
        settings_service=intelligence_settings,
    )
    runtime["model_router"] = base_router
    runtime["models"] = intelligence
    runtime["intelligence"] = intelligence
    runtime["intelligence_settings"] = intelligence_settings
    runtime["model_performance"] = model_performance
    runtime["training_candidate_store"] = training_store
    runtime["training_collector"] = training_collector
    runtime["training_dataset_exporter"] = training_exporter

    # Existing runtime objects were constructed before E9 attachment. Point
    # their model-intelligence references at the facade without changing any
    # execution, approval, tool, memory or security owner.
    if agent_executor is not None:
        agent_executor.models = intelligence
        planner = getattr(agent_executor, "planner", None)
        if planner is not None:
            planner.models = intelligence
    voice = runtime.get("voice")
    if voice is not None:
        voice.models = intelligence
        backend = getattr(voice, "backend", None)
        if backend is not None and hasattr(backend, "models"):
            backend.models = intelligence
    model_evaluation = runtime.get("model_evaluation")
    if model_evaluation is not None and hasattr(model_evaluation, "models"):
        model_evaluation.models = intelligence
    worker_intelligence = runtime.get("worker_intelligence")
    if worker_intelligence is not None and hasattr(worker_intelligence, "attach_intelligence"):
        worker_intelligence.attach_intelligence(intelligence)
    hybrid_intelligence = runtime.get("hybrid_intelligence")
    if hybrid_intelligence is not None and hasattr(hybrid_intelligence, "canonical_router"):
        hybrid_intelligence.canonical_router = intelligence
    advanced_autonomy = runtime.get("advanced_autonomy")
    if advanced_autonomy is not None and hasattr(advanced_autonomy, "models"):
        advanced_autonomy.models = intelligence

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
        models=intelligence,
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
        advanced_intelligence_enabled=settings_snapshot.enabled,
        intelligence_mode=settings_snapshot.mode.value,
        intelligence_auto_escalation=settings_snapshot.auto_escalation,
        training_candidates_governed=True,
        training_publication_automatic=False,
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
    model_performance = runtime.get("model_performance")
    if model_performance is not None:
        model_performance.close()
    training_store = runtime.get("training_candidate_store")
    if training_store is not None:
        training_store.close()
