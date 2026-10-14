from __future__ import annotations

from types import SimpleNamespace

from core.runtime_composition import compose_vishnu_runtime


def test_runtime_composition_reuses_existing_authorities_and_keeps_domains_separate():
    root_key_store = object()
    vault = SimpleNamespace(root_key_store=root_key_store)
    approvals = object()
    action_audit = object()
    agent_executor = SimpleNamespace(approvals=approvals, action_audit=action_audit)
    memory_audit = object()
    memory = SimpleNamespace(audit=memory_audit)
    tools = object()
    memory_brain = object()
    knowledge_store = object()
    knowledge_authority = object()
    intelligence = object()

    runtime = compose_vishnu_runtime({
        'vault': vault,
        'agent_executor': agent_executor,
        'memory': memory,
        'tools': tools,
        'second_brain': memory_brain,
        'knowledge_store': knowledge_store,
        'knowledge': knowledge_authority,
        'intelligence': intelligence,
    })

    assert runtime.security.root_key_store is root_key_store
    assert runtime.security.secret_vault is vault
    assert runtime.security.approvals is approvals
    assert runtime.security.audit_sinks == (memory_audit, action_audit)
    assert runtime.work.tool_registry is tools
    assert runtime.work.agent_executor is agent_executor
    assert runtime.memory.store is memory
    assert runtime.memory.second_brain is memory_brain
    assert runtime.knowledge.store is knowledge_store
    assert runtime.knowledge.authority is knowledge_authority
    assert runtime.intelligence.engine is intelligence
    assert runtime.memory is not runtime.knowledge


def test_product_runtime_has_no_owner_secret_or_unrestricted_execution_authority():
    runtime = compose_vishnu_runtime({
        'vault': object(),
        'tools': object(),
        'agent_executor': SimpleNamespace(approvals=object()),
    })

    assert runtime.products.manifest_store is None
    assert runtime.products.composer is None
    assert runtime.products.distribution is None
    assert not hasattr(runtime.products, 'secret_vault')
    assert not hasattr(runtime.products, 'root_key_store')
    assert not hasattr(runtime.products, 'tool_registry')
    assert not hasattr(runtime.intelligence, 'tool_registry')
