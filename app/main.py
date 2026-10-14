from __future__ import annotations

import logging
import sys
import threading
import time

from agent.effect_runtime import EffectAwareDurableAgentExecutor
from app.e9_runtime import attach_e9_runtime, start_e9_services, stop_e9_services
from automation.engine import AutomationEngine
from capabilities.benchmark import CapabilityBenchmark
from capabilities.dialogue_evaluation import ModelDialogueEvaluation
from capabilities.scenarios import CompetitiveScenarioSuite
from continuity.runtime import build_agent_continuity_runtime
from core.config import settings
from core.durable_approval_runtime import DurableApprovalTurnRuntime
from core.events import EventBus
from core.preferences import Preferences
from core.runtime_composition import compose_vishnu_runtime
from core.telemetry import Telemetry
from devices.continuity import ContinuityService
from devices.gateway import DeviceGateway
from devices.registry import DeviceRegistry
from evidence import EvidenceStore
from evidence.ingestion import EvidenceIngestor
from evolution import (
    CodeBodyEvolutionService,
    EvolutionHandoffService,
    EvolutionMode,
    EvolutionService,
    EvolutionStore,
    GitHubPublicReviewVerifier,
    GuardedVerificationProvider,
    LocalSubprocessVerificationProvider,
    OwnerBodyAdoptionService,
)
from evolution.runtime_config import CodeBodyRuntimeConfig
from future_intelligence.engineering.final_qualification import EngineeringCandidateFinalizer
from future_intelligence.engineering.runtime import EngineeringRuntime
from future_intelligence.engineering.work_executor import EngineeringWorkExecutor
from future_intelligence.program import FutureIntelligenceProgram
from future_intelligence.work_orchestration import LocalGitRepositoryProvider, WorkDispatcher
from future_intelligence.workers import WorkerIntelligenceExecutor
from identity import IdentityStore
from integrations.plugins import PluginManifestRegistry
from integrations.runtime import build_integrations
from knowledge.governance import KnowledgeAuthority
from knowledge.universal_store import UniversalKnowledgeStore
from memory.governance import GovernedMemory
from memory.second_brain import SecondBrain
from memory.store import MemoryStore
from memory.vector_store import VectorStore
from models.governed_router import GovernedModelRouter
from notifications.apns import APNsProvider
from notifications.service import NotificationService
from onboarding.first_run import FirstRunCoordinator
from proactive.engine import AttentionRelevanceEngine
from qualification.program import P3QualificationProgram
from qualification.voice import VoiceQualificationRecorder
from recovery.backup import BackupService
from security.vault import SecretVault
from security.owner_access import OwnerAccessStore
from sensorium import (
    DesktopPhysicalSensorAdapter,
    MobilePhysicalSensorAdapter,
    SensoriumLiveWorkProjection,
    VirtualDeviceLab,
)
from tools import benchmark as benchmark_tools
from tools import engineering_repository as engineering_repository_tools
from tools import engineering_work as engineering_work_tools
from tools.builtins import register_builtin_tools
from tools.registry import ToolRegistry
from voice.realtime import RealtimeVoiceSession
from voice.wake_phrase import WakePhraseGate


logger = logging.getLogger(__name__)


def build_runtime():
    telemetry=Telemetry(settings.data_dir/'telemetry.json'); events=EventBus(listener_failure_handler=lambda _event,_exc:telemetry.increment('events.listener_failures')); preferences=Preferences(settings.data_dir/'preferences.json'); backups=BackupService(settings.data_dir)
    vault=SecretVault(settings.data_dir/'vault.json',settings.vault_password or None)
    memory=MemoryStore(settings.data_dir/'assistant.sqlite3'); models=GovernedModelRouter(settings,events=events,audit=memory.audit,vault=vault); models.set_owner_privacy(str(preferences.get('model_privacy_mode',settings.model_privacy_mode))); vector=VectorStore(settings.data_dir/'vectors.sqlite3',lambda text:models.embed(text,sensitivity='sensitive')); memory_engine=SecondBrain(memory,models,vector); second_brain=GovernedMemory(memory_engine,settings.data_dir/'memory-candidates.sqlite3',events=events,is_enabled=lambda: bool(preferences.get('memory_enabled',True)))
    knowledge_store=UniversalKnowledgeStore(settings.data_dir/'knowledge.sqlite3',settings.data_dir/'knowledge'/'objects'); knowledge=KnowledgeAuthority(knowledge_store,events=events); device_registry=DeviceRegistry(settings.data_dir/'devices.sqlite3',events=events); owner_access=OwnerAccessStore(settings.data_dir/'owner-access.sqlite3'); device_gateway=DeviceGateway(device_registry,events); continuity=ContinuityService(settings.data_dir/'continuity.sqlite3',events=events,second_brain=second_brain)
    primary_thread=continuity.latest_thread()
    if primary_thread is None: primary_thread_id=continuity.create_thread('Primary Vishnu Context',device_id='desktop',context={'surface':'desktop','topic':'current work'})
    else: primary_thread_id=primary_thread['id']; continuity.set_active('desktop',primary_thread_id)
    proactive=AttentionRelevanceEngine(settings.data_dir/'proactive.sqlite3',events=events,second_brain=second_brain,enabled=settings.proactive_enabled,interruptions_per_hour=settings.proactive_interruptions_per_hour,default_cooldown_seconds=settings.proactive_default_cooldown_seconds)
    integrations,adapters,oauth,oauth_providers=build_integrations(settings,vault); plugins=PluginManifestRegistry(settings.data_dir/'plugins'); plugins.load(); apns=APNsProvider(settings,device_registry,events); notifications=NotificationService(settings.data_dir/'notifications.sqlite3',device_registry,apns,events,owner_preferences=preferences); tools=ToolRegistry(settings); tools.set_autonomy_mode(str(preferences.get('autonomy_mode',settings.autonomy_mode)))
    agent_executor=EffectAwareDurableAgentExecutor(models=models,tools=tools,memory=memory,events=events,second_brain=second_brain,knowledge=knowledge,telemetry=telemetry); executor=DurableApprovalTurnRuntime(agent_executor,continuity,settings.data_dir/'turn-runtime.sqlite3',events=events)
    evidence_store=EvidenceStore(settings.data_dir/'evidence.sqlite3'); evidence_ingestor=EvidenceIngestor(evidence_store); evolution_store=EvolutionStore(connection=evidence_store.connection); identity_store=IdentityStore(settings.data_dir/'identity.sqlite3'); code_body_config=CodeBodyRuntimeConfig.from_environment(data_dir=settings.data_dir)
    agent_continuity_runtime=build_agent_continuity_runtime(data_dir=settings.data_dir,backups=backups,identity_store=identity_store,agent_executor=agent_executor,events=events,repository_root=code_body_config.repository_root)
    try:evolution_mode=EvolutionMode(str(preferences.get('evolution_mode',EvolutionMode.CO_EVOLVE.value)))
    except ValueError:evolution_mode=EvolutionMode.CO_EVOLVE
    evolution=EvolutionService(store=evolution_store,ingestor=evidence_ingestor,mode=evolution_mode)
    def context_provider():
        latest=continuity.latest_thread(); return {'devices':device_registry.list(),'integrations':integrations.list(),'memory_count':len(second_brain.graph().get('nodes',[])),'continuity':latest or {},'focus_mode':bool(preferences.get('focus_mode',False))}
    automations=AutomationEngine(settings.data_dir/'automations.sqlite3',executor=executor,events=events,context_provider=context_provider,default_timeout_seconds=settings.workflow_default_timeout_seconds,default_retries=settings.workflow_default_retries)
    capability_objects=register_builtin_tools(tools,memory,settings,models=models,automation_engine=automations,apns=apns,second_brain=second_brain,events=events,proactive_engine=proactive,continuity_service=continuity,integration_adapters=adapters,memory_enabled=lambda: bool(preferences.get('memory_enabled',True)))
    sensorium_lab=VirtualDeviceLab.from_device_registry(device_registry,event_bus=events); sensorium_live_work=SensoriumLiveWorkProjection(events); sensorium_desktop=DesktopPhysicalSensorAdapter(device_registry,computer=capability_objects.get('computer'),event_bus=events); sensorium_mobile=MobilePhysicalSensorAdapter(device_registry,device_gateway,event_bus=events)
    voice=RealtimeVoiceSession(models,executor,events); voice_qualification=VoiceQualificationRecorder(settings.data_dir/'voice-qualification.sqlite3',events=events); p3_qualification=P3QualificationProgram(settings.data_dir/'p3-qualification.sqlite3'); wake_phrase=WakePhraseGate(events,phrases=(str(preferences.get('wake_phrase','Hey Personal')),)); events.subscribe('voice.transcript',lambda event:wake_phrase.accept(event.get('text',''))); events.subscribe('state',lambda event:telemetry.increment(f"state.{event.get('state','unknown')}")); events.subscribe('voice.reply',lambda event:telemetry.increment('voice.replies'))
    runtime={'settings':settings,'events':events,'runtime_state':events.runtime_state,'memory':memory,'models':models,'second_brain':second_brain,'knowledge':knowledge,'knowledge_store':knowledge_store,'vector_store':vector,'device_registry':device_registry,'owner_access':owner_access,'device_gateway':device_gateway,'continuity':continuity,'proactive':proactive,'tools':tools,'executor':executor,'turn_runtime':executor,'agent_executor':agent_executor,'effect_ledger':agent_executor.effect_ledger,'evidence_store':evidence_store,'evidence_ingestor':evidence_ingestor,'identity_store':identity_store,'evolution_store':evolution_store,'evolution':evolution,'evolution_handoff':None,'code_body_config':code_body_config,'repository_provider':None,'engineering':None,'engineering_executor':None,'engineering_finalizer':None,'code_body':None,'body_adoption':None,'code_worker_epoch':int(time.time()),'automations':automations,'integrations':integrations,'integration_adapters':adapters,'oauth':oauth,'oauth_providers':oauth_providers,'plugins':plugins,'vault':vault,'voice':voice,'voice_qualification':voice_qualification,'p3_qualification':p3_qualification,'wake_phrase':wake_phrase,'apns':apns,'notifications':notifications,'telemetry':telemetry,'preferences':preferences,'backups':backups,'computer':capability_objects.get('computer'),'sensorium_lab':sensorium_lab,'sensorium_live_work':sensorium_live_work,'sensorium_desktop':sensorium_desktop,'sensorium_mobile':sensorium_mobile,'primary_continuity_thread_id':primary_thread_id,'worker_intelligence':None,'work_dispatcher':None,**agent_continuity_runtime}; p3_qualification.runtime=runtime
    future=FutureIntelligenceProgram(settings.data_dir/'future-intelligence',runtime=runtime); runtime.update({'future_intelligence':future,'everyday_intelligence':future.everyday,'life_graph':future.life_graph,'personal_operations':future.operations,'world_understanding':future.world,'personal_ai_everywhere':future.everywhere,'hybrid_intelligence':future.hybrid,'advanced_autonomy':future.autonomy})
    if hasattr(executor,'attach_autonomy'): executor.attach_autonomy(future.autonomy)
    work_bridge=getattr(future.autonomy,'_work_bridge',None)
    if work_bridge is not None:
        if hasattr(agent_executor,'attach_work_store'): agent_executor.attach_work_store(work_bridge.work)
        runtime['work_dispatcher']=WorkDispatcher(work_bridge.work)
        runtime['worker_intelligence']=WorkerIntelligenceExecutor(models,work_bridge.work,registry=getattr(future.autonomy,'_worker_registry',None))
        handoff=EvolutionHandoffService(evolution_store=evolution_store,work_store=work_bridge.work); runtime['evolution_handoff']=handoff
        if code_body_config.repository_root is not None:
            try:
                repository_provider=LocalGitRepositoryProvider(repository=code_body_config.repository,repository_root=code_body_config.repository_root,workspace_root=code_body_config.workspace_root)
                engineering=EngineeringRuntime(repository_provider=repository_provider,work_store=work_bridge.work,evidence_root=settings.data_dir/'engineering-evidence',continuation_authority_guard=agent_continuity_runtime['continuation_authority'].assert_active)
                engineering_repository_tools.register(tools,engineering)
                inner_verifier=None
                if code_body_config.local_verification_enabled:
                    inner_verifier=LocalSubprocessVerificationProvider((('compile', (sys.executable,'-m','compileall','-q','app','agent','automation','browser','capabilities','continuity','core','dashboard','desktop','devices','evidence','evolution','future_intelligence','identity','integrations','knowledge','memory','models','proactive','qualification','security','sensorium','server','tools','training','ui','updates','vision','voice','visual_intelligence')),('evolution-safety-tests',(sys.executable,'-m','pytest','-q','tests/test_evolution_e5.py','tests/test_evolution_e6_handoff.py','tests/test_evolution_e7_code_body.py')),('integration-full-suite',(sys.executable,'-m','pytest','-q'))),enabled=True,timeout_seconds=code_body_config.verification_timeout_seconds)
                verification_provider=GuardedVerificationProvider(repository_provider=repository_provider,inner=inner_verifier) if inner_verifier is not None else None
                engineering_executor=EngineeringWorkExecutor(runtime=engineering,models=models,verification_provider=verification_provider)
                engineering_finalizer=EngineeringCandidateFinalizer(runtime=engineering,models=models)
                engineering_work_tools.register(tools,engineering_executor,runtime_epoch_provider=lambda:runtime['code_worker_epoch'])
                review_verifier=GitHubPublicReviewVerifier(repository=code_body_config.repository)
                code_body=CodeBodyEvolutionService(handoffs=handoff,work_store=work_bridge.work,evidence_store=evidence_store,identity_store=identity_store,repository_provider=repository_provider,verification_provider=verification_provider,review_verifier=review_verifier,continuation_authority_guard=agent_continuity_runtime['continuation_authority'].assert_active)
                adoption=OwnerBodyAdoptionService(evolution_store=evolution_store,code_body=code_body,identity_store=identity_store,repository_provider=repository_provider)
                runtime.update({'repository_provider':repository_provider,'engineering':engineering,'engineering_executor':engineering_executor,'engineering_finalizer':engineering_finalizer,'code_body':code_body,'body_adoption':adoption})
                events.emit('engineering.runtime_ready',repository=code_body_config.repository,local_verification=bool(verification_provider),final_qualification=True,remote_mutation_authority=False)
                events.emit('evolution.code_body_ready',repository=code_body_config.repository,local_verification=bool(verification_provider))
            except Exception as exc:
                events.emit('evolution.code_body_unavailable',error_type=type(exc).__name__)
    benchmark=CapabilityBenchmark(settings.data_dir/'capability-benchmark.sqlite3',runtime=runtime); model_evaluation=ModelDialogueEvaluation(settings.data_dir/'model-dialogue-evaluation.sqlite3',models,audit=memory.audit); scenarios=CompetitiveScenarioSuite(runtime,benchmark); runtime.update({'benchmark':benchmark,'model_evaluation':model_evaluation,'capability_scenarios':scenarios}); benchmark_tools.register(tools,benchmark,scenarios)
    def append_continuity(kind,text,device_id=None,conversation_id=None,event_id=None):
        if not text or conversation_id:return
        source_device=str(device_id or 'desktop')
        try:
            thread=continuity.active_for_device(source_device)
            if thread is None:thread=continuity.resume(source_device)['thread']
            continuity.append(thread['id'],device_id=source_device,kind=kind,payload={'text':str(text)},event_id=str(event_id) if event_id else None)
        except Exception as exc:
            telemetry.increment('continuity.append_failures')
            logger.error('Conversation continuity append failed for %s from %s',kind,source_device,exc_info=(type(exc),exc,exc.__traceback__))
            events.emit('continuity.append_failed',kind=str(kind),source_device=source_device,error_type=type(exc).__name__)
    events.subscribe('conversation.user',lambda event:append_continuity('user_message',event.get('text'),event.get('device_id'),event.get('conversation_id'),event.get('event_id') or event.get('message_id'))); events.subscribe('conversation.assistant',lambda event:append_continuity('assistant_message',event.get('text'),event.get('device_id'),event.get('conversation_id'),event.get('event_id') or event.get('message_id'))); events.subscribe('proactive.ingest',lambda event:proactive.consider(str(event.get('source','unknown')),dict(event.get('payload') or {}),context={**context_provider(),**dict(event.get('context') or {})})); events.subscribe('automation.failed',lambda event:proactive.consider('automation',{'kind':'failure','id':event.get('automation_id'),'failed':True,'importance':.7,'message':f"An automation failed: {event.get('error','unknown error')}"},context=context_provider())); events.subscribe('workflow.failed',lambda event:proactive.consider('workflow',{'kind':'failure','id':event.get('run_id'),'failed':True,'importance':.75,'message':f"A workflow needs attention: {event.get('error','workflow failed')}"},context=context_provider())); events.subscribe('workflow.approval_required',lambda event:proactive.consider('workflow',{'kind':'approval','id':event.get('run_id'),'needs_approval':True,'urgency':.7,'importance':.8,'message':f"A workflow is waiting for your approval to use {event.get('tool','a tool')}."},context=context_provider()))
    attach_e9_runtime(runtime)
    runtime['composition']=compose_vishnu_runtime(runtime)
    return runtime


def start_server(runtime):
    if not settings.control_server_enabled:return
    from server.api import create_app
    from server.agent_continuity_api import agent_continuity_router
    from server.evidence_api import evidence_router
    from server.evolution_api import evolution_router
    from server.identity_api import identity_router
    from server.model_provider_api import model_provider_router
    from server.sensorium_physical_api import sensorium_physical_router
    import uvicorn
    composition=runtime['composition']
    app=create_app(composition.work.turn_runtime,settings,device_registry=composition.devices.registry,device_gateway=composition.devices.gateway,second_brain=composition.memory.second_brain,automations=composition.work.automation_engine,runtime=runtime)
    app.include_router(evolution_router(runtime)); app.include_router(identity_router(runtime)); app.include_router(evidence_router(runtime)); app.include_router(agent_continuity_router(runtime)); app.include_router(model_provider_router(runtime)); app.include_router(sensorium_physical_router(runtime),prefix='/owner/ai')
    uvicorn.run(app,host=settings.control_server_host,port=settings.control_server_port,log_level='warning')


def _close_runtime(runtime, *, services_started=False, floating_presence=None):
    if floating_presence is not None:
        floating_presence.close()
    runtime['voice'].stop()
    runtime['sensorium_live_work'].close()
    if services_started:
        stop_e9_services(runtime)
        runtime['automations'].stop()
    runtime['notifications'].close()
    runtime['telemetry'].persist()
    runtime['apns'].close()
    runtime['evidence_store'].close()
    runtime['identity_store'].close()


def main():
    from PyQt6.QtWidgets import QApplication, QDialog
    from desktop.floating_presence import FloatingPresence
    from ui.main_window import MainWindow
    from ui.canonical_main_window import CanonicalMainWindow
    from ui.first_run_wizard import FirstRunWizard

    app=QApplication(sys.argv); app.setApplicationName('Vishnu')
    FirstRunCoordinator.apply_pending_restore(settings.data_dir, vault_password=settings.vault_password or None)
    runtime=build_runtime()
    setup=FirstRunCoordinator(settings.data_dir,runtime=runtime); runtime['first_run_setup']=setup
    if setup.should_run():
        wizard=FirstRunWizard(runtime,setup)
        result=wizard.exec()
        if result != QDialog.DialogCode.Accepted or wizard.restart_required or wizard.external_connect or not setup.ready:
            _close_runtime(runtime)
            return 0

    composition=runtime['composition']
    composition.work.automation_engine.start(); start_e9_services(runtime)
    if settings.control_server_enabled:threading.Thread(target=start_server,args=(runtime,),daemon=True).start()
    window=CanonicalMainWindow(events=runtime['events'],executor=composition.work.turn_runtime,memory=composition.memory.store,runtime=runtime); window.show(); floating_presence=FloatingPresence(runtime=runtime); runtime['floating_presence']=floating_presence; floating_presence.show()
    if runtime['preferences'].get('launch_voice_on_start'):window.toggle_voice()
    code=app.exec(); _close_runtime(runtime,services_started=True,floating_presence=floating_presence); return code


if __name__=='__main__':raise SystemExit(main())
