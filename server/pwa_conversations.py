from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from security.request_context import current_trusted_request


class HistoryMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=12)


class HistoryOrganizeBody(BaseModel):
    kind: Literal['personal', 'work', 'project', 'workspace']
    target_id: str | None = Field(default=None, max_length=80)
    confirm: Literal[True]


def pwa_conversation_router(runtime):
    router = APIRouter(prefix='/iphone/api/conversations', tags=['iphone-pwa-conversations'])
    continuity = runtime['continuity']

    def require_session():
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, {
                'code': 'session_expired',
                'message': 'This browser session is missing, expired, or revoked.',
            })
        registry = runtime.get('device_registry')
        if registry is not None:
            if not registry.is_active(context.device_id):
                raise HTTPException(401, 'Trusted device is revoked')
            if hasattr(registry, 'authorize') and not registry.authorize(context.device_id, 'ai:chat'):
                raise HTTPException(403, 'This device cannot access conversations')
        return context

    def existing(conversation_id):
        thread = continuity.thread(conversation_id)
        if not thread:
            raise HTTPException(404, 'Conversation not found')
        return thread

    def emit(event, **payload):
        events = runtime.get('events')
        if events is not None:
            events.emit(event, **payload)

    @router.get('/history/search')
    def history_search(
        q: str = Query(default='', max_length=160),
        kind: Literal['all', 'personal', 'work', 'project', 'workspace'] = 'all',
        status: Literal['active', 'archived', 'all'] = 'active',
        pinned: bool = False,
        tag: str = Query(default='', max_length=32),
        project_id: str = Query(default='', max_length=80),
        workspace_id: str = Query(default='', max_length=80),
        since: date | None = None, until: date | None = None,
        cursor_time: str = Query(default='', max_length=64),
        cursor_id: str = Query(default='', max_length=80),
        limit: int = Query(default=40, ge=1, le=100),
    ):
        require_session()
        if bool(cursor_time) != bool(cursor_id):
            raise HTTPException(422, 'Cursor must include both fields')
        if since and until and since > until:
            raise HTTPException(422, 'Invalid date range')
        if project_id:
            project_store = runtime.get('base_project_store') or runtime.get('project_store')
            if not project_store or not project_store.get(project_id):
                raise HTTPException(404, 'Project not found')
        if workspace_id:
            store = runtime.get('workspace_store')
            if not store or not store.get('owner', workspace_id):
                raise HTTPException(404, 'Workspace not found')
        return continuity.history_page(
            query=q, kind=kind, status=status, pinned=pinned, tag=tag,
            project_id=project_id, workspace_id=workspace_id,
            since=str(since) if since else '', until=str(until) if until else '',
            cursor_time=cursor_time, cursor_id=cursor_id, limit=limit,
        )

    @router.patch('/{conversation_id}/metadata')
    def history_metadata(conversation_id: str, body: HistoryMetadataUpdate):
        owner = require_session()
        existing(conversation_id)
        if not body.model_fields_set:
            raise HTTPException(422, 'No fields to update')
        try:
            thread = continuity.update_history_metadata(
                conversation_id, **body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        emit('conversation.metadata.updated', conversation_id=conversation_id, device_id=owner.device_id)
        return {'conversation': thread}

    @router.post('/{conversation_id}/restore')
    def history_restore(conversation_id: str):
        owner = require_session()
        thread = existing(conversation_id)
        if not thread.get('closed_at'):
            return {'conversation': thread, 'status': 'already_active'}
        continuity.restore_thread(conversation_id)
        emit('conversation.restored', conversation_id=conversation_id, device_id=owner.device_id)
        return {'conversation': continuity.thread(conversation_id), 'status': 'restored'}

    @router.post('/{conversation_id}/organize')
    def history_organize(conversation_id: str, body: HistoryOrganizeBody):
        owner = require_session()
        old = existing(conversation_id)
        if old.get('closed_at'):
            raise HTTPException(409, 'Restore conversation first')
        kind, target = body.kind, body.target_id
        if kind == 'project':
            projects = runtime.get('base_project_store') or runtime.get('project_store')
            project = projects.get(target) if projects and target else None
            if not project or project.get('status') == 'archived':
                raise HTTPException(404, 'Target Project unavailable')
        elif kind == 'workspace':
            workspaces = runtime.get('workspace_store')
            workspace = workspaces.get('owner', target) if workspaces and target else None
            if not workspace or workspace.get('status') != 'active':
                raise HTTPException(404, 'Target Workspace unavailable')
        elif target:
            raise HTTPException(422, 'No target permitted for this conversation type')
        # An explicit owner decision updates the one transcript's organization, not a copy.
        try:
            thread = continuity.organize_thread(conversation_id, kind=kind, target_id=target)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        emit('conversation.context.changed', conversation_id=conversation_id,
             context_type=kind, device_id=owner.device_id)
        return {'conversation': thread}

    @router.get('/{conversation_id}/related')
    def history_related(conversation_id: str):
        require_session()
        thread = existing(conversation_id)
        ctx = thread.get('context') or {}
        result = {'conversation_id': conversation_id, 'projects': [], 'workspaces': [],
                  'tasks': [], 'files': [], 'coverage': {
                    'file_links': False, 'conversation_task_links': False}}
        p_id = ctx.get('project_id') or ctx.get('work_project_id')
        if p_id:
            projects = runtime.get('base_project_store') or runtime.get('project_store')
            project = projects.get(p_id) if projects else None
            if project and project.get('status') != 'archived':
                result['projects'].append({'id': project['id'], 'name': project['name'],
                                           'status': project.get('status')})
        w_id = ctx.get('workspace_id')
        if w_id:
            workspaces = runtime.get('workspace_store')
            workspace = workspaces.get('owner', w_id) if workspaces else None
            if workspace and workspace.get('status') == 'active':
                result['workspaces'].append({'id': workspace['id'],
                                             'name': workspace['name']})
        return result

    @router.post('/{conversation_id}/archive')
    def archive(conversation_id: str):
        require_session()
        thread = continuity.thread(conversation_id)
        if not thread:
            raise HTTPException(404, 'Conversation not found')
        if thread.get('closed_at'):
            return {'ok': True, 'conversation_id': conversation_id, 'status': 'already_archived'}
        continuity.archive_thread(conversation_id)
        return {'ok': True, 'conversation_id': conversation_id, 'status': 'archived'}

    @router.delete('/{conversation_id}')
    def delete(conversation_id: str):
        require_session()
        if not continuity.delete_thread(conversation_id):
            raise HTTPException(404, 'Conversation not found')
        return {'ok': True, 'conversation_id': conversation_id, 'status': 'deleted'}

    @router.delete('/')
    def clear_history(confirm: bool = False):
        context = require_session()
        if not confirm:
            raise HTTPException(422, 'Explicit conversation-history deletion confirmation is required')
        turn_runtime = runtime.get('turn_runtime')
        if turn_runtime is not None and hasattr(turn_runtime, 'clear_conversation_history'):
            try:
                turn_runtime.clear_conversation_history()
            except RuntimeError as exc:
                raise HTTPException(409, str(exc)) from exc
        count = continuity.delete_all_threads()
        memory = runtime.get('memory')
        if memory is not None and hasattr(memory, 'clear_conversation_messages'):
            memory.clear_conversation_messages()
        if memory is not None and hasattr(memory, 'audit'):
            memory.audit('privacy', 'chat_history.cleared', {'device_id': context.device_id, 'deleted_count': count})
        return {'ok': True, 'deleted_count': count}

    @router.get('/{conversation_id}/export')
    def export(conversation_id: str):
        require_session()
        try:
            bundle = continuity.export_thread(conversation_id)
        except KeyError as exc:
            raise HTTPException(404, 'Conversation not found') from exc
        return JSONResponse(
            content=bundle,
            headers={
                'Content-Disposition': f'attachment; filename="personal-ai-conversation-{conversation_id}.json"'
            },
        )

    return router
