from __future__ import annotations

import base64
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.sqlite import connect_sqlite, run_migrations, MigrationError
from memory.crypto import MemoryEncryptionError, MemoryFieldCipher, VAULT_KEY_NAME
from memory.migrations import MEMORY_STORE_COMPONENT, MEMORY_STORE_MIGRATIONS
from memory.store import MemoryStore
from security.vault import SecretVault


SENTINEL = 'SENSITIVE_TEST_VALUE_DO_NOT_LEAK_memory_7d03'


class FixedRootKeyStore:
    def __init__(self, key: bytes):
        self.key = key

    def get(self):
        return self.key

    def get_or_create(self):
        return self.key


class RotatingRootKeyStore(FixedRootKeyStore):
    def __init__(self, key: bytes):
        super().__init__(key)
        self.staged = {}

    def validate_rotation_id(self, rotation_id):
        if not re.fullmatch(r'[0-9a-f]{32}', rotation_id):
            raise ValueError('invalid rotation ID')
        return rotation_id

    def stage_rotation(self, rotation_id):
        self.staged[rotation_id] = b'n' * 32
        return self.staged[rotation_id]

    def promote_staged(self, rotation_id):
        self.key = self.staged[rotation_id]
        return self.key

    def get_staged(self, rotation_id):
        return self.staged.get(rotation_id)

    def discard_staged(self, rotation_id):
        self.staged.pop(rotation_id, None)


def make_vault(path, key=b'k' * 32):
    return SecretVault(path, root_key_store=FixedRootKeyStore(key))


def test_new_content_is_authenticated_and_not_stored_as_plaintext(tmp_path):
    db_path = tmp_path / 'owner.sqlite3'
    store = MemoryStore(db_path, vault=make_vault(tmp_path / 'vault.json'))
    memory_id = store.remember(type='private', subject='personal subject ' + SENTINEL,
                               content='private content ' + SENTINEL,
                               evidence=[{'text': SENTINEL}], metadata={'note': SENTINEL})
    store.add_message('user', 'message ' + SENTINEL, metadata={'private': SENTINEL})
    store.record_usage(memory_id, query='query ' + SENTINEL)
    store.audit('test', 'stored', {'private': SENTINEL})

    assert store.get(memory_id)['content'] == 'private content ' + SENTINEL
    store.con().close()
    raw = db_path.read_bytes()
    assert SENTINEL.encode() not in raw

    with sqlite3.connect(db_path) as con:
        assert con.execute('SELECT content FROM memories').fetchone()[0].startswith('v1:')
        assert con.execute('SELECT content FROM messages').fetchone()[0].startswith('v1:')
        assert con.execute('SELECT query FROM memory_usage').fetchone()[0].startswith('v1:')
        assert con.execute('SELECT payload_json FROM audit').fetchone()[0].startswith('v1:')


def test_legacy_plaintext_rows_upgrade_once_and_remain_readable(tmp_path):
    db_path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(db_path) as con:
        con.executescript('''
            CREATE TABLE messages(id TEXT PRIMARY KEY, role TEXT, content TEXT, created_at TEXT);
            CREATE TABLE memories(id TEXT PRIMARY KEY, type TEXT, subject TEXT, content TEXT, source TEXT,
                confidence REAL, verified INTEGER, sensitivity TEXT, parent_id TEXT, tags_json TEXT,
                created_at TEXT, updated_at TEXT);
            INSERT INTO messages VALUES('m1','user', 'legacy message SENTINEL', '2020-01-01');
            INSERT INTO memories VALUES('r1','fact','legacy subject SENTINEL','legacy content SENTINEL',
                'user',1,0,'normal',NULL,'[]','2020-01-01','2020-01-01');
        ''')
    store = MemoryStore(db_path, vault=make_vault(tmp_path / 'vault.json'))
    assert store.get('r1')['content'] == 'legacy content SENTINEL'
    assert store.recent_messages() == [{'role': 'user', 'content': 'legacy message SENTINEL'}]
    with sqlite3.connect(db_path) as con:
        content = con.execute('SELECT content FROM memories WHERE id="r1"').fetchone()[0]
        assert content.startswith('v1:')
    first = db_path.read_bytes()
    MemoryStore(db_path, vault=store.vault)
    assert db_path.read_bytes() == first
    assert b'legacy content SENTINEL' not in first


def test_legacy_auxiliary_memory_fields_are_migrated(tmp_path):
    path = tmp_path / 'auxiliary.sqlite3'
    with sqlite3.connect(path) as con:
        con.executescript('''
            CREATE TABLE tasks(id TEXT PRIMARY KEY, title TEXT, status TEXT, due_at TEXT,
                payload_json TEXT, created_at TEXT);
            CREATE TABLE audit(id TEXT PRIMARY KEY, category TEXT, action TEXT,
                payload_json TEXT, created_at TEXT);
            CREATE TABLE memory_usage(id TEXT PRIMARY KEY, memory_id TEXT, query TEXT,
                score REAL, used_at TEXT);
            CREATE TABLE memory_conflicts(id TEXT PRIMARY KEY, older_id TEXT, newer_id TEXT,
                resolution TEXT, reason TEXT, created_at TEXT);
            INSERT INTO tasks VALUES('t1','private task title','pending',NULL,'{"detail":"private task payload"}','now');
            INSERT INTO audit VALUES('a1','memory','updated','{"private":"private audit payload"}','now');
            INSERT INTO memory_usage VALUES('u1','missing','private search query',0.5,'now');
            INSERT INTO memory_conflicts VALUES('c1','old','new','unresolved','private conflict reason','now');
        ''')
    MemoryStore(path, vault=make_vault(tmp_path / 'vault.json'))
    with sqlite3.connect(path) as con:
        values = {
            'task_title': con.execute('SELECT title FROM tasks WHERE id="t1"').fetchone()[0],
            'task_payload': con.execute('SELECT payload_json FROM tasks WHERE id="t1"').fetchone()[0],
            'audit': con.execute('SELECT payload_json FROM audit WHERE id="a1"').fetchone()[0],
            'query': con.execute('SELECT query FROM memory_usage WHERE id="u1"').fetchone()[0],
            'reason': con.execute('SELECT reason FROM memory_conflicts WHERE id="c1"').fetchone()[0],
        }
    assert all(value.startswith('v1:') for value in values.values())
    raw = path.read_bytes()
    for marker in (b'private task title', b'private task payload', b'private audit payload',
                   b'private search query', b'private conflict reason'):
        assert marker not in raw


def test_wrong_key_and_tampering_fail_closed(tmp_path, caplog):
    vault = make_vault(tmp_path / 'vault.json')
    cipher = MemoryFieldCipher(vault)
    encoded = cipher.encrypt('messages', 'record-a', 'content', SENTINEL)
    assert cipher.decrypt('messages', 'record-a', 'content', encoded) == SENTINEL

    envelope = json.loads(encoded[3:])
    raw = bytearray(base64.b64decode(envelope['ct']))
    raw[-1] ^= 1
    envelope['ct'] = base64.b64encode(raw).decode()
    with pytest.raises(MemoryEncryptionError):
        cipher.decrypt('messages', 'record-a', 'content', 'v1:' + json.dumps(envelope))

    envelope = json.loads(encoded[3:])
    raw = bytearray(base64.b64decode(envelope['nonce']))
    raw[0] ^= 1
    envelope['nonce'] = base64.b64encode(raw).decode()
    with pytest.raises(MemoryEncryptionError):
        cipher.decrypt('messages', 'record-a', 'content', 'v1:' + json.dumps(envelope))

    envelope = json.loads(encoded[3:])
    envelope['kid'] = 'memory_store_dek_wrong'
    with pytest.raises(MemoryEncryptionError):
        cipher.decrypt('messages', 'record-a', 'content', 'v1:' + json.dumps(envelope))

    with pytest.raises(MemoryEncryptionError):
        cipher.decrypt('messages', 'record-b', 'content', encoded)
    with pytest.raises(MemoryEncryptionError):
        cipher.decrypt('memories', 'record-a', 'content', encoded)

    wrong_key_vault = make_vault(tmp_path / 'wrong-vault.json', key=b'w' * 32)
    wrong_key_cipher = MemoryFieldCipher(wrong_key_vault)
    with pytest.raises(MemoryEncryptionError):
        wrong_key_cipher.decrypt('messages', 'record-a', 'content', encoded)
    assert SENTINEL not in caplog.text


def test_concurrent_first_use_and_key_removal_fail_closed(tmp_path):
    vault = make_vault(tmp_path / 'vault.json')
    cipher = MemoryFieldCipher(vault)
    values = [(f'row-{index}', f'private-{index}') for index in range(64)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        encrypted = list(pool.map(
            lambda pair: cipher.encrypt('messages', pair[0], 'content', pair[1]), values
        ))
    assert [cipher.decrypt('messages', row_id, 'content', value)
            for (row_id, _), value in zip(values, encrypted)] == [value for _, value in values]

    vault.delete(VAULT_KEY_NAME)
    with pytest.raises(MemoryEncryptionError, match='key is unavailable'):
        cipher.encrypt('messages', 'new-row', 'content', 'must fail')


def test_mixed_legacy_and_encrypted_rows_migrate_without_reencrypting(tmp_path):
    path = tmp_path / 'mixed.sqlite3'
    vault = make_vault(tmp_path / 'vault.json')
    cipher = MemoryFieldCipher(vault)
    pre_encrypted = cipher.encrypt('messages', 'encrypted', 'content', 'kept')
    # Build v3 schema, then insert both a legacy row and an already-encrypted row.
    with connect_sqlite(path) as con:
        run_migrations(con, component=MEMORY_STORE_COMPONENT, migrations=MEMORY_STORE_MIGRATIONS)
        con.execute("INSERT INTO messages(id,role,content,created_at,metadata_json) VALUES(?,?,?,?,?)",
                    ('encrypted', 'user', pre_encrypted, 'now', '{}'))
        con.execute("INSERT INTO messages(id,role,content,created_at,metadata_json) VALUES(?,?,?,?,?)",
                    ('legacy', 'user', 'legacy mixed value', 'now', '{}'))

    store = MemoryStore(path, vault=vault)
    assert {item['content'] for item in store.recent_messages()} == {'kept', 'legacy mixed value'}
    with sqlite3.connect(path) as con:
        values = [row[0] for row in con.execute('SELECT content FROM messages ORDER BY id')]
    assert all(value.startswith('v1:') for value in values)
    assert values[0] == pre_encrypted


def test_encryption_migration_rollback_then_restart_is_safe(tmp_path):
    path = tmp_path / 'rollback.sqlite3'
    with sqlite3.connect(path) as con:
        con.executescript('''
            CREATE TABLE messages(id TEXT PRIMARY KEY, role TEXT, content TEXT, created_at TEXT);
            CREATE TABLE memories(id TEXT PRIMARY KEY, type TEXT, subject TEXT, content TEXT, source TEXT,
                confidence REAL, verified INTEGER, sensitivity TEXT, parent_id TEXT, tags_json TEXT,
                created_at TEXT, updated_at TEXT);
            INSERT INTO messages VALUES('m1','user', 'crash sentinel', 'now');
        ''')
    vault = make_vault(tmp_path / 'vault.json')
    store = MemoryStore.__new__(MemoryStore)
    store.path = path
    store.vault = vault
    store.cipher = MemoryFieldCipher(vault)
    store.lock = __import__('threading').RLock()
    con = store.con()
    try:
        def interrupt(phase, version):
            if phase == 'after_apply' and version == 4:
                raise RuntimeError('injected migration interruption')
        with pytest.raises(MigrationError, match='migration 4'):
            run_migrations(con, component=MEMORY_STORE_COMPONENT,
                           migrations=__import__('memory.migrations', fromlist=['memory_store_migrations']).memory_store_migrations(store.cipher),
                           fault_injector=interrupt)
        assert con.execute('SELECT content FROM messages WHERE id="m1"').fetchone()[0] == 'crash sentinel'
    finally:
        con.close()

    recovered = MemoryStore(path, vault=vault)
    assert recovered.recent_messages() == [{'role': 'user', 'content': 'crash sentinel'}]


def test_encrypted_backup_carries_only_wrapped_memory_key_and_restores_on_clean_host(tmp_path):
    from recovery.backup import BackupError, BackupService, MEMORY_KEY_ENVELOPE

    root_key = b'r' * 32
    source = tmp_path / 'source'
    source.mkdir()
    vault = SecretVault(source / 'vault.json', password='vault-password',
                        root_key_store=FixedRootKeyStore(root_key))
    store = MemoryStore(source / 'assistant.sqlite3', vault=vault)
    memory_id = store.remember(type='private', subject='backup subject', content=SENTINEL)
    original_key = base64.b64decode(vault.get(VAULT_KEY_NAME))
    backups = BackupService(source, root_key_store=FixedRootKeyStore(root_key),
                            vault=vault, vault_password='vault-password')
    archive = backups.create('encrypted-data.paibackup')
    raw_backup = archive.read_bytes()
    assert original_key not in raw_backup
    assert base64.b64encode(original_key) not in raw_backup

    payload, encrypted, cleanup = backups._payload_for_read(archive)
    try:
        assert encrypted
        with __import__('zipfile').ZipFile(payload) as zipped:
            envelope = json.loads(zipped.read(MEMORY_KEY_ENVELOPE))
            assert original_key not in base64.b64decode(envelope['wrapped_key'])
            envelope['wrapped_key'] = base64.b64encode(b'x' * 48).decode('ascii')
            with pytest.raises(BackupError, match='envelope is invalid'):
                backups._unwrap_memory_key(json.dumps(envelope).encode())
    finally:
        if cleanup:
            payload.unlink(missing_ok=True)

    target = tmp_path / 'clean-host'
    target.mkdir()
    target_backups = BackupService(target, root_key_store=FixedRootKeyStore(root_key),
                                   vault_password='vault-password')
    result = target_backups.restore(archive)
    assert result['ok'] is True
    restored_vault = SecretVault(target / 'vault.json', password='vault-password',
                                 root_key_store=FixedRootKeyStore(root_key))
    restored = MemoryStore(target / 'assistant.sqlite3', vault=restored_vault)
    assert base64.b64decode(restored.vault.get(VAULT_KEY_NAME)) == original_key
    assert restored.get(memory_id)['content'] == SENTINEL


def test_root_key_rotation_preserves_memory_field_key_and_content(tmp_path):
    path = tmp_path / 'assistant.sqlite3'
    root_store = RotatingRootKeyStore(b'o' * 32)
    vault_path = tmp_path / 'vault.json'
    vault = SecretVault(vault_path, root_key_store=root_store)
    store = MemoryStore(path, vault=vault)
    memory_id = store.remember(type='fact', subject='rotation', content=SENTINEL)
    field_key = vault.get(VAULT_KEY_NAME)

    vault.rotate_root_key()
    reopened_vault = SecretVault(vault_path, root_key_store=root_store)
    assert reopened_vault.get(VAULT_KEY_NAME) == field_key
    reopened = MemoryStore(path, vault=reopened_vault)
    assert reopened.get(memory_id)['content'] == SENTINEL

