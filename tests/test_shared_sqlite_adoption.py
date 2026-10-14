from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from core.sqlite import MIGRATION_TABLE, MigrationError, connect_sqlite, run_migrations, schema_version
from knowledge.migrations import KNOWLEDGE_COMPONENT, KNOWLEDGE_MIGRATIONS
from knowledge.store import KnowledgeStore
from projects.migrations import PROJECT_COMPONENT, project_migrations
from projects.store import ProjectStore


def _cases(tmp_path):
    return [
        (
            'knowledge',
            tmp_path / 'knowledge.sqlite3',
            KNOWLEDGE_COMPONENT,
            KNOWLEDGE_MIGRATIONS,
            lambda path: KnowledgeStore(path, tmp_path / 'objects'),
            'knowledge_documents',
            'lineage_id',
        ),
        (
            'projects',
            tmp_path / 'projects.sqlite3',
            PROJECT_COMPONENT,
            project_migrations(ProjectStore._extract_text),
            ProjectStore,
            'projects',
            'project_type',
        ),
    ]


def _seed_v1(path, component, migrations, table):
    con = connect_sqlite(path)
    try:
        run_migrations(con, component=component, migrations=migrations, target_version=1)
        if table == 'knowledge_documents':
            con.execute(
                '''INSERT INTO knowledge_documents
                   (id,title,filename,media_type,source,checksum,size_bytes,object_name,created_at,updated_at)
                   VALUES('doc-1','Owner document','doc.txt','text/plain','upload','hash-1',4,'doc-1','t0','t0')'''
            )
        else:
            con.execute("INSERT INTO projects(id,name,created_at,updated_at) VALUES('project-1','Owner project','t0','t0')")
        con.commit()
    finally:
        con.close()


@pytest.mark.parametrize('component_index', [0, 1], ids=['knowledge', 'projects'])
def test_clean_initialization_uses_shared_connection_and_integrity(tmp_path, component_index):
    name, path, component, migrations, build, table, new_column = _cases(tmp_path)[component_index]
    store = build(path)
    con = store._con() if name == 'knowledge' else store.con()
    try:
        assert schema_version(con, component) == len(migrations)
        assert new_column in {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
        assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert con.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        con.close()


@pytest.mark.parametrize('component_index', [0, 1], ids=['knowledge', 'projects'])
def test_legacy_and_partially_upgraded_database_migrate_without_data_loss(tmp_path, component_index):
    name, path, component, migrations, build, table, new_column = _cases(tmp_path)[component_index]
    _seed_v1(path, component, migrations, table)
    con = connect_sqlite(path)
    try:
        # Simulate a historical unversioned/partially upgraded database: the
        # base schema exists but the component version record was not written.
        declaration = 'TEXT' if new_column == 'lineage_id' else "TEXT NOT NULL DEFAULT 'software'"
        con.execute(f'ALTER TABLE {table} ADD COLUMN {new_column} {declaration}')
        con.execute(f'DELETE FROM {MIGRATION_TABLE} WHERE component=?', (component,))
        con.commit()
    finally:
        con.close()

    build(path)
    con = connect_sqlite(path)
    try:
        assert schema_version(con, component) == len(migrations)
        assert new_column in {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
        assert con.execute(f'SELECT id FROM {table}').fetchone()[0] in {'doc-1', 'project-1'}
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        con.close()
    # Reopen after upgrade: startup is idempotent and existing state is retained.
    assert build(path)


@pytest.mark.parametrize('component_index', [0, 1], ids=['knowledge', 'projects'])
def test_migration_failure_rolls_back_and_retries(tmp_path, component_index):
    name, path, component, migrations, build, table, new_column = _cases(tmp_path)[component_index]
    _seed_v1(path, component, migrations, table)

    def fail_after_apply(phase, version):
        if phase == 'after_apply' and version == 2:
            raise RuntimeError('injected migration interruption')

    con = connect_sqlite(path)
    try:
        with pytest.raises(MigrationError):
            run_migrations(con, component=component, migrations=migrations, fault_injector=fail_after_apply)
        assert schema_version(con, component) == 1
        assert new_column not in {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
        run_migrations(con, component=component, migrations=migrations)
        assert schema_version(con, component) == len(migrations)
    finally:
        con.close()
    assert build(path)


@pytest.mark.parametrize('component_index', [0, 1], ids=['knowledge', 'projects'])
def test_concurrent_startup_and_future_schema_fail_closed(tmp_path, component_index):
    name, path, component, migrations, build, table, new_column = _cases(tmp_path)[component_index]
    with ThreadPoolExecutor(max_workers=6) as pool:
        stores = list(pool.map(lambda _index: build(path), range(6)))
    assert len(stores) == 6

    con = connect_sqlite(path)
    try:
        con.execute(
            f'''INSERT INTO {MIGRATION_TABLE}(component,version,updated_at)
                VALUES(?, ?, 'future') ON CONFLICT(component) DO UPDATE SET version=excluded.version''',
            (component, len(migrations) + 1),
        )
        con.commit()
    finally:
        con.close()
    with pytest.raises(MigrationError, match='newer than supported'):
        build(path)
