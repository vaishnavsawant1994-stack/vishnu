from __future__ import annotations
from contextlib import asynccontextmanager
import asyncio
import json
import os
from app.main import build_runtime
from app.e9_runtime import start_e9_services, stop_e9_services
from core.config import settings
from onboarding.first_run import FirstRunCoordinator
from core.storage import validate_runtime_storage
from future_intelligence.release_control.automation import ReleaseAutomationService
from future_intelligence.release_control.handoff import ReleaseAwareEngineeringFinalizer
from future_intelligence.release_control.monitoring import ProductionReleaseMonitor
from future_intelligence.release_control.runtime import build_release_control_runtime
from security.pwa_sessions import PwaSessionStore
from server.api import create_app
from server.activities_api import activities_router
from server.apps_tools_api import apps_tools_router
from server.devices_presence_api import devices_presence_router
from server.data_plane_owner_api import data_plane_owner_router
from server.about_api import about_router
from server.approval_api import approval_router
from server.approvals_center_api import approvals_center_router
from server.automation_visibility_api import automation_visibility_router
from server.recovery_visibility_api import recovery_visibility_router
from server.cloud_security import cloud_security_router
from server.agent_continuity_api import agent_continuity_router
from server.agent_workforce_assets import agent_workforce_assets_router
from server.agent_workforce_pwa_api import agent_workforce_pwa_router
from server.agent_work_requests_api import agent_work_requests_router
from server.evidence_api import evidence_router
from server.evolution_api import evolution_router
from server.identity_api import identity_router
from server import iphone_pwa as iphone_pwa_module
from server.owner_product import owner_product_router
from server.owner_intelligence_api import owner_intelligence_router
from server.owner_intelligence_ui import OwnerIntelligenceUiMiddleware, owner_intelligence_ui_router
from server.owner_engineering_api import owner_engineering_router
from server.owner_engineering_ui import OwnerEngineeringUiMiddleware, owner_engineering_ui_router
from server.owner_release_api import owner_release_router
from server.owner_release_ui import OwnerReleaseUiMiddleware, owner_release_ui_router
from server.portable_intelligence_api import portable_intelligence_router
from server.portable_intelligence_ui import PortableIntelligenceUiMiddleware, portable_intelligence_ui_router
from server.self_improvement_ui import SelfImprovementUiMiddleware, self_improvement_ui_router
from server.capability_console import capability_console_router
from server.capability_forge_api import capability_forge_router
from server.capability_forge_v3_api import capability_forge_oauth_callback_router, capability_forge_v3_router
from server.capability_forge_ui import CapabilityForgeUiMiddleware, capability_forge_ui_router
from server.capability_forge_v3_ui import capability_forge_v3_ui_router
from server.memory_knowledge_inspection import memory_knowledge_inspection_router
from server.memory_governance_api import memory_governance_router
from server.memory_ambient_api import memory_ambient_router
from server.everyday_intelligence_api import everyday_intelligence_router
from server.personal_operations_api import personal_operations_router
from server.multimodal_world_api import multimodal_world_router
from server.continuity_sync_api import continuity_sync_router
from server.pwa_security import pwa_security_router
from server.pwa_session_middleware import PwaSessionMiddleware
from server.native_capability_auth import native_capability_auth_router
from server.logical_request_middleware import LogicalRequestMiddleware
from server.request_aware_pwa_state import RequestAwareIphonePwaState
from server.runtime_state_api import runtime_state_router
from server.session_bound_executor import SessionBoundExecutor
from server.conversation_voice_api import conversation_voice_router
from server.workflow_budget_api import workflow_budget_router
from server.workflow_budget_ui import WorkflowBudgetUiMiddleware, workflow_budget_ui_router
from server.connector_api import connector_router
from server.connector_ui import ConnectorUiMiddleware, connector_ui_router
from server.connector_oauth_callback import connector_oauth_callback_router
from server.content_ingestion_api import content_ingestion_router
from server.visualizations_api import visualizations_router
from server.visualize_ui import VisualizeUiMiddleware, visualize_assets_router
from projects.store import ProjectStore
from projects.workforce_adapter import ProjectWorkforceStoreAdapter
from products.store import ProductStore
from products.license_store import ProductLicenseStore
from server.projects_api import projects_router
from server.products_api import products_router
from server.product_distribution_api import product_distribution_router
from server.product_runner_queue_api import product_runner_queue_router
from server.project_work_api import project_work_router
from server.project_autonomy_api import project_autonomy_router
from server.work_order_detail_api import work_order_detail_router
from server.global_work_api import global_work_router
from server.work_attention_api import work_attention_router
from visual_intelligence import VisualIntelligenceService

class CanonicalConversationProjection:
    """Compatibility view for legacy PWA conversation helpers."""
    def __init__(self,continuity):self._continuity=continuity
    def __getattr__(self,name):return getattr(self._continuity,name)
    def append(self,thread_id,*,device_id,kind,payload,event_id=None):
        if kind in {'user_message','assistant_message'} and event_id is None:
            return {'event_id':None,'sequence':None,'thread_id':thread_id,'duplicate':True,'projection':'canonical-turn-runtime'}
        return self._continuity.append(thread_id,device_id=device_id,kind=kind,payload=payload,event_id=event_id)

def _release_monitor_interval_seconds():
    try:
        value=float(str(os.environ.get('VISHNU_RELEASE_MONITOR_INTERVAL_SECONDS','60')).strip() or '60')
    except (TypeError,ValueError):
        value=60.0
    return max(30.0,min(value,3600.0))

storage_status=validate_runtime_storage(settings)
def _native_client_redirects():
    raw=os.getenv('VISHNU_NATIVE_CLIENT_REDIRECTS','{}')
    try:
        value=json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError('VISHNU_NATIVE_CLIENT_REDIRECTS must be a JSON object') from exc
    if not isinstance(value,dict) or any(not isinstance(key,str) or not isinstance(uris,list) or
        any(not isinstance(uri,str) for uri in uris) for key,uris in value.items()):
        raise RuntimeError('VISHNU_NATIVE_CLIENT_REDIRECTS must map client IDs to redirect URI arrays')
    return value

runtime=build_runtime();runtime['storage_status']=storage_status
runtime['setup_surface']='web-runtime'
runtime['first_run_setup']=FirstRunCoordinator(settings.data_dir,runtime=runtime)
runtime['first_run_setup'].should_run()
runtime['pwa_sessions']=PwaSessionStore(settings.data_dir/'pwa-sessions.sqlite3',native_client_redirects=_native_client_redirects())
def _json_env(name, default):
    raw=os.getenv(name, '')
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{name} must contain valid JSON') from exc

runtime['android_asset_links']=_json_env('VISHNU_ANDROID_ASSET_LINKS_JSON',[])
runtime['apple_app_site_association']=_json_env('VISHNU_APPLE_APP_SITE_ASSOCIATION_JSON',{})
runtime['visual_intelligence']=VisualIntelligenceService(settings.data_dir/'visual-intelligence.sqlite3',events=runtime.get('events'))
base_project_store=ProjectStore(settings.data_dir/'projects.sqlite3')
project_store=ProjectWorkforceStoreAdapter(base_project_store,runtime['agent_workforce'],events=runtime.get('events'));runtime['project_store']=project_store;runtime['base_project_store']=base_project_store
product_store=ProductStore(settings.data_dir/'products.sqlite3');runtime['product_store']=product_store
product_license_store=ProductLicenseStore(settings.data_dir/'products.sqlite3');runtime['product_license_store']=product_license_store
runtime['release_control']=None;runtime['release_automation']=None;runtime['release_monitor']=None
try:
    dispatcher=runtime.get('work_dispatcher');engineering=runtime.get('engineering')
    work_store=getattr(dispatcher,'store',None) or getattr(engineering,'work_store',None)
    release_control=build_release_control_runtime(data_dir=settings.data_dir,work_store=work_store)
    release_automation=ReleaseAutomationService(
        release_control,
        default_provider=str(os.environ.get('VISHNU_RELEASE_DEFAULT_PROVIDER','')).strip(),
        default_target=str(os.environ.get('VISHNU_RELEASE_TARGET','')).strip(),
    )
    release_monitor=ProductionReleaseMonitor(release_control)
    runtime['release_control']=release_control;runtime['release_automation']=release_automation;runtime['release_monitor']=release_monitor
    if engineering is not None:
        runtime['engineering_finalizer']=ReleaseAwareEngineeringFinalizer(
            runtime=engineering,
            release_automation=release_automation,
            models=runtime.get('models'),
        )
    if runtime.get('events') is not None:
        runtime['events'].emit(
            'release.runtime_ready',
            providers=sorted(release_control.providers),
            mode=release_control.policy().mode.value,
            finalizer_handoff=engineering is not None,
            production_monitoring=True,
            monitor_interval_seconds=_release_monitor_interval_seconds(),
            body_activation_authority=False,
        )
except Exception as exc:
    runtime['release_control']=None;runtime['release_automation']=None;runtime['release_monitor']=None
    if runtime.get('events') is not None:
        runtime['events'].emit('release.runtime_unavailable',error_type=type(exc).__name__)
print(json.dumps({'event':'storage.ready',**storage_status}),flush=True)

@asynccontextmanager
async def lifespan(app):
    runtime['automations'].start();start_e9_services(runtime);evaluation_task=None
    release_automation=runtime.get('release_automation')
    if release_automation is not None:
        try:
            recovery_results=await asyncio.to_thread(release_automation.reconcile)
            if runtime.get('events') is not None:
                runtime['events'].emit(
                    'release.recovery_reconciled',
                    releases=len(recovery_results),
                    recovery_required=sum(1 for item in recovery_results if item.status=='recovery_required'),
                )
        except Exception as exc:
            if runtime.get('events') is not None:
                runtime['events'].emit('release.recovery_failed',error_type=type(exc).__name__)
    async def release_monitor_worker():
        monitor=runtime.get('release_monitor')
        interval=_release_monitor_interval_seconds()
        while True:
            try:
                results=await asyncio.to_thread(monitor.poll_all)
                if results and runtime.get('events') is not None:
                    runtime['events'].emit(
                        'release.monitoring_cycle',
                        releases=len(results),
                        healthy=sum(1 for item in results if item.outcome=='healthy'),
                        transient_failures=sum(1 for item in results if item.outcome=='transient_failure'),
                        rollback_recommended=sum(1 for item in results if item.outcome=='rollback_recommended'),
                    )
            except Exception as exc:
                if runtime.get('events') is not None:
                    runtime['events'].emit('release.monitoring_cycle_failed',error_type=type(exc).__name__)
            await asyncio.sleep(interval)
    release_monitor_task=asyncio.create_task(release_monitor_worker()) if runtime.get('release_monitor') is not None else None
    async def ambient_retention_worker():
        governed = runtime['second_brain']
        while True:
            try: await asyncio.to_thread(governed.expire_ambient_memories, owner_id='owner')
            except Exception as exc: print(json.dumps({'event':'memory.ambient.retention_sweep_failed','error':type(exc).__name__}),flush=True)
            await asyncio.sleep(3600)
    retention_task=asyncio.create_task(ambient_retention_worker())
    if settings.model_evaluation_on_startup:
        async def evaluate_model():
            result=await asyncio.to_thread(runtime['model_evaluation'].run);safe={key:value for key,value in result.items() if key!='cases'};safe['case_results']=[{'case':item['case'],'passed':item['passed'],'error_code':item['error_code']} for item in result['cases']];print(json.dumps({'event':'model.dialogue_evaluation',**safe}),flush=True)
        evaluation_task=asyncio.create_task(evaluate_model())
    try:yield
    finally:
        if release_monitor_task is not None:
            release_monitor_task.cancel()
            try: await release_monitor_task
            except asyncio.CancelledError: pass
        retention_task.cancel()
        try: await retention_task
        except asyncio.CancelledError: pass
        if evaluation_task and not evaluation_task.done():evaluation_task.cancel()
        runtime['voice'].stop();stop_e9_services(runtime);runtime['automations'].stop();runtime['telemetry'].persist();runtime['apns'].close();runtime['visual_intelligence'].close()

app=create_app(runtime['executor'],settings,device_registry=runtime['device_registry'],device_gateway=runtime['device_gateway'],second_brain=runtime['second_brain'],automations=runtime['automations'],runtime=runtime)
app.add_middleware(LogicalRequestMiddleware)
app.add_middleware(PwaSessionMiddleware,sessions=runtime['pwa_sessions'],device_registry=runtime['device_registry'],cookie_max_age=60*60*24*max(1,min(int(getattr(settings,'iphone_device_cookie_days',365)),3650)),first_run_setup=runtime['first_run_setup'])
app.add_middleware(WorkflowBudgetUiMiddleware);app.add_middleware(ConnectorUiMiddleware);app.add_middleware(VisualizeUiMiddleware);app.add_middleware(OwnerIntelligenceUiMiddleware);app.add_middleware(OwnerEngineeringUiMiddleware);app.add_middleware(OwnerReleaseUiMiddleware);app.add_middleware(PortableIntelligenceUiMiddleware);app.add_middleware(SelfImprovementUiMiddleware);app.add_middleware(CapabilityForgeUiMiddleware)
pwa_runtime=dict(runtime);pwa_runtime['executor']=SessionBoundExecutor(runtime['executor'],continuity=runtime['continuity'],surface='iphone-pwa');pwa_runtime['continuity']=CanonicalConversationProjection(runtime['continuity'])
app.include_router(approval_router(runtime,pwa_runtime['executor']))
app.include_router(approvals_center_router(runtime))
app.include_router(conversation_voice_router(runtime,pwa_runtime['executor']))
# The workforce shell router is intentionally mounted before iphone_pwa_router
# only for /iphone and /iphone/. It injects isolated workspace navigation entries
# while every existing API/asset route remains owned by the canonical PWA.
app.include_router(agent_workforce_assets_router(settings))
app.include_router(visualize_assets_router(settings))
_original_pwa_state=iphone_pwa_module.IphonePwaState
iphone_pwa_module.IphonePwaState=lambda:RequestAwareIphonePwaState(cancel_turn=pwa_runtime['executor'].cancel_turn)
try:app.include_router(iphone_pwa_module.iphone_pwa_router(pwa_runtime,settings,include_legacy_runtime_routes=False))
finally:iphone_pwa_module.IphonePwaState=_original_pwa_state
app.include_router(native_capability_auth_router(runtime));app.include_router(visualizations_router(runtime));app.include_router(pwa_security_router(runtime));app.include_router(cloud_security_router(runtime));app.include_router(agent_continuity_router(runtime));app.include_router(identity_router(runtime));app.include_router(evidence_router(runtime));app.include_router(evolution_router(runtime));app.include_router(activities_router(runtime));app.include_router(apps_tools_router(runtime));app.include_router(devices_presence_router(runtime));app.include_router(automation_visibility_router(runtime));app.include_router(recovery_visibility_router(runtime));app.include_router(runtime_state_router(runtime));app.include_router(memory_knowledge_inspection_router(runtime));app.include_router(memory_governance_router(runtime));app.include_router(memory_ambient_router(runtime));app.include_router(everyday_intelligence_router(runtime));app.include_router(personal_operations_router(runtime));app.include_router(content_ingestion_router(runtime));app.include_router(data_plane_owner_router(runtime));app.include_router(about_router(runtime));app.include_router(projects_router(runtime,project_store));app.include_router(products_router(runtime,product_store,project_store));app.include_router(product_distribution_router(runtime,product_store,product_license_store));app.include_router(product_runner_queue_router(runtime,product_store));app.include_router(project_work_router(runtime,project_store));app.include_router(project_autonomy_router(runtime,project_store));app.include_router(work_order_detail_router(runtime,project_store));app.include_router(global_work_router(runtime,project_store));app.include_router(work_attention_router(runtime,project_store));app.include_router(agent_workforce_pwa_router(runtime));app.include_router(agent_work_requests_router(runtime));app.include_router(multimodal_world_router(runtime));app.include_router(continuity_sync_router(runtime));app.include_router(owner_product_router(runtime));app.include_router(owner_intelligence_router(runtime));app.include_router(owner_engineering_router(runtime));app.include_router(owner_release_router(runtime));app.include_router(portable_intelligence_router(runtime));app.include_router(owner_intelligence_ui_router());app.include_router(owner_engineering_ui_router());app.include_router(owner_release_ui_router());app.include_router(portable_intelligence_ui_router());app.include_router(self_improvement_ui_router());app.include_router(workflow_budget_router(runtime));app.include_router(workflow_budget_ui_router());app.include_router(connector_router(runtime));app.include_router(connector_oauth_callback_router());app.include_router(connector_ui_router());app.include_router(capability_console_router(runtime));app.include_router(capability_forge_router(runtime));app.include_router(capability_forge_v3_router(runtime));app.include_router(capability_forge_oauth_callback_router(runtime));app.include_router(capability_forge_ui_router());app.include_router(capability_forge_v3_ui_router());app.router.lifespan_context=lifespan
