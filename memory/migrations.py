from __future__ import annotations

import sqlite3

from core.sqlite import Migration, add_column_if_missing


MEMORY_STORE_COMPONENT = 'memory_store'


def _create_baseline(con: sqlite3.Connection) -> None:
    statements = (
        '''CREATE TABLE IF NOT EXISTS messages(
            id TEXT PRIMARY KEY, role TEXT, content TEXT, created_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS memories(
            id TEXT PRIMARY KEY, type TEXT, subject TEXT, content TEXT, source TEXT,
            confidence REAL, verified INTEGER, sensitivity TEXT, parent_id TEXT,
            tags_json TEXT, created_at TEXT, updated_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS relations(
            id TEXT PRIMARY KEY, source_id TEXT, relation TEXT, target_id TEXT, created_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, title TEXT, status TEXT, due_at TEXT, payload_json TEXT, created_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS audit(
            id TEXT PRIMARY KEY, category TEXT, action TEXT, payload_json TEXT, created_at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS memory_usage(
            id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, query TEXT, score REAL,
            used_at TEXT NOT NULL, FOREIGN KEY(memory_id) REFERENCES memories(id))''',
        '''CREATE TABLE IF NOT EXISTS memory_conflicts(
            id TEXT PRIMARY KEY, older_id TEXT NOT NULL, newer_id TEXT NOT NULL,
            resolution TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS memory_preferences(
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    )
    for statement in statements:
        con.execute(statement)


def _add_memory_lifecycle_fields(con: sqlite3.Connection) -> None:
    additions = (
        ('importance', 'REAL NOT NULL DEFAULT 0.5'),
        ('occurred_at', 'TEXT'),
        ('last_used_at', 'TEXT'),
        ('use_count', 'INTEGER NOT NULL DEFAULT 0'),
        ('valid_from', 'TEXT'),
        ('valid_to', 'TEXT'),
        ('superseded_by', 'TEXT'),
        ('evidence_json', "TEXT NOT NULL DEFAULT '[]'"),
        ('metadata_json', "TEXT NOT NULL DEFAULT '{}'"),
        ('removed_at', 'TEXT'),
    )
    for column, definition in additions:
        add_column_if_missing(con, 'memories', column, definition)
    con.execute('CREATE INDEX IF NOT EXISTS idx_memories_subject_type ON memories(type,subject)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_memories_temporal ON memories(occurred_at,created_at)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_memory_usage_memory ON memory_usage(memory_id,used_at)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_memories_removed_updated ON memories(removed_at,updated_at)')


def _add_message_context_fields(con: sqlite3.Connection) -> None:
    additions = (
        ('conversation_id', 'TEXT'),
        ('device_id', 'TEXT'),
        ('metadata_json', "TEXT NOT NULL DEFAULT '{}'"),
    )
    for column, definition in additions:
        add_column_if_missing(con, 'messages', column, definition)
    con.execute(
        'CREATE INDEX IF NOT EXISTS idx_messages_conversation_created '
        'ON messages(conversation_id,created_at)'
    )


MEMORY_STORE_MIGRATIONS = (
    Migration(1, 'baseline-memory-store-schema', _create_baseline),
    Migration(2, 'memory-lifecycle-fields-and-indexes', _add_memory_lifecycle_fields),
    Migration(3, 'message-context-fields-and-index', _add_message_context_fields),
)
