from __future__ import annotations

import sqlite3

from core.sqlite import Migration, add_column_if_missing


KNOWLEDGE_COMPONENT = 'knowledge_store'


def _create_initial_schema(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_documents(
        id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
        media_type TEXT NOT NULL, source TEXT NOT NULL, checksum TEXT NOT NULL,
        size_bytes INTEGER NOT NULL, access_class TEXT NOT NULL DEFAULT 'owner',
        metadata_json TEXT NOT NULL DEFAULT '{}', object_name TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_checksum ON knowledge_documents(checksum)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_updated ON knowledge_documents(updated_at)')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_chunks(
        id TEXT PRIMARY KEY, document_id TEXT NOT NULL, position INTEGER NOT NULL,
        content TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE)''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document ON knowledge_chunks(document_id,position)')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_memory_links(
        id TEXT PRIMARY KEY, document_id TEXT NOT NULL, memory_id TEXT NOT NULL,
        relationship TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE)''')
    con.execute('''CREATE TABLE IF NOT EXISTS knowledge_collections(
        id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')


def _add_lineage_schema(con: sqlite3.Connection) -> None:
    for name, definition in (
        ('lineage_id', 'TEXT'),
        ('version_number', 'INTEGER NOT NULL DEFAULT 1'),
        ('is_current', 'INTEGER NOT NULL DEFAULT 1'),
        ('superseded_by_id', 'TEXT'),
        ('ingested_at', 'TEXT'),
    ):
        add_column_if_missing(con, 'knowledge_documents', name, definition)
    for name, definition in (
        ('page_start', 'INTEGER'),
        ('page_end', 'INTEGER'),
        ('location_json', "TEXT NOT NULL DEFAULT '{}'"),
    ):
        add_column_if_missing(con, 'knowledge_chunks', name, definition)
    con.execute('''UPDATE knowledge_documents
        SET lineage_id=COALESCE(lineage_id,id),
            version_number=COALESCE(version_number,1),
            is_current=COALESCE(is_current,1),
            ingested_at=COALESCE(ingested_at,created_at)''')
    con.execute('DROP INDEX IF EXISTS idx_knowledge_checksum')
    con.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_checksum ON knowledge_documents(checksum)')
    con.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_lineage_version
        ON knowledge_documents(lineage_id,version_number)''')
    con.execute('''CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_current
        ON knowledge_documents(lineage_id,is_current,version_number)''')


KNOWLEDGE_MIGRATIONS = (
    Migration(1, 'knowledge-document-storage', _create_initial_schema),
    Migration(2, 'knowledge-document-lineage-and-locations', _add_lineage_schema),
)
