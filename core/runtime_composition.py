from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SecurityRuntime:
    root_key_store: Any
    secret_vault: Any
    approvals: Any
    owner_access: Any
    audit_sinks: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class IntelligenceRuntime:
    router: Any
    engine: Any
    settings: Any
    performance: Any
    training: Any
    portable: Any


@dataclass(frozen=True, slots=True)
class MemoryRuntime:
    store: Any
    second_brain: Any
    vector_store: Any


@dataclass(frozen=True, slots=True)
class KnowledgeRuntime:
    store: Any
    authority: Any


@dataclass(frozen=True, slots=True)
class WorkRuntime:
    tool_registry: Any
    agent_executor: Any
    turn_runtime: Any
    automation_engine: Any
    dispatcher: Any
    canonical_work_store: Any
    automation_bridge: Any
    workforce: Any
    worker_intelligence: Any


@dataclass(frozen=True, slots=True)
class DeviceRuntime:
    registry: Any
    gateway: Any
    continuity: Any
    sensorium_lab: Any
    live_work: Any
    desktop: Any
    mobile: Any


@dataclass(frozen=True, slots=True)
class ProductRuntime:
    """Safe product composition boundary; owner security material is excluded."""

    manifest_store: Any = None
    composer: Any = None
    distribution: Any = None
    runtime: Any = None


@dataclass(frozen=True, slots=True)
class EngineeringRuntime:
    engineering: Any
    executor: Any
    finalizer: Any
    code_body: Any
    body_adoption: Any
    evolution: Any
    evolution_handoff: Any


@dataclass(frozen=True, slots=True)
class VishnuRuntime:
    """Typed view of the existing canonical services composed by the app."""

    security: SecurityRuntime
    intelligence: IntelligenceRuntime
    memory: MemoryRuntime
    knowledge: KnowledgeRuntime
    work: WorkRuntime
    devices: DeviceRuntime
    products: ProductRuntime
    engineering: EngineeringRuntime


def compose_vishnu_runtime(services: Mapping[str, Any]) -> VishnuRuntime:
    """Group existing service instances without constructing new authorities."""
    vault = services.get('vault')
    agent_executor = services.get('agent_executor')
    memory_store = services.get('memory')

    return VishnuRuntime(
        security=SecurityRuntime(
            root_key_store=getattr(vault, 'root_key_store', None),
            secret_vault=vault,
            approvals=getattr(agent_executor, 'approvals', None),
            owner_access=services.get('owner_access'),
            audit_sinks=tuple(
                sink for sink in (
                    getattr(memory_store, 'audit', None),
                    getattr(agent_executor, 'action_audit', None),
                ) if sink is not None
            ),
        ),
        intelligence=IntelligenceRuntime(
            router=services.get('model_router'),
            engine=services.get('intelligence'),
            settings=services.get('intelligence_settings'),
            performance=services.get('model_performance'),
            training=services.get('training_coordinator'),
            portable=services.get('portable_intelligence'),
        ),
        memory=MemoryRuntime(
            store=memory_store,
            second_brain=services.get('second_brain'),
            vector_store=services.get('vector_store'),
        ),
        knowledge=KnowledgeRuntime(
            store=services.get('knowledge_store'),
            authority=services.get('knowledge'),
        ),
        work=WorkRuntime(
            tool_registry=services.get('tools'),
            agent_executor=agent_executor,
            turn_runtime=services.get('turn_runtime'),
            automation_engine=services.get('automations'),
            dispatcher=services.get('work_dispatcher'),
            canonical_work_store=services.get('canonical_work_store'),
            automation_bridge=services.get('automation_work_bridge'),
            workforce=services.get('agent_workforce'),
            worker_intelligence=services.get('worker_intelligence'),
        ),
        devices=DeviceRuntime(
            registry=services.get('device_registry'),
            gateway=services.get('device_gateway'),
            continuity=services.get('continuity'),
            sensorium_lab=services.get('sensorium_lab'),
            live_work=services.get('sensorium_live_work'),
            desktop=services.get('sensorium_desktop'),
            mobile=services.get('sensorium_mobile'),
        ),
        # Product composition receives no SecretVault, RootKeyStore, or owner
        # credential fields. Product-specific services can be added explicitly.
        products=ProductRuntime(),
        engineering=EngineeringRuntime(
            engineering=services.get('engineering'),
            executor=services.get('engineering_executor'),
            finalizer=services.get('engineering_finalizer'),
            code_body=services.get('code_body'),
            body_adoption=services.get('body_adoption'),
            evolution=services.get('evolution'),
            evolution_handoff=services.get('evolution_handoff'),
        ),
    )
