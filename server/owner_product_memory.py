from __future__ import annotations

import json

from fastapi import APIRouter, Cookie, HTTPException

from memory.second_brain import MemoryCandidate
from server.owner_product_schemas import MemoryCreateBody, MemoryPreferencesBody, MemoryUpdateBody, RetentionBody


def create_owner_memory_router(
    runtime,
    *,
    authenticate,
    audit,
    can_read_sensitive_memory,
    filter_memories,
    filter_tree,
):
    router = APIRouter(prefix='/iphone/api', tags=['owner-product'])
    memory = runtime['memory']
    second_brain = runtime['second_brain']

    @router.get('/memory')
    def memory_list(
        q: str = '',
        limit: int = 100,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        rows = memory.temporal_search(q=q.strip(), limit=min(limit, 100))
        return {'memories': filter_memories(rows, device_id)}

    @router.get('/memory/preferences')
    def memory_preferences_get(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'memory:read')
        return memory.preferences()

    @router.patch('/memory/preferences')
    def memory_preferences_update(body: MemoryPreferencesBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        changes = body.model_dump(exclude_none=True)
        if not changes:
            raise HTTPException(422, 'Provide at least one memory preference')
        result = memory.update_preferences(**changes)
        audit('memory.preferences.updated', device_id=device_id, preferences=changes)
        return result

    @router.get('/memory/removed')
    def memory_removed(limit: int = 100, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        return {'memories': filter_memories(memory.recently_removed(limit), device_id)}

    @router.post('/memory/{memory_id}/restore')
    def memory_restore(memory_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        existing = memory.get(memory_id, include_removed=True)
        if not existing or not filter_memories([existing], device_id):
            raise HTTPException(404, 'Removed memory not found')
        if not memory.restore(memory_id):
            raise HTTPException(404, 'Removed memory not found')
        audit('memory.restored', device_id=device_id, memory_id=memory_id)
        return {'ok': True, 'memory': second_brain.memory_detail(memory_id)}

    @router.delete('/memory/{memory_id}/permanent')
    def memory_permanent_delete(memory_id: str, confirm: bool = False, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        if not confirm:
            raise HTTPException(409, 'Permanent deletion requires confirm=true')
        existing = memory.get(memory_id, include_removed=True)
        if not existing or not filter_memories([existing], device_id):
            raise HTTPException(404, 'Memory not found')
        if not second_brain.delete(memory_id):
            raise HTTPException(404, 'Memory not found')
        audit('memory.permanently_deleted', device_id=device_id, memory_id=memory_id)
        return {'ok': True, 'memory_id': memory_id}

    @router.get('/memory/graph')
    def memory_graph(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        graph = second_brain.graph()
        nodes = filter_memories(graph.get('nodes', []), device_id)
        ids = {row['id'] for row in nodes}
        return {'nodes': nodes, 'edges': [edge for edge in graph.get('edges', []) if edge['source_id'] in ids and edge['target_id'] in ids]}

    @router.get('/memory/tree')
    def memory_tree(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        return {'roots': filter_tree(memory.tree(), device_id)}

    @router.get('/memory/export')
    def memory_export(
        include_sensitive: bool = True,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        if include_sensitive and not can_read_sensitive_memory(device_id):
            raise HTTPException(403, 'This device cannot export sensitive memory')
        audit('memory.exported', device_id=device_id, include_sensitive=include_sensitive)
        return memory.export(include_sensitive=include_sensitive)

    @router.post('/memory/retention')
    def memory_retention(
        body: RetentionBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        if body.sensitivity in {'sensitive', 'secret'} and not can_read_sensitive_memory(device_id):
            raise HTTPException(403, 'This device cannot create sensitive memory')
        result = second_brain.apply_retention(
            older_than_days=body.older_than_days,
            sensitivity=body.sensitivity,
            dry_run=not body.confirm_delete,
        )
        audit('memory.retention', device_id=device_id, matched=result['matched'], deleted=body.confirm_delete)
        return result

    @router.post('/memory')
    def memory_create(
        body: MemoryCreateBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        if body.sensitivity == 'never_store':
            raise HTTPException(409, 'NEVER_STORE content cannot be written to durable memory')
        if body.sensitivity in {'sensitive', 'secret'} and not can_read_sensitive_memory(device_id):
            raise HTTPException(403, 'This device cannot create sensitive memory')
        if body.scope == 'project':
            project_store = runtime.get('project_store')
            if not body.project_id or project_store is None or not project_store.get(body.project_id):
                raise HTTPException(404, 'Authorized project not found')
        elif body.project_id:
            raise HTTPException(422, 'Personal memories cannot include a project ID')
        memory_id = second_brain.remember(MemoryCandidate(
            type=body.type,
            subject=body.subject,
            content=body.content,
            confidence=body.confidence,
            source=body.source,
            verified=body.verified,
            tags=body.tags,
            importance=body.importance,
            sensitivity=body.sensitivity,
            occurred_at=body.occurred_at,
            metadata={'scope': body.scope, **({'project_id': body.project_id} if body.project_id else {})},
        ))
        if body.parent_id:
            memory.update_memory(memory_id, parent_id=body.parent_id)
        audit('memory.created', device_id=device_id, memory_id=memory_id)
        return second_brain.memory_detail(memory_id)

    @router.get('/memory/{memory_id}')
    def memory_detail(memory_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        detail = second_brain.memory_detail(memory_id)
        if not detail or not filter_memories([detail], device_id):
            raise HTTPException(404, 'Memory not found')
        return detail

    @router.patch('/memory/{memory_id}')
    def memory_update(
        memory_id: str,
        body: MemoryUpdateBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        existing = memory.get(memory_id)
        if not existing or not filter_memories([existing], device_id):
            raise HTTPException(404, 'Memory not found')
        if body.sensitivity == 'never_store':
            raise HTTPException(409, 'Delete this memory instead of marking durable content NEVER_STORE')
        if body.sensitivity in {'sensitive', 'secret'} and not can_read_sensitive_memory(device_id):
            raise HTTPException(403, 'This device cannot mark memory sensitive')
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        if 'pinned' in changes:
            pinned = bool(changes.pop('pinned'))
            try:
                current_metadata = json.loads(existing.get('metadata_json') or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                current_metadata = {}
            if pinned:
                current_metadata['pinned'] = True
            else:
                current_metadata.pop('pinned', None)
            changes['metadata'] = current_metadata
        if 'scope' in changes or 'project_id' in changes:
            metadata_raw = existing.get('metadata_json') or '{}'
            try:
                metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else dict(metadata_raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata = {}
            scope = changes.pop('scope', metadata.get('scope') or ('project' if metadata.get('project_id') else 'personal'))
            project_id = changes.pop('project_id', metadata.get('project_id'))
            if scope == 'project':
                project_store = runtime.get('project_store')
                if not project_id or project_store is None or not project_store.get(project_id):
                    raise HTTPException(404, 'Authorized project not found')
                metadata.update({'scope': 'project', 'project_id': project_id})
            else:
                metadata.update({'scope': 'personal'})
                metadata.pop('project_id', None)
            changes['metadata'] = metadata
        if not memory.update_memory(memory_id, **changes):
            raise HTTPException(404, 'Memory not found or no supported changes supplied')
        audit('memory.corrected', device_id=device_id, memory_id=memory_id, fields=sorted(changes))
        return second_brain.memory_detail(memory_id)

    @router.delete('/memory/{memory_id}')
    def memory_delete(
        memory_id: str,
        confirm: bool = False,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'memory:write')
        if not confirm:
            raise HTTPException(409, 'Memory deletion requires confirm=true')
        existing = memory.get(memory_id)
        if not existing or not filter_memories([existing], device_id):
            raise HTTPException(404, 'Memory not found')
        if not memory.soft_delete(memory_id):
            raise HTTPException(404, 'Memory not found')
        audit('memory.removed', device_id=device_id, memory_id=memory_id)
        return {'ok': True, 'memory_id': memory_id}
    return router
