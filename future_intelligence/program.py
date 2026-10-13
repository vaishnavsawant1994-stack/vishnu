from __future__ import annotations
from pathlib import Path
from devices.continuity_sync import ContinuitySync
from future_intelligence.gates import TrustGate
from future_intelligence.everyday import EverydayIntelligence
from future_intelligence.deep_brain import LifeGraph
from future_intelligence.second_brain_graph import SecondBrainLifeGraph
from future_intelligence.operations import PersonalOperations
from future_intelligence.multimodal import WorldUnderstanding
from future_intelligence.everywhere import PersonalAIEverywhere
from future_intelligence.sovereignty import HybridIntelligenceRouter
from future_intelligence.autonomy import AdvancedAutonomy
from future_intelligence.autonomy_runtime import install as install_autonomy_runtime
from future_intelligence.work_orchestration.p10_runtime import install as install_work_orchestration_runtime
from future_intelligence.work_orchestration.hierarchical_runtime import install as install_hierarchical_work_planning
from future_intelligence.work_orchestration.versioned_replanning import install as install_versioned_replanning
from future_intelligence.work_orchestration.completion_runtime import install as install_completion_judge
from future_intelligence.work_orchestration.project_mode_runtime import install as install_project_autonomy_modes
from future_intelligence.work_orchestration.completion_propagation import install as install_completion_propagation, bind_notifications as bind_canonical_completion_notifications
from future_intelligence.work_orchestration.event_normalization import WorkEventNormalizer
from future_intelligence.work_orchestration.notification_bridge import WorkNotificationBridge
from future_intelligence.work_orchestration.memory_promotion import WorkMemoryPromotionBridge
from future_intelligence.capability_forge import (
    CapabilityForgeBuildService,
    CapabilityForgeExecutionBridge,
    CapabilityForgeLifecycle,
    CapabilityForgeWorkBridge,
    CapabilityPackageBuilder,
    GeneratedCapabilityEvaluator,
    build_capability_forge,
)
from future_intelligence.capability_forge.governed_activation import GovernedCapabilityActivationService
from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.generated_runtime import rehydrate_generated_capabilities
from core.p10_approval_continuation import install as install_p10_turn_continuation

install_autonomy_runtime(AdvancedAutonomy)
install_work_orchestration_runtime(AdvancedAutonomy)
install_hierarchical_work_planning(AdvancedAutonomy)
install_versioned_replanning(AdvancedAutonomy)
install_completion_judge(AdvancedAutonomy)
install_project_autonomy_modes(AdvancedAutonomy)


class FutureIntelligenceProgram:
    """Integrated P4-P10 runtime foundation, deliberately gated by P3 evidence."""

    def __init__(self, data_dir: Path, *, runtime: dict):
        root = Path(data_dir)
        self.gate = TrustGate(); self.runtime = runtime
        self.everyday = EverydayIntelligence(root/'everyday.sqlite3',memory=runtime.get('memory'),second_brain=runtime.get('second_brain'),proactive=runtime.get('proactive'),continuity=runtime.get('continuity'),integrations=runtime.get('integrations'),events=runtime.get('events'))
        if runtime.get('memory') is not None:
            try: runtime['memory'].everyday_intelligence=self.everyday
            except Exception: pass
        runtime['everyday_intelligence']=self.everyday
        self.life_graph=LifeGraph(root/'life-graph.sqlite3'); self.second_brain_life_graph=SecondBrainLifeGraph(self.life_graph,runtime.get('second_brain')); runtime['second_brain_life_graph']=self.second_brain_life_graph
        turn_executor=runtime.get('executor'); governed_executor=runtime.get('agent_executor') or turn_executor
        self.operations=PersonalOperations(gate=self.gate,executor=governed_executor,automations=runtime.get('automations'),events=runtime.get('events'),second_brain=runtime.get('second_brain'),memory=runtime.get('memory'),everyday=self.everyday,path=root/'operations.sqlite3')
        memory=runtime.get('memory')
        self.world=WorldUnderstanding(gate=self.gate,events=runtime.get('events'),path=root/'world.sqlite3',device_registry=runtime.get('device_registry'),audit=getattr(memory,'audit',None) if memory is not None else None)
        executor=turn_executor; approvals=getattr(governed_executor,'approvals',None) if governed_executor is not None else None
        epoch_provider=approvals.current_security_epoch if approvals is not None and hasattr(approvals,'current_security_epoch') else (lambda:0)
        self.continuity_sync=ContinuitySync(runtime.get('continuity'),gate=self.gate,device_registry=runtime.get('device_registry'),security_epoch_provider=epoch_provider,operations=self.operations,world=self.world,events=runtime.get('events')); runtime['continuity_sync']=self.continuity_sync
        self.everywhere=PersonalAIEverywhere(gate=self.gate,device_registry=runtime.get('device_registry'),continuity=runtime.get('continuity'),continuity_sync=self.continuity_sync)
        self.hybrid=HybridIntelligenceRouter(gate=self.gate,canonical_router=runtime.get('models'))
        canonical_stop=runtime.get('emergency_stop_provider')
        if canonical_stop is None and runtime.get('automations') is not None:
            budgets=getattr(runtime.get('automations'),'budgets',None)
            if budgets is not None and hasattr(budgets,'emergency_stopped'): canonical_stop=budgets.emergency_stopped
        self.autonomy=AdvancedAutonomy(gate=self.gate,operations=self.operations,events=runtime.get('events'),path=root/'autonomy.sqlite3',executor=governed_executor,automations=runtime.get('automations'),models=runtime.get('models'),memory=runtime.get('second_brain') or runtime.get('memory'),knowledge=runtime.get('knowledge'),world=self.world,continuity=self.continuity_sync,emergency_stop_provider=canonical_stop)
        self.autonomy.project_store=runtime.get('project_store') or runtime.get('projects')
        runtime['advanced_autonomy']=self.autonomy
        install_completion_propagation(self.autonomy)

        # Capability Forge reuses Universal Capabilities + Canonical Work. This
        # startup hook is intentionally additive: generated capabilities remain
        # inert unless they were already owner-approved and persisted active.
        self.capability_forge=None
        self.capability_forge_lifecycle=None
        self.capability_forge_evaluator=None
        self.capability_forge_work=None
        self.capability_forge_activation=None
        self.capability_forge_packages=CapabilityPackageBuilder()
        self.capability_catalog=None
        self.rehydrated_generated_capabilities=()
        data_root=root.parent
        state=getattr(runtime.get('integrations'),'state_store',None)
        tools=runtime.get('tools')
        if state is not None and tools is not None:
            try:
                self.capability_catalog=CapabilityCatalogStore(state.path.parent/'capability-catalog.sqlite3')
                self.capability_forge=build_capability_forge(data_root,catalog=self.capability_catalog,events=runtime.get('events'))
                self.capability_forge_lifecycle=CapabilityForgeLifecycle(data_root/'capability-forge.sqlite3')
                self.capability_forge_evaluator=GeneratedCapabilityEvaluator(self.capability_forge_lifecycle,events=runtime.get('events'))
                work_runtime=getattr(self.autonomy,'_work_bridge',None)
                work_store=getattr(work_runtime,'work',None)
                if work_store is not None:
                    self.capability_forge_work=CapabilityForgeWorkBridge(work_store,events=runtime.get('events'))
                if approvals is not None:
                    self.capability_forge_activation=GovernedCapabilityActivationService(
                        catalog=self.capability_catalog,
                        approvals=approvals,
                        tools=tools,
                        data_root=data_root,
                        lifecycle=self.capability_forge_lifecycle,
                        events=runtime.get('events'),
                    )

                def forge_invocation_observer(capability, _context):
                    capability_id=str(capability.get('id') or '')
                    version=str(capability.get('version') or '')
                    def observe(*,ok,duration_ms,error_code=None):
                        self.capability_forge_lifecycle.record_invocation(
                            capability_id=capability_id,
                            version=version,
                            ok=bool(ok),
                            duration_ms=float(duration_ms),
                            error_code=error_code,
                        )
                    return observe

                self.rehydrated_generated_capabilities=tuple(rehydrate_generated_capabilities(
                    self.capability_catalog,
                    tools=tools,
                    data_root=data_root,
                    invocation_observer=forge_invocation_observer,
                ))
                runtime.update({
                    'capability_forge':self.capability_forge,
                    'capability_forge_store':self.capability_forge.store,
                    'capability_forge_lifecycle':self.capability_forge_lifecycle,
                    'capability_forge_evaluator':self.capability_forge_evaluator,
                    'capability_forge_work':self.capability_forge_work,
                    'capability_forge_packages':self.capability_forge_packages,
                    'capability_forge_activation':self.capability_forge_activation,
                    'capability_catalog':self.capability_catalog,
                    'generated_capabilities_rehydrated':self.rehydrated_generated_capabilities,
                    'capability_forge_execution_factory':self.forge_execution_bridge,
                    'capability_forge_build_factory':self.forge_build_service,
                })
                if runtime.get('events') is not None:
                    runtime['events'].emit(
                        'capability_forge.runtime_ready',
                        rehydrated=list(self.rehydrated_generated_capabilities),
                        activation_available=bool(self.capability_forge_activation),
                        engineering_available=bool(runtime.get('engineering_executor')),
                        monitoring_available=True,
                    )
            except Exception as exc:
                # Forge startup is fail-closed and cannot break the canonical
                # assistant runtime. The error type is observable without secrets.
                if runtime.get('events') is not None:
                    runtime['events'].emit('capability_forge.runtime_unavailable',error_type=type(exc).__name__)

        # One canonical raw->work.* translation layer on the existing EventBus.
        # It is installed before Notifications/Memory so every downstream product
        # surface observes the same taxonomy and Activities audit the same events.
        self.work_event_normalizer=None
        if runtime.get('events') is not None:
            audit=getattr(runtime.get('memory'),'audit',None) if runtime.get('memory') is not None else None
            self.work_event_normalizer=WorkEventNormalizer(runtime['events'],autonomy=self.autonomy,audit=audit)
            runtime['work_event_normalizer']=self.work_event_normalizer

        self.work_notifications=None
        if runtime.get('events') is not None and runtime.get('notifications') is not None:
            self.work_notifications=WorkNotificationBridge(runtime['events'],runtime['notifications']); bind_canonical_completion_notifications(self.work_notifications,self.autonomy); runtime['work_notifications']=self.work_notifications
        self.work_memory_promotion=None
        if runtime.get('events') is not None and runtime.get('second_brain') is not None:
            self.work_memory_promotion=WorkMemoryPromotionBridge(runtime['events'],self.autonomy,runtime['second_brain']); runtime['work_memory_promotion']=self.work_memory_promotion
        if turn_executor is not None: install_p10_turn_continuation(type(turn_executor))

    def forge_execution_bridge(self):
        """Return a live Forge->Engineering bridge only after engineering is ready."""
        executor=self.runtime.get('engineering_executor')
        work_runtime=getattr(self.autonomy,'_work_bridge',None)
        work_store=getattr(work_runtime,'work',None)
        if executor is None or work_store is None:
            return None
        return CapabilityForgeExecutionBridge(
            work_store,
            executor,
            events=self.runtime.get('events'),
            lifecycle=self.capability_forge_lifecycle,
        )

    def forge_build_service(self):
        """Return the governed execute->package service after Engineering is ready."""
        executor=self.runtime.get('engineering_executor')
        engineering=self.runtime.get('engineering')
        work_runtime=getattr(self.autonomy,'_work_bridge',None)
        work_store=getattr(work_runtime,'work',None)
        if executor is None or engineering is None or work_store is None or self.capability_forge_lifecycle is None:
            return None
        return CapabilityForgeBuildService(
            work_store=work_store,
            engineering_runtime=engineering,
            engineering_executor=executor,
            package_builder=self.capability_forge_packages,
            output_root=Path(self.runtime.get('settings_data_dir') or engineering.evidence_root.parent)/'generated-capabilities',
            lifecycle=self.capability_forge_lifecycle,
            events=self.runtime.get('events'),
        )

    def status(self):
        p5_link=self.second_brain_life_graph.status(); p4_status=self.everyday.safe_status()
        return {'p4':{'implemented':True,'activation':'safe-now','lifecycle':p4_status},'p5':{'implemented':True,'activation':'safe-now','second_brain_linked':p5_link['linked'],'linked_memory_nodes':p5_link['memory_nodes']},'p6':{'implemented':True,'activation':self.gate.decision('p6').reason,'operations':self.operations.safe_status()},'p7':{'implemented':True,'activation':self.gate.decision('p7').reason},'p8':{'implemented':True,'activation':self.gate.decision('p8').reason},'p9':{'implemented':True,'activation':self.gate.decision('p9').reason,'canonical_router':self.hybrid.authoritative},'p10':{'implemented':True,'activation':self.gate.decision('p10').reason,'autonomy':self.autonomy.status()}}