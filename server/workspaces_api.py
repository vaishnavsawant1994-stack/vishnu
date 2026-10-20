from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field

from security.request_context import current_trusted_request
from workspaces.store import WorkspaceStore


class WorkspaceCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=4000)
    workspace_type: str = Field(default='personal', pattern='^(personal|business|development|research|creative|learning|other)$')


class WorkspaceUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    workspace_type: str | None = Field(default=None, pattern='^(personal|business|development|research|creative|learning|other)$')
    is_pinned: bool | None = None
    status: str | None = Field(default=None, pattern='^(active|archived)$')


class StudioViewBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    layout: dict = Field(default_factory=dict)


class WorkspaceResourceBody(BaseModel):
    resource_type: str = Field(pattern='^project$')
    resource_id: str = Field(min_length=1, max_length=100)


def workspaces_router(runtime, store: WorkspaceStore):
    router = APIRouter(prefix='/iphone/api/workspaces', tags=['workspaces'])
    registry = runtime['device_registry']

    def authenticate(device_id: str | None, token: str | None, *, write: bool = False) -> str:
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, 'This browser is not trusted or its session was revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, 'ai:chat'):
            raise HTTPException(403, 'This device is not permitted to access Workspaces')
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, 'A current trusted owner session is required to change Workspace data')
        # This runtime currently has one canonical owner. The owner_id column
        # keeps every query partitioned and supports future identity migration.
        return 'owner'

    def owned(owner_id: str, workspace_id: str):
        workspace = store.get(owner_id, workspace_id)
        if workspace is None:
            raise HTTPException(404, 'Workspace not found')
        return workspace

    def workspace_document(owner_id: str, workspace_id: str):
        workspace = owned(owner_id, workspace_id)
        projects = runtime.get('base_project_store')
        linked = []
        if projects is not None:
            for item in store.linked_projects(owner_id, workspace_id):
                project = projects.get(item['resource_id'])
                if project is not None:
                    linked.append({'project': project, 'linked_at': item['created_at']})
        workspace['linked_project_count'] = len(linked)
        return {'workspace': workspace, 'projects': linked}

    @router.get('')
    def list_workspaces(q: str = Query(default='', max_length=120),
                        workspace_type: str = Query(default='all', pattern='^(all|personal|business|development|research|creative|learning|other)$'),
                        status: str = Query(default='active', pattern='^(all|active|archived)$'),
                        sort: str = Query(default='recent', pattern='^(recent|name|opened|attention)$'),
                        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token)
        rows = store.list(owner_id, query=q, workspace_type=workspace_type, status=status, sort=sort)
        return {'workspaces': rows, 'counts': {
            'all': len(store.list(owner_id, status='active')),
            'pinned': sum(item['is_pinned'] for item in store.list(owner_id, status='active')),
            'active': len(store.list(owner_id, status='active')),
            'archived': len(store.list(owner_id, status='archived')),
            'types': {kind: len(store.list(owner_id, workspace_type=kind, status='active'))
                      for kind in ('personal','business','development','research')},
        }}

    @router.post('', status_code=201)
    def create_workspace(body: WorkspaceCreateBody,
                         pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        try:
            return {'workspace': store.create(owner_id, **body.model_dump())}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post('/reference-demo', status_code=201)
    def create_reference_demo(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        return {'workspace': store.create_reference_fixture(owner_id), 'notice': 'Illustrative reference demo; not a real organization or customer record.'}

    @router.get('/{workspace_id}')
    def get_workspace(workspace_id: str,
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token)
        return workspace_document(owner_id, workspace_id)

    @router.patch('/{workspace_id}')
    def update_workspace(workspace_id: str, body: WorkspaceUpdateBody,
                         pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        try:
            value = store.update(owner_id, workspace_id, body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if value is None:
            raise HTTPException(404, 'Workspace not found')
        return {'workspace': value}

    @router.post('/{workspace_id}/open')
    def open_workspace(workspace_id: str,
                       pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        value = store.touch_opened(owner_id, workspace_id)
        if value is None:
            raise HTTPException(404, 'Workspace not found or archived')
        return workspace_document(owner_id, workspace_id)

    @router.post('/{workspace_id}/resources', status_code=201)
    def link_workspace_resource(workspace_id: str, body: WorkspaceResourceBody,
                                pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        owned(owner_id, workspace_id)
        projects = runtime.get('base_project_store')
        project = projects.get(body.resource_id) if projects is not None else None
        if body.resource_type == 'project' and project is None:
            raise HTTPException(404, 'Canonical Project not found')
        try:
            store.link_project(owner_id, workspace_id, body.resource_id)
        except LookupError as exc:
            raise HTTPException(404, 'Workspace not found') from exc
        return workspace_document(owner_id, workspace_id)

    @router.delete('/{workspace_id}/resources/projects/{project_id}')
    def unlink_workspace_project(workspace_id: str, project_id: str,
                                 pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        owned(owner_id, workspace_id)
        store.unlink_project(owner_id, workspace_id, project_id)
        return workspace_document(owner_id, workspace_id)

    @router.get('/{workspace_id}/studio/views')
    def list_studio_views(workspace_id: str,
                          pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token)
        owned(owner_id, workspace_id)
        return {'views': store.list_studio_views(owner_id, workspace_id)}

    @router.put('/{workspace_id}/studio/views')
    def save_studio_view(workspace_id: str, body: StudioViewBody,
                         pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        owner_id = authenticate(pa_device, pa_token, write=True)
        try:
            view = store.save_studio_view(owner_id, workspace_id, name=body.name, layout=body.layout)
        except LookupError as exc:
            raise HTTPException(404, 'Workspace not found') from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'view': view}

    return router
