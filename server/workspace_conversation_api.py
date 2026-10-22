"""P2-02D: owner-scoped Workspace conversation adapter.

WorkspaceStore owns workspace identity and Project links; ContinuityService owns
the single conversation ledger. No third Workspace or chat database is created.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field

from security.request_context import current_trusted_request


class WorkspaceChatCreate(BaseModel):
    title: str = Field(default='New Workspace Conversation', min_length=1, max_length=120)
    request_id: str | None = Field(default=None, min_length=8, max_length=80)


def workspace_conversation_router(runtime, store):
    router = APIRouter(prefix='/iphone/api/workspaces', tags=['workspace-conversations'])
    registry = runtime['device_registry']
    continuity = runtime.get('continuity')
    projects = runtime.get('base_project_store')

    def owner(pa_device, pa_token, *, write=False):
        ctx = current_trusted_request()
        if not pa_device or not pa_token or not registry.authenticate(pa_device, pa_token):
            raise HTTPException(401, 'Trusted owner session is required')
        if ctx is None or ctx.device_id != pa_device:
            raise HTTPException(401, 'Current trusted owner session is required')
        if hasattr(registry, 'is_active') and not registry.is_active(pa_device):
            raise HTTPException(401, 'Trusted device was revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(pa_device, 'ai:chat'):
            raise HTTPException(403, 'Device lacks Workspace access permission')
        return 'owner'

    def workspace_or_404(owner_id, workspace_id):
        workspace = store.get(owner_id, workspace_id)
        if not workspace:
            raise HTTPException(404, 'Workspace not found')
        return workspace

    def continuity_or_503():
        if continuity is None:
            raise HTTPException(503, 'Canonical conversation service is unavailable')
        return continuity

    def scoped_thread(owner_id, workspace_id, conversation_id):
        workspace_or_404(owner_id, workspace_id)
        service = continuity_or_503()
        thread = service.thread(conversation_id)
        meta = (thread or {}).get('context') or {}
        if (not thread or thread.get('closed_at')
            or meta.get('conversation_kind') != 'workspace'
            or meta.get('workspace_id') != workspace_id
            or meta.get('owner_id') != owner_id):
            raise HTTPException(404, 'Workspace conversation not found')
        return thread

    @router.get('/{workspace_id}/summary')
    def summary(workspace_id: str,
                pa_device: str | None = Cookie(default=None),
                pa_token: str | None = Cookie(default=None)):
        owner_id = owner(pa_device, pa_token)
        workspace = workspace_or_404(owner_id, workspace_id)
        active_projects = []
        if projects is not None:
            for link in store.linked_projects(owner_id, workspace_id):
                project = projects.get(link['resource_id'])
                if project and project.get('status') != 'archived':
                    active_projects.append(project)
        active_tasks = sum(1 for p in active_projects for task in p.get('tasks', [])
                           if task.get('status') in {'planned', 'in_progress', 'blocked', 'paused', 'needs_review'})
        return {'workspace': workspace,
                'projects': [
                    {'id': p['id'], 'name': p['name'], 'status': p.get('status'),
                     'task_count': len(p.get('tasks', [])),
                     'done_count': sum(t.get('status') == 'done' for t in p.get('tasks', [])),
                     'file_count': len(p.get('files', []))}
                    for p in active_projects],
                'counts': {'projects': len(active_projects), 'active_tasks': active_tasks,
                           'files': sum(len(p.get('files', [])) for p in active_projects),
                           'members': None, 'agents': None},
                'members_supported': False, 'workspace_agent_assignments_supported': False}

    @router.get('/{workspace_id}/conversations')
    def list_chats(workspace_id: str,
                   q: str = Query(default='', max_length=120),
                   limit: int = Query(default=60, ge=1, le=100),
                   pa_device: str | None = Cookie(default=None),
                   pa_token: str | None = Cookie(default=None)):
        owner_id = owner(pa_device, pa_token)
        workspace_or_404(owner_id, workspace_id)
        return {'workspace_id': workspace_id,
                'conversations': continuity_or_503().list_threads(
                    q, workspace_id=workspace_id, limit=limit)}

    @router.post('/{workspace_id}/conversations', status_code=201)
    def new_chat(workspace_id: str, body: WorkspaceChatCreate,
                 pa_device: str | None = Cookie(default=None),
                 pa_token: str | None = Cookie(default=None)):
        owner_id = owner(pa_device, pa_token, write=True)
        workspace = workspace_or_404(owner_id, workspace_id)
        if workspace['status'] != 'active':
            raise HTTPException(409, 'Archived Workspace must be restored before creating chats')
        service = continuity_or_503()
        with service.lock:
            if body.request_id:
                for row in service.list_threads(workspace_id=workspace_id, include_closed=True, limit=200):
                    if (row.get('context') or {}).get('create_request_id') == body.request_id:
                        return {'workspace_id': workspace_id,
                                'conversation': service.thread(row['id'])}
            ident = service.create_thread(body.title.strip(), device_id=pa_device,
                                          context={'conversation_kind': 'workspace',
                                                   'workspace_id': workspace_id,
                                                   'owner_id': owner_id,
                                                   'create_request_id': body.request_id})
        if runtime.get('events'):
            runtime['events'].emit('workspace.conversation.created', workspace_id=workspace_id,
                                   conversation_id=ident, device_id=pa_device)
        return {'workspace_id': workspace_id, 'conversation': service.thread(ident)}

    @router.get('/{workspace_id}/conversations/{conversation_id}')
    def get_chat(workspace_id: str, conversation_id: str,
                 after_sequence: int = Query(default=0, ge=0),
                 limit: int = Query(default=200, ge=1, le=500),
                 pa_device: str | None = Cookie(default=None),
                 pa_token: str | None = Cookie(default=None)):
        owner_id = owner(pa_device, pa_token)
        thread = scoped_thread(owner_id, workspace_id, conversation_id)
        return {'workspace_id': workspace_id, 'conversation': thread,
                'events': continuity_or_503().events_for_thread(
                    thread['id'], after_sequence=after_sequence, limit=limit)}

    return router
