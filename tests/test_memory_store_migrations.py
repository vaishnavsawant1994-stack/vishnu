from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.sqlite import MIGRATION_TABLE, MigrationError, connect_sqlite, run_migrations, schema_version, table_columns
from memory.migrations import MEMORY_STORE_COMPONENT, MEMORY_STORE_MIGRATIONS
from memory.store import MemoryStore


def _create_legacy_memory_store(path) -> None:
    con = sqlite3.connect(path)
    try:
        statements = (
            '''CREATE TABLE messages(
                id TEXT PRIMARY KEY, role TEXT, content TEXT, created_at TEXT)''',
            '''CREATE TABLE memories(
                id TEXT PRIMARY KEY, type TEXT, subject TEXT, content TEXT, source TEXT,
                confidence REAL, verified INTEGER, sensitivity TEXT, parent_id TEXT,
                tags_json TEXT, created_at TEXT, updated_at TEXT)''',
            '''CREATE TABLE relations(
                id TEXT PRIMARY KEY, source_id TEXT, relation TEXT, target_id TEXT, created_at TEXT)''',
            '''CREATE TABLE tasks(
                id TEXT PRIMARY KEY, title TEXT, status TEXT, due_at TEXT, payload_json TEXT, created_at TEXT)''',
            '''CREATE TABLE audit(
                id TEXT PRIMARY KEY, category TEXT, action TEXT, payload_json TEXT, created_at TEXT)''',
            '''CREATE TABLE memory_usage(
                id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, query TEXT, score REAL,
                used_at TEXT NOT NULL, FOREIGN KEY(memory_id) REFERENCES memories(id))''',
            '''CREATE TABLE memory_conflicts(
                id TEXT PRIMARY KEY, older_id TEXT NOT NULL, newer_id TEXT NOT NULL,
                resolution TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL)''',
            '''CREATE TABLE memory_preferences(
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)''',
        )
        for statement in statements:
            con.execute(statement)
        con.execute(
            '''INSERT INTO memories(
                id,type,subject,content,source,confidence,verified,sensitivity,parent_id,
                tags_json,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                'legacy-memory',
                'fact',
                'Legacy subject',
                'Legacy content',
                'user',
                0.9,
                1,
                'normal',
                None,
                '[]',
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00',
            ),
        )
        con.execute(
            'INSERT INTO messages(id,role,content,created_at) VALUES(?,?,?,?)',
            ('legacy-message', 'user', 'hello', '2026-01-01T00:00:00+00:00'),
        )
        con.execute(
            'INSERT INTO memory_preferences(key,value,updated_at) VALUES(?,?,?)',
            ('memory_enabled', 'false', '2026-01-01T00:00:00+00:00'),
        )
        con.commit()
    finally:
        con.close()


def test_fresh_memory_store_uses_shared_sqlite_and_latest_schema(tmp_path):
    path = tmp_path / 'memory.sqlite3'
    store = MemoryStore(path)

    con = store.con()
    try:
        assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert con.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
        assert schema_version(con, MEMORY_STORE_COMPONENT) == len(MEMORY_STORE_MIGRATIONS)
        assert {
            'importance',
            'occurred_at',
            'last_used_at',
            'use_count',
            'valid_from',
            'valid_to',
            'superseded_by',
            'evidence_json',
            'metadata_json',
            'removed_at',
        } <= table_columns(con, 'memories')
        assert {'conversation_id', 'device_id', 'metadata_json'} <= table_columns(con, 'messages')
        indexes = {
            row['name']
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert {
            'idx_memories_subject_type',
            'idx_memories_temporal',
            'idx_memory_usage_memory',
            'idx_memories_removed_updated',
            'idx_messages_conversation_created',
        } <= indexes
    finally:
        con.close()

    memory_id = store.remember(type='fact', subject='Name', content='Vishnu')
    assert store.get(memory_id)['content'] == 'Vishnu'
    store.add_message('user', 'hello', conversation_id='conversation-1', device_id='phone-1')
    assert store.recent_messages(conversation_id='conversation-1') == [
        {'role': 'user', 'content': 'hello'}
    ]


def test_legacy_unversioned_store_upgrades_without_losing_data(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    _create_legacy_memory_store(path)

    store = MemoryStore(path)
    con = store.con()
    try:
        assert schema_version(con, MEMORY_STORE_COMPONENT) == len(MEMORY_STORE_MIGRATIONS)
        row = con.execute('SELECT * FROM memories WHERE id=?', ('legacy-memory',)).fetchone()
        assert row['content'] == 'Legacy content'
        assert row['importance'] == pytest.approx(0.5)
        assert row['use_count'] == 0
        assert row['evidence_json'] == '[]'
        assert row['metadata_json'] == '{}'
        message = con.execute('SELECT * FROM messages WHERE id=?', ('legacy-message',)).fetchone()
        assert message['content'] == 'hello'
        assert message['metadata_json'] == '{}'
    finally:
        con.close()

    # Existing owner choices are preserved while a missing default is repaired.
    assert store.preferences() == {'memory_enabled': False, 'review_before_saving': True}


def test_partially_upgraded_unversioned_store_is_idempotently_completed(tmp_path):
    path = tmp_path / 'partial.sqlite3'
    _create_legacy_memory_store(path)
    raw = sqlite3.connect(path)
    try:
        raw.execute('ALTER TABLE memories ADD COLUMN importance REAL NOT NULL DEFAULT 0.5')
        raw.execute('ALTER TABLE messages ADD COLUMN conversation_id TEXT')
        raw.commit()
    finally:
        raw.close()

    MemoryStore(path)
    con = connect_sqlite(path)
    try:
        assert schema_version(con, MEMORY_STORE_COMPONENT) == len(MEMORY_STORE_MIGRATIONS)
        assert len([row for row in con.execute('PRAGMA table_info(memories)') if row['name'] == 'importance']) == 1
        assert len([row for row in con.execute('PRAGMA table_info(messages)') if row['name'] == 'conversation_id']) == 1
    finally:
        con.close()


def test_failed_memory_migration_rolls_back_and_restart_recovers(tmp_path):
    path = tmp_path / 'rollback.sqlite3'
    _create_legacy_memory_store(path)
    con = connect_sqlite(path)
    try:
        def fail_after_memory_fields(phase, version):
            if phase == 'after_apply' and version == 2:
                raise RuntimeError('simulated memory migration crash')

        with pytest.raises(MigrationError, match='memory_store migration 2'):
            run_migrations(
                con,
                component=MEMORY_STORE_COMPONENT,
                migrations=MEMORY_STORE_MIGRATIONS,
                fault_injector=fail_after_memory_fields,
            )
        assert schema_version(con, MEMORY_STORE_COMPONENT) == 1
        assert 'importance' not in table_columns(con, 'memories')
        assert con.execute('SELECT content FROM memories WHERE id=?', ('legacy-memory',)).fetchone()[0] == 'Legacy content'
    finally:
        con.close()

    # Normal restart retries from the last committed version and preserves data.
    store = MemoryStore(path)
    con = store.con()
    try:
        assert schema_version(con, MEMORY_STORE_COMPONENT) == len(MEMORY_STORE_MIGRATIONS)
        assert con.execute('SELECT content FROM memories WHERE id=?', ('legacy-memory',)).fetchone()[0] == 'Legacy content'
    finally:
        con.close()


def test_concurrent_memory_store_initializers_serialize_migrations(tmp_path):
    path = tmp_path / 'concurrent.sqlite3'
    _create_legacy_memory_store(path)

    def initialize(_value):
        store = MemoryStore(path)
        return store.preferences()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(initialize, range(4)))

    assert all(result == {'memory_enabled': False, 'review_before_saving': True} for result in results)
    con = connect_sqlite(path)
    try:
        assert schema_version(con, MEMORY_STORE_COMPONENT) == len(MEMORY_STORE_MIGRATIONS)
        assert con.execute(
            f'SELECT COUNT(*) FROM {MIGRATION_TABLE} WHERE component=?',
            (MEMORY_STORE_COMPONENT,),
        ).fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM memory_preferences').fetchone()[0] == 2
    finally:
        con.close()


def test_memory_preference_integrity_repair_is_restart_safe(tmp_path):
    path = tmp_path / 'preferences.sqlite3'
    store = MemoryStore(path)
    assert store.update_preferences(memory_enabled=False, review_before_saving=False) == {
        'memory_enabled': False,
        'review_before_saving': False,
    }

    con = store.con()
    try:
        with con:
            con.execute('DELETE FROM memory_preferences WHERE key=?', ('review_before_saving',))
    finally:
        con.close()

    restarted = MemoryStore(path)
    assert restarted.preferences() == {'memory_enabled': False, 'review_before_saving': True}


def test_memory_store_fails_closed_on_future_schema(tmp_path):
    path = tmp_path / 'future.sqlite3'
    con = connect_sqlite(path)
    try:
        con.execute(
            f'''CREATE TABLE {MIGRATION_TABLE}(
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL CHECK(version >= 0),
                updated_at TEXT NOT NULL
            )'''
        )
        con.execute(
            f'INSERT INTO {MIGRATION_TABLE}(component,version,updated_at) VALUES(?,?,?)',
            (MEMORY_STORE_COMPONENT, 99, 'now'),
        )
        con.commit()
    finally:
        con.close()

    with pytest.raises(MigrationError, match='newer than supported'):
        MemoryStore(path)
