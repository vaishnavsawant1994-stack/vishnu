from __future__ import annotations

import sqlite3
from collections.abc import Callable

from core.sqlite import Migration, add_column_if_missing


PROJECT_COMPONENT = 'project_store'


_BASE_TABLES = (
    '''CREATE TABLE IF NOT EXISTS projects(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
        target_date TEXT, conversation_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_tasks(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned',
        priority TEXT NOT NULL DEFAULT 'medium', owner TEXT NOT NULL DEFAULT 'owner', due_date TEXT,
        milestone_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_milestones(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned',
        target_date TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_threads(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_replies(
        id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES project_threads(id) ON DELETE CASCADE,
        author TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_files(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'link', url TEXT NOT NULL,
        knowledge_id TEXT, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_file_blobs(
        file_id TEXT PRIMARY KEY REFERENCES project_files(id) ON DELETE CASCADE,
        media_type TEXT NOT NULL, content BLOB NOT NULL, size_bytes INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_file_versions(
        file_id TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL,
        size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT 'owner',
        PRIMARY KEY(file_id,version))''',
    '''CREATE TABLE IF NOT EXISTS project_file_index(
        file_id TEXT PRIMARY KEY REFERENCES project_files(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        extracted_text TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'not_indexed',
        error TEXT NOT NULL DEFAULT '', indexed_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS project_activity(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        actor TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT,
        detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_task_files(
        task_id TEXT NOT NULL REFERENCES project_tasks(id) ON DELETE CASCADE,
        file_id TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        PRIMARY KEY(task_id,file_id))''',
    '''CREATE TABLE IF NOT EXISTS project_approvals(
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL, summary TEXT NOT NULL, impact_summary TEXT NOT NULL DEFAULT '',
        scope_summary TEXT NOT NULL DEFAULT '', proposed_by TEXT NOT NULL DEFAULT 'owner',
        proposed_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT,
        reviewed_at TEXT, decision TEXT, reviewer_comments TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS project_approval_tasks(
        approval_id TEXT NOT NULL REFERENCES project_approvals(id) ON DELETE CASCADE,
        task_id TEXT NOT NULL REFERENCES project_tasks(id) ON DELETE CASCADE,
        PRIMARY KEY(approval_id,task_id))''',
    '''CREATE TABLE IF NOT EXISTS project_approval_files(
        approval_id TEXT NOT NULL REFERENCES project_approvals(id) ON DELETE CASCADE,
        file_id TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
        PRIMARY KEY(approval_id,file_id))''',
    '''CREATE TABLE IF NOT EXISTS project_approval_history(
        id TEXT PRIMARY KEY, approval_id TEXT NOT NULL REFERENCES project_approvals(id) ON DELETE CASCADE,
        actor TEXT NOT NULL, decision TEXT NOT NULL, comments TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''',
)

_ADDITIONS = {
    'projects': {
        'project_type': "TEXT NOT NULL DEFAULT 'software'",
        'success_criteria': "TEXT NOT NULL DEFAULT ''",
        'instructions': "TEXT NOT NULL DEFAULT ''",
        'context_notes': "TEXT NOT NULL DEFAULT ''",
        'is_walkthrough': 'INTEGER NOT NULL DEFAULT 0',
    },
    'project_threads': {
        'linked_item_type': "TEXT NOT NULL DEFAULT ''", 'linked_item_id': 'TEXT',
        'pinned_reply_id': 'TEXT', 'followed': 'INTEGER NOT NULL DEFAULT 0',
        'resolved_by': 'TEXT', 'resolved_at': 'TEXT',
    },
    'project_files': {
        'folder_id': 'TEXT', 'is_pinned': 'INTEGER NOT NULL DEFAULT 0',
        'source_state': "TEXT NOT NULL DEFAULT 'stored'", 'deliverable_status': "TEXT NOT NULL DEFAULT ''",
        'source_provider': "TEXT NOT NULL DEFAULT ''", 'source_file_id': "TEXT NOT NULL DEFAULT ''",
        'source_modified_at': "TEXT NOT NULL DEFAULT ''",
    },
    'project_milestones': {'completion_criteria': "TEXT NOT NULL DEFAULT ''"},
    'project_tasks': {
        'context_notes': "TEXT NOT NULL DEFAULT ''", 'execution_workflow_id': 'TEXT',
        'execution_run_id': 'TEXT', 'execution_result': "TEXT NOT NULL DEFAULT ''",
    },
}


def _create_initial_schema(con: sqlite3.Connection) -> None:
    for statement in _BASE_TABLES:
        con.execute(statement)
    con.execute('CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_project_tasks_project ON project_tasks(project_id, created_at)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_project_activity_project ON project_activity(project_id, created_at DESC)')


def _add_workspace_features(extract_text: Callable) -> Callable[[sqlite3.Connection], None]:
    def apply(con: sqlite3.Connection) -> None:
        for table, columns in _ADDITIONS.items():
            for name, definition in columns.items():
                add_column_if_missing(con, table, name, definition)
        con.execute('''CREATE TABLE IF NOT EXISTS project_milestone_tasks(
            milestone_id TEXT NOT NULL REFERENCES project_milestones(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES project_tasks(id) ON DELETE CASCADE,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            PRIMARY KEY(milestone_id, task_id))''')
        con.execute('''INSERT OR IGNORE INTO project_milestone_tasks(milestone_id,task_id,project_id)
            SELECT milestone_id,id,project_id FROM project_tasks WHERE milestone_id IS NOT NULL''')
        try:
            con.execute('CREATE VIRTUAL TABLE IF NOT EXISTS project_file_fts USING fts5(file_id UNINDEXED, project_id UNINDEXED, title, body)')
            con.execute('CREATE INDEX IF NOT EXISTS idx_project_file_versions ON project_file_versions(file_id,version DESC)')
        except sqlite3.OperationalError:
            # Some packaged SQLite builds omit FTS5; the scoped LIKE fallback remains functional.
            pass
        rows = con.execute('''SELECT f.id,f.project_id,f.title,b.media_type,b.content,b.size_bytes
            FROM project_files f JOIN project_file_blobs b ON b.file_id=f.id
            LEFT JOIN project_file_index i ON i.file_id=f.id WHERE i.file_id IS NULL''').fetchall()
        for blob in rows:
            text = extract_text(blob['title'], blob['media_type'], bytes(blob['content']))
            state = 'indexed' if text is not None else 'not_indexed'
            con.execute('''INSERT OR IGNORE INTO project_file_index
                (file_id,project_id,extracted_text,state,indexed_at) VALUES(?,?,?,?,?)''',
                (blob['id'], blob['project_id'], text or '', state, _now() if text is not None else None))
            con.execute('''INSERT OR IGNORE INTO project_file_versions
                (file_id,version,media_type,content,size_bytes,created_at,created_by)
                VALUES(?,?,?,?,?,?,?)''',
                (blob['id'], 1, blob['media_type'], blob['content'], blob['size_bytes'], _now(), 'owner'))
            if text is not None:
                try:
                    con.execute('INSERT INTO project_file_fts(file_id,project_id,title,body) VALUES(?,?,?,?)',
                        (blob['id'], blob['project_id'], blob['title'], text))
                except sqlite3.OperationalError:
                    pass
    return apply


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def project_migrations(extract_text: Callable) -> tuple[Migration, ...]:
    return (
        Migration(1, 'project-workspace-storage', _create_initial_schema),
        Migration(2, 'project-workspace-features-and-backfill', _add_workspace_features(extract_text)),
    )
