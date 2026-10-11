from __future__ import annotations

import os

from automation.work_bridge import AutomationWorkBridge
from evolution import AutomaticCodeEvolution, ContinuousEvolutionRuntime, ModelFileImplementationProvider
from evolution.automation_runtime import AutomaticCodeEvolutionRuntime
from future_intelligence.agent_workforce import AgentWorkforceService, AgentWorkforceStore
from future_intelligence.agent_workforce.evolution import AgentEvolutionRuntime
from future_intelligence.agent_workforce.learning_bridge import AgentLearningEventBridge
from identity import IdentityRuntime
from integrations.extension_contracts import ExtensionGrantStore
from integrations.provider_contracts import runtime_provider_inventory
from models.intelligence import IntelligenceEngine
from models.intelligence_settings import IntelligenceSettingsService
from models.performance import ModelPerformanceTracker
from models.performance_routing import attach_performance_routing
from models.portable_runtime import PortableIntelligenceRuntime
from training import (
    AutoTrainingCoordinator,
    AutoTrainingRuntime,
    ContributionSettingsService,
    LocalCheckpointEvaluator,
    LocalPeftTrainerBackend,
    ModelDeploymentController,
    ShadowQualificationRuntime,
    TrainingCandidateStore,
    TrainingCollector,
    TrainingDatasetExporter,
    TrainingDatasetSnapshotBuilder,
    TrainingRegistry,
    TrainingSettingsService,
)
from training.specialists import SpecialistAdapterRegistry


def attach_e9_runtime(runtime: dict) -> dict:
    """Attach E9 convergence and governed self-improvement services."""

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
    attach_performance_routing(
        base_router,
        model_performance,
        enabled=lambda: intelligence_settings.snapshot().performance_learning,
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

    # Governed auto-training: approved datasets only, immutable source-grouped
    # snapshots, real optional PEFT training, current-baseline evaluation,
    # persistent lineage and a distinct live-shadow and release boundary.
    training_settings = TrainingSettingsService(
        runtime["settings"].data_dir / "training-settings.json",
        events=events,
    )
    contribution_settings = ContributionSettingsService(
        runtime["settings"].data_dir / "contribution-settings.json",
        events=events,
    )
    training_snapshots = TrainingDatasetSnapshotBuilder(
        training_store,
        runtime["settings"].data_dir / "training-datasets",
    )
    training_registry = TrainingRegistry(runtime["settings"].data_dir / "training-registry.sqlite3")
    specialist_registry = SpecialistAdapterRegistry(
        runtime["settings"].data_dir / "specialist-adapters.sqlite3",
        training_registry,
    )

    def active_training_baseline():
        governance = getattr(training_registry, 'governance', None)
        if governance is None:
            return None
        active = governance.active_model()
        if not active:
            return None
        return training_registry.get_model(active['model_id'])

    training_evaluator = LocalCheckpointEvaluator(baseline_provider=active_training_baseline)
    training_backends = {"local_peft": LocalPeftTrainerBackend()}
    remote_gpu_backend = runtime.get("remote_gpu_training_backend")
    if remote_gpu_backend is not None:
        training_backends[str(remote_gpu_backend.backend_id)] = remote_gpu_backend
    training_coordinator = AutoTrainingCoordinator(
        settings=training_settings,
        candidates=training_store,
        snapshots=training_snapshots,
        registry=training_registry,
        backends=training_backends,
        evaluator=training_evaluator,
        output_root=runtime["settings"].data_dir / "trained-models",
        events=events,
    )
    auto_training = AutoTrainingRuntime(training_coordinator, events=events)
    shadow_qualification = ShadowQualificationRuntime(
        training_registry,
        training_settings,
        backends={},
        events=events,
    )
    intelligence.shadow_hook = shadow_qualification.observe_request
    model_deployment = ModelDeploymentController(
        training_registry,
        backends={},
        events=events,
        settings=training_settings,
    )
    portable = PortableIntelligenceRuntime(
        runtime["settings"].data_dir,
        model_router=base_router,
        settings=runtime["settings"],
        training_registry=training_registry,
        specialist_registry=specialist_registry,
        events=events,
        vault_persistent=str(os.environ.get("VISHNU_INTELLIGENCE_VAULT_PERSISTENT") or "").lower().strip() in {"1", "true", "yes", "on"},
    )
    runtime.update({
        "training_settings": training_settings,
        "contribution_settings": contribution_settings,
        "training_snapshots": training_snapshots,
        "training_registry": training_registry,
        "specialist_registry": specialist_registry,
        "training_evaluator": training_evaluator,
        "training_coordinator": training_coordinator,
        "auto_training": auto_training,
        "shadow_qualification": shadow_qualification,
        "model_deployment": model_deployment,
        "portable_intelligence": portable,
        "intelligence_manifest_store": portable.manifests,
        "intelligence_vault": portable.vault,
        "offline_pack_manager": portable.offline_packs,
        "fresh_machine_activation": portable.activation,
    })

    # On an existing restored installation, the restored active manifest/package
    # remains authoritative. On a new installation, publish the current governed
    # runtime once so continuity/backups have an exact portable identity to bind.
    try:
        if portable.manifests.active() is None:
            core_version = str(runtime.get("running_git_revision") or trusted_release_revision or "unversioned")
            portable.publish_current_restore_package(core_version=core_version)
    except Exception as exc:
        events.emit("intelligence.portable_bootstrap_failed", error_type=type(exc).__name__)

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

    automatic_code_evolution = None
    automatic_code_runtime = None
    if code_body is not None and runtime.get("evolution_handoff") is not None:
        automatic_code_evolution = AutomaticCodeEvolution(
            code_body=code_body,
            implementation=ModelFileImplementationProvider(intelligence),
            events=events,
        )
        automatic_code_runtime = AutomaticCodeEvolutionRuntime(
            automatic_code_evolution,
            handoffs=runtime["evolution_handoff"],
            runtime_epoch=lambda: runtime.get("code_worker_epoch", 0),
            events=events,
        )
    runtime["automatic_code_evolution"] = automatic_code_evolution
    runtime["automatic_code_evolution_runtime"] = automatic_code_runtime

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
        performance_routing_learning=True,
        training_capture_default=settings_snapshot.training_capture,
        training_candidates_governed=True,
        shared_learning_mode=contribution_settings.snapshot().preferences.mode.value,
        auto_training_enabled=training_settings.snapshot().enabled,
        live_shadow_qualification=True,
        automatic_code_evolution=bool(automatic_code_runtime and automatic_code_runtime.enabled),
        portable_intelligence=True,
        training_publication_automatic=False,
        trained_model_activation_automatic=False,
        body_adoption_automatic=False,
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
    auto_training = runtime.get("auto_training")
    if auto_training is not None:
        auto_training.start()
    auto_code = runtime.get("automatic_code_evolution_runtime")
    if auto_code is not None:
        auto_code.start()


def stop_e9_services(runtime: dict) -> None:
    auto_code = runtime.get("automatic_code_evolution_runtime")
    if auto_code is not None:
        auto_code.stop()
    auto_training = runtime.get("auto_training")
    if auto_training is not None:
        auto_training.stop()
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
    specialist_registry = runtime.get("specialist_registry")
    if specialist_registry is not None:
        specialist_registry.close()
    model_performance = runtime.get("model_performance")
    if model_performance is not None:
        model_performance.close()
    training_registry = runtime.get("training_registry")
    if training_registry is not None:
        training_registry.close()
    training_store = runtime.get("training_candidate_store")
    if training_store is not None:
        training_store.close()
