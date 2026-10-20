from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from core.sqlite import connect_sqlite, run_migrations, Migration


WORKSPACE_COMPONENT = 'workspace_store'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _schema(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS workspaces(
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
        description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 4000),
        workspace_type TEXT NOT NULL DEFAULT 'personal'
            CHECK(workspace_type IN ('personal','business','development','research','creative','learning','other')),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
        is_pinned INTEGER NOT NULL DEFAULT 0 CHECK(is_pinned IN (0,1)),
        is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0,1)),
        fixture_key TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_opened_at TEXT,
        UNIQUE(owner_id, fixture_key)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_workspaces_owner_updated ON workspaces(owner_id,status,updated_at DESC)')
    con.execute('''CREATE TABLE IF NOT EXISTS workspace_studio_views(
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
        layout_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(owner_id, workspace_id, name)
    )''')


def _resource_links(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS workspace_resource_links(
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        resource_type TEXT NOT NULL CHECK(resource_type IN ('project')),
        resource_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(owner_id,workspace_id,resource_type,resource_id)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_workspace_resources ON workspace_resource_links(owner_id,workspace_id,resource_type)')


class WorkspaceStore:
    """Durable owner-scoped organizational Workspaces, not Project containers."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        con = connect_sqlite(self.path)
        try:
            run_migrations(con, component=WORKSPACE_COMPONENT,
                           migrations=[Migration(1, 'owner-scoped-workspaces-and-studio-views', _schema),
                                       Migration(2, 'canonical-resource-links', _resource_links)])
        finally:
            con.close()

    @contextmanager
    def con(self):
        connection = connect_sqlite(self.path)
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _map(row):
        if row is None:
            return None
        result = dict(row)
        result['is_pinned'] = bool(result['is_pinned'])
        result['is_demo'] = bool(result['is_demo'])
        return result

    def list(self, owner_id: str, *, query: str = '', workspace_type: str = 'all',
             status: str = 'active', sort: str = 'recent') -> list[dict]:
        clauses = ['owner_id=?']
        values: list[object] = [str(owner_id)]
        if status != 'all':
            clauses.append('status=?')
            values.append(status)
        if workspace_type != 'all':
            clauses.append('workspace_type=?')
            values.append(workspace_type)
        if query.strip():
            clauses.append('(name LIKE ? OR description LIKE ?)')
            needle = f'%{query.strip()}%'
            values.extend((needle, needle))
        order = {'recent': 'updated_at DESC', 'name': 'name COLLATE NOCASE ASC',
                 'opened': 'COALESCE(last_opened_at,created_at) DESC', 'attention': 'is_pinned DESC,updated_at DESC'}.get(sort)
        if order is None:
            raise ValueError('Unsupported workspace sort order')
        with self.con() as con:
            rows = con.execute(f'''SELECT w.*,
                (SELECT count(*) FROM workspace_resource_links r WHERE r.owner_id=w.owner_id AND r.workspace_id=w.id AND r.resource_type='project') AS linked_project_count
                FROM workspaces w WHERE {" AND ".join(clauses)} ORDER BY {order},w.id''', values).fetchall()
        return [self._map(row) for row in rows]

    def get(self, owner_id: str, workspace_id: str) -> dict | None:
        with self.con() as con:
            row = con.execute('SELECT * FROM workspaces WHERE owner_id=? AND id=?',
                              (str(owner_id), str(workspace_id))).fetchone()
        return self._map(row)

    def create(self, owner_id: str, *, name: str, description: str = '', workspace_type: str = 'personal',
               is_demo: bool = False, fixture_key: str | None = None) -> dict:
        clean_name = str(name or '').strip()
        clean_description = str(description or '').strip()
        if not clean_name or len(clean_name) > 120:
            raise ValueError('Workspace name must be between 1 and 120 characters')
        if len(clean_description) > 4000:
            raise ValueError('Workspace description must be at most 4000 characters')
        if workspace_type not in {'personal','business','development','research','creative','learning','other'}:
            raise ValueError('Unsupported workspace type')
        workspace_id, stamp = str(uuid.uuid4()), _now()
        with self.lock, self.con() as con:
            con.execute('''INSERT INTO workspaces(id,owner_id,name,description,workspace_type,is_demo,fixture_key,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)''', (workspace_id, str(owner_id), clean_name, clean_description,
                workspace_type, int(is_demo), fixture_key, stamp, stamp))
        return self.get(owner_id, workspace_id)

    def create_reference_fixture(self, owner_id: str) -> dict:
        """Create one explicit reference-only example; never seed it at startup."""
        with self.con() as con:
            existing = con.execute('SELECT id FROM workspaces WHERE owner_id=? AND fixture_key=?',
                                   (str(owner_id), 'screen-17-rudra-reference-v1')).fetchone()
        if existing:
            return self.get(owner_id, existing['id'])
        try:
            return self.create(owner_id, name='Rudra Health Care · Reference Demo',
                description='Illustrative Screen 17–20 reference data only. This is not a real customer, workspace, project, or activity record.',
                workspace_type='business', is_demo=True, fixture_key='screen-17-rudra-reference-v1')
        except sqlite3.IntegrityError:
            with self.con() as con:
                existing = con.execute('SELECT id FROM workspaces WHERE owner_id=? AND fixture_key=?',
                                       (str(owner_id), 'screen-17-rudra-reference-v1')).fetchone()
            if existing:
                return self.get(owner_id, existing['id'])
            raise

    def update(self, owner_id: str, workspace_id: str, fields: dict) -> dict | None:
        allowed = {'name', 'description', 'workspace_type', 'is_pinned', 'status'}
        changes = {key: value for key, value in fields.items() if key in allowed}
        if not changes:
            return self.get(owner_id, workspace_id)
        if 'name' in changes:
            changes['name'] = str(changes['name'] or '').strip()
            if not changes['name'] or len(changes['name']) > 120:
                raise ValueError('Workspace name must be between 1 and 120 characters')
        if 'description' in changes:
            changes['description'] = str(changes['description'] or '').strip()
            if len(changes['description']) > 4000:
                raise ValueError('Workspace description must be at most 4000 characters')
        if 'workspace_type' in changes and changes['workspace_type'] not in {'personal','business','development','research','creative','learning','other'}:
            raise ValueError('Unsupported workspace type')
        if 'status' in changes and changes['status'] not in {'active','archived'}:
            raise ValueError('Unsupported workspace status')
        if 'is_pinned' in changes:
            changes['is_pinned'] = int(bool(changes['is_pinned']))
        changes['updated_at'] = _now()
        assignments = ','.join(f'{key}=?' for key in changes)
        with self.lock, self.con() as con:
            result = con.execute(f'UPDATE workspaces SET {assignments} WHERE owner_id=? AND id=?',
                                 [*changes.values(), str(owner_id), str(workspace_id)])
            if result.rowcount == 0:
                return None
        return self.get(owner_id, workspace_id)

    def touch_opened(self, owner_id: str, workspace_id: str) -> dict | None:
        stamp = _now()
        with self.con() as con:
            result = con.execute('UPDATE workspaces SET last_opened_at=?,updated_at=? WHERE owner_id=? AND id=? AND status="active"',
                                 (stamp, stamp, str(owner_id), str(workspace_id)))
            if result.rowcount == 0:
                return None
        return self.get(owner_id, workspace_id)

    def save_studio_view(self, owner_id: str, workspace_id: str, *, name: str, layout: dict) -> dict:
        if not self.get(owner_id, workspace_id):
            raise LookupError('Workspace not found')
        clean_name = str(name or '').strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError('View name must be between 1 and 80 characters')
        if not isinstance(layout, dict) or set(layout) - {'version', 'panels'} or layout.get('version', 1) != 1:
            raise ValueError('Studio layout must use the supported version 1 view contract')
        panels = layout.get('panels', [])
        if not isinstance(panels, list) or len(panels) > 24:
            raise ValueError('Studio views may contain at most 24 panels')
        allowed_panel_keys = {'type', 'resource_type', 'resource_id', 'title', 'description', 'x', 'y', 'w', 'h', 'collapsed'}
        allowed_panel_types = {'workspace_overview', 'resource_list', 'project', 'work', 'agents', 'files', 'knowledge', 'conversation', 'assistant'}
        allowed_resource_types = {'workspace', 'project', 'work', 'agent', 'file', 'knowledge', 'conversation'}
        clean_panels = []
        for panel in panels:
            if not isinstance(panel, dict) or set(panel) - allowed_panel_keys:
                raise ValueError('Studio panels may store only approved references, labels, geometry and view state')
            if panel.get('type') not in allowed_panel_types:
                raise ValueError('Unsupported Studio panel type')
            if panel.get('resource_type', 'workspace') not in allowed_resource_types:
                raise ValueError('Unsupported Studio resource reference type')
            resource_id = str(panel.get('resource_id', '') or '')
            if len(resource_id) > 100:
                raise ValueError('Studio resource references must be at most 100 characters')
            clean = dict(panel)
            for key in ('title', 'description'):
                if key in clean and (not isinstance(clean[key], str) or len(clean[key]) > (80 if key == 'title' else 200)):
                    raise ValueError('Studio panel labels exceed the permitted size')
            for key in ('x', 'y', 'w', 'h'):
                if key in clean and (not isinstance(clean[key], int) or isinstance(clean[key], bool) or not 0 <= clean[key] <= 10000):
                    raise ValueError('Studio panel geometry must use bounded non-negative integers')
            if 'collapsed' in clean and not isinstance(clean['collapsed'], bool):
                raise ValueError('Studio collapsed state must be boolean')
            clean_panels.append(clean)
        normalized = {'version': 1, 'panels': clean_panels}
        if len(json.dumps(normalized)) > 20000:
            raise ValueError('Studio layout must be under 20 KB')
        # Studio persists references and geometry only; content-bearing keys are rejected.
        stamp, view_id = _now(), str(uuid.uuid4())
        encoded = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        with self.lock, self.con() as con:
            con.execute('''INSERT INTO workspace_studio_views(id,owner_id,workspace_id,name,layout_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner_id,workspace_id,name) DO UPDATE SET layout_json=excluded.layout_json,updated_at=excluded.updated_at''',
                (view_id, str(owner_id), str(workspace_id), clean_name, encoded, stamp, stamp))
            row = con.execute('SELECT * FROM workspace_studio_views WHERE owner_id=? AND workspace_id=? AND name=?',
                              (str(owner_id), str(workspace_id), clean_name)).fetchone()
        return {**dict(row), 'layout': json.loads(row['layout_json'])}

    def list_studio_views(self, owner_id: str, workspace_id: str) -> list[dict]:
        with self.con() as con:
            rows = con.execute('SELECT * FROM workspace_studio_views WHERE owner_id=? AND workspace_id=? ORDER BY name',
                               (str(owner_id), str(workspace_id))).fetchall()
        return [{**dict(row), 'layout': json.loads(row['layout_json'])} for row in rows]

    def link_project(self, owner_id: str, workspace_id: str, project_id: str) -> None:
        if not self.get(owner_id, workspace_id):
            raise LookupError('Workspace not found')
        with self.con() as con:
            con.execute('''INSERT OR IGNORE INTO workspace_resource_links(id,owner_id,workspace_id,resource_type,resource_id,created_at)
                VALUES(?,?,?,?,?,?)''', (str(uuid.uuid4()), str(owner_id), str(workspace_id), 'project', str(project_id), _now()))

    def unlink_project(self, owner_id: str, workspace_id: str, project_id: str) -> bool:
        with self.con() as con:
            result = con.execute('''DELETE FROM workspace_resource_links
                WHERE owner_id=? AND workspace_id=? AND resource_type='project' AND resource_id=?''',
                (str(owner_id), str(workspace_id), str(project_id)))
        return result.rowcount > 0

    def linked_projects(self, owner_id: str, workspace_id: str) -> list[dict]:
        with self.con() as con:
            rows = con.execute('''SELECT resource_id,created_at FROM workspace_resource_links
                WHERE owner_id=? AND workspace_id=? AND resource_type='project' ORDER BY created_at,resource_id''',
                (str(owner_id), str(workspace_id))).fetchall()
        return [dict(row) for row in rows]
