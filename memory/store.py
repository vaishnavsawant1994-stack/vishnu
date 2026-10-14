from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from core.sqlite import connect_sqlite, run_migrations
from memory.crypto import MemoryEncryptionError, MemoryFieldCipher, SENSITIVE_FIELDS
from memory.migrations import MEMORY_STORE_COMPONENT, memory_store_migrations
from memory.policy import require_storable
from security.vault import SecretVault


def now():
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    STORABLE_SQL = "lower(replace(replace(trim(COALESCE(sensitivity,'')),'-','_'),' ','_')) != 'never_store'"
    SEARCH_SCAN_LIMIT = 5000

    def __init__(self, path: Path, *, vault: SecretVault | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        vault_path = self.path.parent / 'vault.json'
        self.vault = vault or SecretVault.get_or_create_live(vault_path)
        self.cipher = MemoryFieldCipher(self.vault)
        self._init()

    def con(self):
        con = connect_sqlite(self.path)
        # The one-time plaintext-to-ciphertext migration must not leave old
        # field values in freed SQLite pages.
        con.execute('PRAGMA secure_delete=ON')
        return con

    def _init(self):
        con = self.con()
        try:
            run_migrations(
                con,
                component=MEMORY_STORE_COMPONENT,
                migrations=memory_store_migrations(self.cipher),
            )
            self._validate_encryption(con)
            # These preferences are operational toggles, not owner-authored content.
            # Reconcile them on every startup so a missing row is repaired without
            # overwriting an owner's existing choice.
            with con:
                con.executemany(
                    'INSERT OR IGNORE INTO memory_preferences(key,value,updated_at) VALUES(?,?,?)',
                    [('memory_enabled', 'true', now()), ('review_before_saving', 'true', now())],
                )
        finally:
            con.close()

    def _validate_encryption(self, con):
        self.cipher.ensure_key(allow_create=False)
        for table, fields in SENSITIVE_FIELDS.items():
            columns = {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
            for field in fields:
                if field not in columns:
                    continue
                plaintext = con.execute(
                    f"SELECT id FROM {table} WHERE {field} IS NOT NULL AND {field} NOT LIKE 'v1:%' LIMIT 1"
                ).fetchone()
                if plaintext is not None:
                    raise MemoryEncryptionError(
                        f'MemoryStore encryption migration incomplete for {table}.{field}'
                    )
                sample = con.execute(
                    f"SELECT id,{field} FROM {table} WHERE {field} LIKE 'v1:%' LIMIT 1"
                ).fetchone()
                if sample is not None:
                    self.cipher.decrypt(table, str(sample['id']), field, sample[field])
        missing_hash = con.execute(
            "SELECT id FROM memories WHERE subject IS NOT NULL AND subject_hash IS NULL LIMIT 1"
        ).fetchone()
        if missing_hash is not None:
            raise MemoryEncryptionError('MemoryStore subject blind index is incomplete')

    def _encrypt(self, table, row_id, field, value):
        return self.cipher.encrypt(table, str(row_id), field, value)

    def _decrypt_row(self, table, row):
        item = dict(row)
        for field in SENSITIVE_FIELDS.get(table, ()):
            if field in item and item[field] is not None:
                item[field] = self.cipher.decrypt(table, str(item['id']), field, item[field])
        if table == 'memories':
            item.pop('subject_hash', None)
        return item

    def add_message(self, role, content, *, conversation_id=None, device_id=None, metadata=None):
        message_id = str(uuid.uuid4())
        encrypted_content = self._encrypt('messages', message_id, 'content', content)
        encrypted_metadata = self._encrypt(
            'messages', message_id, 'metadata_json', json.dumps(metadata or {}, default=str)
        )
        with self.lock, self.con() as con:
            con.execute(
                '''INSERT INTO messages(id,role,content,created_at,conversation_id,device_id,metadata_json)
                   VALUES(?,?,?,?,?,?,?)''',
                (message_id, role, encrypted_content, now(), conversation_id, device_id, encrypted_metadata),
            )
        return message_id

    def clear_conversation_messages(self) -> int:
        """Delete stored chat transcripts while preserving durable memories and audit rows."""
        with self.lock, self.con() as con:
            count = int(con.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
            con.execute('DELETE FROM messages')
        return count

    def recent_messages(self, limit=20, *, conversation_id=None):
        with self.con() as con:
            if conversation_id:
                rows = con.execute(
                    'SELECT id,role,content FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?',
                    (conversation_id, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT id,role,content FROM messages ORDER BY created_at DESC LIMIT ?',
                    (limit,),
                ).fetchall()
        output = []
        for row in reversed(rows):
            item = self._decrypt_row('messages', row)
            item.pop('id', None)
            output.append(item)
        return output

    def remember(
        self,
        *,
        type,
        subject,
        content,
        source='user',
        confidence=1.0,
        verified=False,
        sensitivity='normal',
        parent_id=None,
        tags=None,
        importance=0.5,
        occurred_at=None,
        valid_from=None,
        evidence=None,
        metadata=None,
    ):
        require_storable(sensitivity=sensitivity, metadata=metadata)
        memory_id = str(uuid.uuid4())
        stamp = now()
        subject_text = str(subject)
        with self.lock, self.con() as con:
            con.execute(
                '''INSERT INTO memories(
                    id,type,subject,content,source,confidence,verified,sensitivity,parent_id,tags_json,
                    created_at,updated_at,importance,occurred_at,last_used_at,use_count,valid_from,valid_to,
                    superseded_by,evidence_json,metadata_json,subject_hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,?)''',
                (
                    memory_id,
                    type,
                    self._encrypt('memories', memory_id, 'subject', subject_text),
                    self._encrypt('memories', memory_id, 'content', content),
                    self._encrypt('memories', memory_id, 'source', source),
                    float(confidence),
                    int(verified),
                    sensitivity,
                    parent_id,
                    self._encrypt('memories', memory_id, 'tags_json', json.dumps(tags or [])),
                    stamp,
                    stamp,
                    max(0.0, min(1.0, float(importance))),
                    occurred_at,
                    None,
                    0,
                    valid_from or occurred_at or stamp,
                    self._encrypt('memories', memory_id, 'evidence_json', json.dumps(evidence or [], default=str)),
                    self._encrypt('memories', memory_id, 'metadata_json', json.dumps(metadata or {}, default=str)),
                    self.cipher.blind_index(subject_text),
                ),
            )
        return memory_id

    def get(self, memory_id: str, *, include_removed: bool = False):
        removed_clause = '' if include_removed else ' AND removed_at IS NULL'
        with self.con() as con:
            row = con.execute(
                f'SELECT * FROM memories WHERE id=? AND {self.STORABLE_SQL}{removed_clause}',
                (memory_id,),
            ).fetchone()
        return self._decrypt_row('memories', row) if row else None

    def preferences(self):
        with self.con() as con:
            rows = {row['key']: row['value'] for row in con.execute('SELECT key,value FROM memory_preferences')}
        return {key: rows.get(key, 'true') == 'true' for key in ('memory_enabled', 'review_before_saving')}

    def update_preferences(self, *, memory_enabled: bool | None = None, review_before_saving: bool | None = None):
        values = {'memory_enabled': memory_enabled, 'review_before_saving': review_before_saving}
        stamp = now()
        with self.lock, self.con() as con:
            for key, value in values.items():
                if value is not None:
                    con.execute(
                        'INSERT INTO memory_preferences(key,value,updated_at) VALUES(?,?,?) '
                        'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                        (key, 'true' if value else 'false', stamp),
                    )
        return self.preferences()

    def soft_delete(self, memory_id: str):
        with self.lock, self.con() as con:
            cur = con.execute(
                'UPDATE memories SET removed_at=?,updated_at=? WHERE id=? AND removed_at IS NULL AND ' + self.STORABLE_SQL,
                (now(), now(), memory_id),
            )
        return cur.rowcount == 1

    def restore(self, memory_id: str):
        with self.lock, self.con() as con:
            cur = con.execute(
                'UPDATE memories SET removed_at=NULL,updated_at=? WHERE id=? AND removed_at IS NOT NULL AND ' + self.STORABLE_SQL,
                (now(), memory_id),
            )
        return cur.rowcount == 1

    def recently_removed(self, limit=100):
        with self.con() as con:
            rows = con.execute(
                f'SELECT * FROM memories WHERE removed_at IS NOT NULL AND {self.STORABLE_SQL} ORDER BY removed_at DESC LIMIT ?',
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._decrypt_row('memories', row) for row in rows]

    def update_memory(self, memory_id: str, **changes):
        require_storable(
            sensitivity=changes.get('sensitivity'),
            metadata=changes.get('metadata'),
        )
        allowed = {
            'type', 'subject', 'content', 'source', 'confidence', 'verified', 'sensitivity',
            'parent_id', 'importance', 'occurred_at', 'valid_from', 'valid_to', 'superseded_by',
        }
        fields = {key: value for key, value in changes.items() if key in allowed}
        if 'tags' in changes:
            fields['tags_json'] = json.dumps(changes['tags'] or [])
        if 'evidence' in changes:
            fields['evidence_json'] = json.dumps(changes['evidence'] or [], default=str)
        if 'metadata' in changes:
            fields['metadata_json'] = json.dumps(changes['metadata'] or {}, default=str)
        if not fields:
            return False
        for field in SENSITIVE_FIELDS['memories']:
            if field in fields:
                fields[field] = self._encrypt('memories', memory_id, field, fields[field])
        if 'subject' in changes:
            fields['subject_hash'] = self.cipher.blind_index(changes['subject'])
        fields['updated_at'] = now()
        query = ','.join(f'{key}=?' for key in fields)
        with self.lock, self.con() as con:
            cur = con.execute(
                f'UPDATE memories SET {query} WHERE id=? AND {self.STORABLE_SQL}',
                [*fields.values(), memory_id],
            )
        return cur.rowcount == 1

    def relate(self, source_id, relation, target_id):
        if not self.get(source_id) or not self.get(target_id):
            raise KeyError('memory not found')
        relation_id = str(uuid.uuid4())
        with self.lock, self.con() as con:
            con.execute('INSERT INTO relations VALUES(?,?,?,?,?)', (relation_id, source_id, relation, target_id, now()))
        return relation_id

    @staticmethod
    def _contains(item, query):
        needle = str(query).casefold()
        return needle in str(item.get('subject') or '').casefold() or needle in str(item.get('content') or '').casefold()

    def search(self, q, limit=20, *, active_only=False):
        limit = max(1, min(int(limit), 1000))
        active_clause = ' AND valid_to IS NULL' if active_only else ''
        with self.con() as con:
            rows = con.execute(
                f'''SELECT * FROM memories WHERE {self.STORABLE_SQL} AND removed_at IS NULL{active_clause}
                    ORDER BY updated_at DESC LIMIT ?''',
                (self.SEARCH_SCAN_LIMIT,),
            ).fetchall()
        output = []
        for row in rows:
            item = self._decrypt_row('memories', row)
            if self._contains(item, q):
                output.append(item)
                if len(output) >= limit:
                    break
        return output

    def active_subject(self, type: str, subject: str, limit=20):
        subject_hash = self.cipher.blind_index(subject)
        with self.con() as con:
            rows = con.execute(
                f'''SELECT * FROM memories WHERE {self.STORABLE_SQL} AND removed_at IS NULL
                   AND lower(type)=lower(?) AND subject_hash=? AND valid_to IS NULL
                   ORDER BY updated_at DESC LIMIT ?''',
                (type, subject_hash, limit),
            ).fetchall()
        return [self._decrypt_row('memories', row) for row in rows]

    def supersede(self, older_id: str, newer_id: str, *, reason='newer supported memory'):
        if not self.get(older_id) or not self.get(newer_id):
            raise KeyError('memory not found')
        stamp = now()
        conflict_id = str(uuid.uuid4())
        with self.lock, self.con() as con:
            older = con.execute('SELECT id FROM memories WHERE id=?', (older_id,)).fetchone()
            newer = con.execute('SELECT id FROM memories WHERE id=?', (newer_id,)).fetchone()
            if not older or not newer:
                raise KeyError('memory not found')
            con.execute(
                'UPDATE memories SET valid_to=?,superseded_by=?,updated_at=? WHERE id=? AND valid_to IS NULL',
                (stamp, newer_id, stamp, older_id),
            )
            con.execute(
                'INSERT INTO memory_conflicts VALUES(?,?,?,?,?,?)',
                (conflict_id, older_id, newer_id, 'superseded', self._encrypt('memory_conflicts', conflict_id, 'reason', reason), stamp),
            )
        return conflict_id

    def conflict(self, older_id: str, newer_id: str, *, resolution='unresolved', reason='conflicting supported memories'):
        if not self.get(older_id) or not self.get(newer_id):
            raise KeyError('memory not found')
        conflict_id = str(uuid.uuid4())
        with self.lock, self.con() as con:
            con.execute(
                'INSERT INTO memory_conflicts VALUES(?,?,?,?,?,?)',
                (conflict_id, older_id, newer_id, resolution, self._encrypt('memory_conflicts', conflict_id, 'reason', reason), now()),
            )
        return conflict_id

    def conflicts(self, limit=100):
        with self.con() as con:
            rows = [
                self._decrypt_row('memory_conflicts', row)
                for row in con.execute(
                    'SELECT * FROM memory_conflicts ORDER BY created_at DESC LIMIT ?',
                    (limit,),
                )
            ]
        return [row for row in rows if self.get(row['older_id']) and self.get(row['newer_id'])]

    def record_usage(self, memory_id: str, *, query: str = '', score: float | None = None):
        usage_id = str(uuid.uuid4())
        stamp = now()
        with self.lock, self.con() as con:
            if not con.execute(
                f'SELECT 1 FROM memories WHERE id=? AND {self.STORABLE_SQL}',
                (memory_id,),
            ).fetchone():
                return None
            con.execute(
                'INSERT INTO memory_usage VALUES(?,?,?,?,?)',
                (usage_id, memory_id, self._encrypt('memory_usage', usage_id, 'query', query), score, stamp),
            )
            con.execute(
                'UPDATE memories SET last_used_at=?,use_count=use_count+1,updated_at=updated_at WHERE id=?',
                (stamp, memory_id),
            )
        return usage_id

    def usage(self, memory_id: str, limit=100):
        if not self.get(memory_id):
            return []
        with self.con() as con:
            rows = con.execute(
                'SELECT * FROM memory_usage WHERE memory_id=? ORDER BY used_at DESC LIMIT ?',
                (memory_id, limit),
            ).fetchall()
        return [self._decrypt_row('memory_usage', row) for row in rows]

    def temporal_search(self, q='', *, start=None, end=None, memory_type=None, limit=100):
        clauses = [self.STORABLE_SQL, 'removed_at IS NULL']
        params = []
        if start:
            clauses.append('COALESCE(occurred_at,created_at)>=?')
            params.append(start)
        if end:
            clauses.append('COALESCE(occurred_at,created_at)<=?')
            params.append(end)
        if memory_type:
            clauses.append('lower(type)=lower(?)')
            params.append(memory_type)
        where = ' WHERE ' + ' AND '.join(clauses)
        requested = max(1, min(int(limit), 1000))
        params.append(self.SEARCH_SCAN_LIMIT if q else requested)
        with self.con() as con:
            rows = con.execute(
                f'SELECT * FROM memories{where} ORDER BY COALESCE(occurred_at,created_at) DESC LIMIT ?',
                params,
            ).fetchall()
        output = []
        for row in rows:
            item = self._decrypt_row('memories', row)
            if not q or self._contains(item, q):
                output.append(item)
                if len(output) >= requested:
                    break
        return output

    def graph(self):
        with self.con() as con:
            nodes = [
                self._decrypt_row('memories', row)
                for row in con.execute(
                    f'SELECT * FROM memories WHERE {self.STORABLE_SQL} AND removed_at IS NULL'
                ).fetchall()
            ]
            allowed = {row['id'] for row in nodes}
            edges = [
                dict(row)
                for row in con.execute('SELECT * FROM relations').fetchall()
                if row['source_id'] in allowed and row['target_id'] in allowed
            ]
            return {'nodes': nodes, 'edges': edges}

    def tree(self):
        """Return parent/child memory structure without changing graph semantics."""
        nodes = self.graph()['nodes']
        by_id = {row['id']: {**row, 'children': []} for row in nodes}
        roots = []
        for item in by_id.values():
            parent = by_id.get(item.get('parent_id'))
            if parent:
                parent['children'].append(item)
            else:
                roots.append(item)
        def key(item):
            return (str(item.get('type') or ''), str(item.get('subject') or '').lower())

        def sort_branch(branch):
            branch.sort(key=key)
            for child in branch:
                sort_branch(child['children'])

        sort_branch(roots)
        return roots

    def delete_memory(self, memory_id: str):
        """Permanently remove one owner-selected memory and its dependent evidence."""
        with self.lock, self.con() as con:
            if not con.execute('SELECT 1 FROM memories WHERE id=?', (memory_id,)).fetchone():
                return False
            con.execute('DELETE FROM relations WHERE source_id=? OR target_id=?', (memory_id, memory_id))
            con.execute('DELETE FROM memory_usage WHERE memory_id=?', (memory_id,))
            con.execute('DELETE FROM memory_conflicts WHERE older_id=? OR newer_id=?', (memory_id, memory_id))
            con.execute('UPDATE memories SET parent_id=NULL WHERE parent_id=?', (memory_id,))
            con.execute('UPDATE memories SET superseded_by=NULL WHERE superseded_by=?', (memory_id,))
            con.execute('DELETE FROM memories WHERE id=?', (memory_id,))
        return True

    def apply_retention(self, *, older_than_days: int, sensitivity: str | None = None, dry_run: bool = True):
        days = max(1, min(int(older_than_days), 36500))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        clauses = [self.STORABLE_SQL, 'removed_at IS NULL', 'COALESCE(occurred_at,created_at)<?']
        params = [cutoff]
        if sensitivity:
            clauses.append('sensitivity=?')
            params.append(str(sensitivity))
        where = ' AND '.join(clauses)
        with self.lock, self.con() as con:
            ids = [row['id'] for row in con.execute(f'SELECT id FROM memories WHERE {where}', params)]
        if not dry_run:
            for memory_id in ids:
                self.delete_memory(memory_id)
        return {'dry_run': bool(dry_run), 'older_than_days': days, 'matched': len(ids), 'memory_ids': ids}

    def export(self, *, include_sensitive: bool = True):
        with self.con() as con:
            clauses = [self.STORABLE_SQL, 'removed_at IS NULL']
            if not include_sensitive:
                clauses.append("sensitivity NOT IN ('sensitive','secret')")
            where = ' WHERE ' + ' AND '.join(clauses)
            memories = [
                self._decrypt_row('memories', row)
                for row in con.execute(f'SELECT * FROM memories{where} ORDER BY created_at')
            ]
            allowed = {row['id'] for row in memories}
            relations = [
                dict(row) for row in con.execute('SELECT * FROM relations ORDER BY created_at')
                if row['source_id'] in allowed and row['target_id'] in allowed
            ]
        return {'version': 1, 'exported_at': now(), 'memories': memories, 'relations': relations}

    def audit_entries(self, category: str | None = None, limit: int = 200):
        with self.con() as con:
            if category:
                rows = con.execute(
                    'SELECT * FROM audit WHERE category=? ORDER BY created_at DESC LIMIT ?',
                    (category, max(1, min(int(limit), 1000))),
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT * FROM audit ORDER BY created_at DESC LIMIT ?',
                    (max(1, min(int(limit), 1000)),),
                ).fetchall()
        output = []
        for row in rows:
            item = self._decrypt_row('audit', row)
            item['payload'] = json.loads(item.pop('payload_json') or '{}')
            output.append(item)
        return output

    def audit(self, category, action, payload=None):
        audit_id = str(uuid.uuid4())
        encrypted_payload = self._encrypt(
            'audit', audit_id, 'payload_json', json.dumps(payload or {}, default=str)
        )
        with self.lock, self.con() as con:
            con.execute(
                'INSERT INTO audit VALUES(?,?,?,?,?)',
                (audit_id, category, action, encrypted_payload, now()),
            )
        return audit_id
