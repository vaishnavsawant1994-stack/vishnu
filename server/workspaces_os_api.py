"""Owner-scoped Vishnu OS workspace organization and Studio layout.

Organizational references only: ProjectStore, WorkRuntime and other domain
authorities retain ownership of their resources. Nothing executes here.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.sqlite import Migration, connect_sqlite, run_migrations
from security.request_context import current_trusted_request


TEMPLATES = ('blank', 'software', 'product', 'business', 'research', 'creative', '3d', 'personal', 'learning')
KINDS = ('project', 'work', 'conversation', 'agent', 'file', 'knowledge', 'product', 'artifact')
MAX_PANELS = 32


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_v1(con) -> None:
    statements = """
        CREATE TABLE IF NOT EXISTS os_workspaces(
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', template_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', pinned INTEGER NOT NULL DEFAULT 0,
            icon TEXT NOT NULL DEFAULT '', cover TEXT NOT NULL DEFAULT '',
            request_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS os_workspaces_retry
            ON os_workspaces(owner_id, request_id) WHERE request_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS os_workspaces_owner
            ON os_workspaces(owner_id, updated_at);
        CREATE TABLE IF NOT EXISTS os_workspace_links(
            workspace_id TEXT NOT NULL REFERENCES os_workspaces(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, resource_id TEXT NOT NULL,
            PRIMARY KEY(workspace_id,kind,resource_id)
        );
        CREATE TABLE IF NOT EXISTS os_studio_views(
            id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL
            REFERENCES os_workspaces(id) ON DELETE CASCADE,
            name TEXT NOT NULL, layout_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS os_studio_workspace
            ON os_studio_views(workspace_id, updated_at);
    """
    for statement in statements.split(';'):
        if statement.strip():
            con.execute(statement)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    template_id: Literal['blank', 'software', 'product', 'business', 'research', 'creative', '3d', 'personal', 'learning'] = 'blank'
    request_id: str | None = Field(default=None, min_length=8, max_length=128)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal['active', 'paused', 'archived'] | None = None
    pinned: bool | None = None


class WorkspaceLink(BaseModel):
    kind: Literal['project', 'work', 'conversation', 'agent', 'file', 'knowledge', 'product', 'artifact']
    resource_id: str = Field(min_length=1, max_length=128)


class StudioViewBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    layout: dict = Field(default_factory=dict)


class WorkspaceStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = RLock()
        with self._con() as con:
            run_migrations(
                con, component='vishnu_os_workspaces',
                migrations=[Migration(1, 'owner workspaces, links and Studio views', _migrate_v1)],
            )

    def _con(self):
        return connect_sqlite(self.path)

    def _row(self, con, ident: str, owner_id: str):
        row = con.execute(
            'SELECT * FROM os_workspaces WHERE id=? AND owner_id=?',
            (ident, owner_id),
        ).fetchone()
        if row is None:
            raise KeyError(ident)
        return dict(row)

    def _expand(self, con, row):
        row = dict(row)
        row['pinned'] = bool(row['pinned'])
        links = con.execute(
            'SELECT kind,resource_id FROM os_workspace_links WHERE workspace_id=? ORDER BY kind,resource_id',
            (row['id'],),
        ).fetchall()
        row['links'] = [dict(item) for item in links]
        counts = {kind: 0 for kind in KINDS}
        for item in links:
            counts[item['kind']] += 1
        row['linked_counts'] = counts
        return row

    def list(self, owner_id: str):
        with self._con() as con:
            rows = con.execute(
                'SELECT * FROM os_workspaces WHERE owner_id=? ORDER BY pinned DESC,updated_at DESC',
                (owner_id,),
            ).fetchall()
            return [self._expand(con, row) for row in rows]

    def get(self, ident: str, owner_id: str):
        with self._con() as con:
            return self._expand(con, self._row(con, ident, owner_id))

    def create(self, owner_id: str, body: WorkspaceCreate):
        name = body.name.strip()
        if not name:
            raise ValueError('Workspace name is required')
        with self.lock, self._con() as con:
            if body.request_id:
                row = con.execute(
                    'SELECT * FROM os_workspaces WHERE owner_id=? AND request_id=?',
                    (owner_id, body.request_id),
                ).fetchone()
                if row:
                    return self._expand(con, row)
            ident, stamp = str(uuid.uuid4()), _now()
            con.execute(
                '''INSERT INTO os_workspaces
                (id,owner_id,name,description,template_id,request_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)''',
                (ident, owner_id, name, body.description.strip(),
                 body.template_id, body.request_id, stamp, stamp),
            )
            return self._expand(con, self._row(con, ident, owner_id))

    def patch(self, ident: str, owner_id: str, body: WorkspacePatch):
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            return self.get(ident, owner_id)
        if 'name' in changes:
            changes['name'] = changes['name'].strip()
            if not changes['name']:
                raise ValueError('Workspace name is required')
        if 'pinned' in changes:
            changes['pinned'] = int(changes['pinned'])
        changes['updated_at'] = _now()
        with self.lock, self._con() as con:
            self._row(con, ident, owner_id)
            con.execute(
                'UPDATE os_workspaces SET ' + ','.join(f'{name}=?' for name in changes) + ' WHERE id=?',
                (*changes.values(), ident),
            )
        return self.get(ident, owner_id)

    def link(self, ident: str, owner_id: str, kind: str, resource_id: str, remove=False):
        with self.lock, self._con() as con:
            self._row(con, ident, owner_id)
            if remove:
                con.execute(
                    'DELETE FROM os_workspace_links WHERE workspace_id=? AND kind=? AND resource_id=?',
                    (ident, kind, resource_id),
                )
            else:
                con.execute(
                    'INSERT OR IGNORE INTO os_workspace_links VALUES(?,?,?)',
                    (ident, kind, resource_id),
                )
            con.execute('UPDATE os_workspaces SET updated_at=? WHERE id=?', (_now(), ident))
        return self.get(ident, owner_id)

    def views(self, ident: str, owner_id: str):
        with self._con() as con:
            self._row(con, ident, owner_id)
            rows = con.execute(
                'SELECT * FROM os_studio_views WHERE workspace_id=? ORDER BY updated_at DESC',
                (ident,),
            ).fetchall()
            return [{**dict(row), 'layout': json.loads(row['layout_json'])} for row in rows]

    def save_view(self, ident: str, owner_id: str, body: StudioViewBody, view_id: str | None = None):
        layout = body.layout
        panels = layout.get('panels', [])
        if not isinstance(panels, list) or len(panels) > MAX_PANELS:
            raise ValueError('Studio accepts at most 32 panels')
        if not all(isinstance(panel, dict) and
                   str(panel.get('kind', '')) in KINDS + ('note', 'diagram', 'code', 'image', '3d_preview') and
                   len(str(panel.get('resource_id', ''))) <= 128
                   for panel in panels):
            raise ValueError('Invalid panel placement')
        payload = json.dumps(layout, separators=(',', ':'))
        if len(payload) > 64000:
            raise ValueError('Studio layout exceeds size limit')
        with self.lock, self._con() as con:
            self._row(con, ident, owner_id)
            stamp = _now()
            if view_id:
                existing = con.execute(
                    'SELECT id FROM os_studio_views WHERE id=? AND workspace_id=?',
                    (view_id, ident),
                ).fetchone()
                if not existing:
                    raise KeyError(view_id)
                con.execute(
                    'UPDATE os_studio_views SET name=?,layout_json=?,updated_at=? WHERE id=?',
                    (body.name.strip(), payload, stamp, view_id),
                )
                target = view_id
            else:
                target = str(uuid.uuid4())
                con.execute(
                    'INSERT INTO os_studio_views VALUES(?,?,?,?,?,?)',
                    (target, ident, body.name.strip(), payload, stamp, stamp),
                )
            row = con.execute('SELECT * FROM os_studio_views WHERE id=?', (target,)).fetchone()
            return {**dict(row), 'layout': json.loads(row['layout_json'])}


def workspaces_os_router(runtime: dict, store: WorkspaceStore) -> APIRouter:
    router = APIRouter(prefix='/iphone/api/os/workspaces', tags=['vishnu-os-workspaces'])
    registry = runtime['device_registry']

    def owner_id() -> str:
        ctx = current_trusted_request()
        if ctx is None or not registry.is_active(ctx.device_id):
            raise HTTPException(401, 'Trusted owner session required')
        if hasattr(registry, 'authorize') and not registry.authorize(ctx.device_id, 'ai:chat'):
            raise HTTPException(403, 'Device lacks permission')
        return 'owner'  # Existing Vishnu single-owner authority.

    def read(call):
        try:
            return call()
        except KeyError as exc:
            raise HTTPException(404, 'Workspace or view not found') from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get('')
    def list_workspaces():
        return {'workspaces': store.list(owner_id()), 'templates': TEMPLATES}

    @router.post('', status_code=201)
    def create_workspace(body: WorkspaceCreate):
        identity = owner_id()
        return {'workspace': read(lambda: store.create(identity, body))}

    @router.get('/{workspace_id}')
    def workspace_detail(workspace_id: str):
        identity = owner_id()
        return {'workspace': read(lambda: store.get(workspace_id, identity))}

    @router.patch('/{workspace_id}')
    def update_workspace(workspace_id: str, body: WorkspacePatch):
        identity = owner_id()
        return {'workspace': read(lambda: store.patch(workspace_id, identity, body))}

    @router.post('/{workspace_id}/links')
    def add_link(workspace_id: str, body: WorkspaceLink):
        identity = owner_id()
        if body.kind == 'project':
            project_store = runtime.get('project_store')
            if project_store is None or project_store.get(body.resource_id) is None:
                raise HTTPException(404, 'Project not found')
        else:
            raise HTTPException(409, 'Linking this resource type is not qualified yet')
        return {'workspace': read(lambda: store.link(workspace_id, identity, body.kind, body.resource_id))}

    @router.delete('/{workspace_id}/links/{kind}/{resource_id}')
    def remove_link(workspace_id: str, kind: str, resource_id: str):
        identity = owner_id()
        if kind not in KINDS:
            raise HTTPException(422, 'Unknown resource type')
        return {'workspace': read(lambda: store.link(workspace_id, identity, kind, resource_id, remove=True))}

    @router.get('/{workspace_id}/summary')
    def workspace_summary(workspace_id: str):
        identity = owner_id()
        workspace = read(lambda: store.get(workspace_id, identity))
        project_store = runtime.get('project_store')
        projects = []
        if project_store:
            for link in workspace['links']:
                if link['kind'] == 'project':
                    project = project_store.get(link['resource_id'])
                    if project and project.get('status') != 'archived':
                        projects.append({
                            'id': project['id'], 'name': project['name'],
                            'description': project.get('description', ''),
                            'status': project.get('status', 'active'),
                            'task_count': project.get('task_count', len(project.get('tasks', []))),
                        })
        return {'workspace': workspace, 'projects': projects}

    @router.get('/{workspace_id}/studio/views')
    def list_views(workspace_id: str):
        identity = owner_id()
        return {'views': read(lambda: store.views(workspace_id, identity))}

    @router.post('/{workspace_id}/studio/views', status_code=201)
    def create_view(workspace_id: str, body: StudioViewBody):
        identity = owner_id()
        return {'view': read(lambda: store.save_view(workspace_id, identity, body))}

    @router.put('/{workspace_id}/studio/views/{view_id}')
    def update_view(workspace_id: str, view_id: str, body: StudioViewBody):
        identity = owner_id()
        return {'view': read(lambda: store.save_view(workspace_id, identity, body, view_id))}

    return router
