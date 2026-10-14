from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from memory.policy import is_never_store
from memory.second_brain import MemoryCandidate


class GovernedMemory:
    """Owner-control gate around the canonical SecondBrain.

    This is governance, not a second memory authority. SecondBrain/MemoryStore
    remains canonical memory truth. This layer owns candidate lifecycle,
    owner-scoping, retry identity and promotion recovery.
    """

    CANONICAL_OWNER = 'owner'
    EXPLICIT_SOURCES = frozenset({
        'user', 'user-message', 'explicit-user', 'explicit-owner',
        'owner-confirmed', 'owner-import',
    })

    def __init__(self, brain, path: Path, *, events=None, is_enabled=None):
        self._brain = brain
        self.events = events
        self.is_enabled = is_enabled or (lambda: True)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(
                '''
                CREATE TABLE IF NOT EXISTS memory_candidates(
                    id TEXT PRIMARY KEY,
                    candidate_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_candidates_status
                    ON memory_candidates(status,created_at);
                CREATE TABLE IF NOT EXISTS ambient_memory_settings(
                    owner_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                    updated_at REAL NOT NULL, PRIMARY KEY(owner_id,key));
                CREATE TABLE IF NOT EXISTS ambient_memory_exclusions(
                    owner_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    created_at REAL NOT NULL, PRIMARY KEY(owner_id,conversation_id));
                '''
            )
            self._ensure_column(con, 'memory_candidates', 'owner_id', "TEXT NOT NULL DEFAULT 'owner'")
            self._ensure_column(con, 'memory_candidates', 'request_id', 'TEXT')
            self._ensure_column(con, 'memory_candidates', 'fingerprint', 'TEXT')
            self._ensure_column(con, 'memory_candidates', 'memory_id', 'TEXT')
            con.execute('CREATE INDEX IF NOT EXISTS idx_memory_candidates_owner_status ON memory_candidates(owner_id,status,created_at)')
            con.execute('CREATE INDEX IF NOT EXISTS idx_memory_candidates_request ON memory_candidates(owner_id,request_id)')
            con.execute('CREATE INDEX IF NOT EXISTS idx_memory_candidates_fingerprint ON memory_candidates(owner_id,fingerprint,status)')
        try:
            self._brain.store.second_brain = self
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._brain, name)

    @staticmethod
    def _ensure_column(con, table: str, name: str, definition: str):
        columns = {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
        if name not in columns:
            con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=30000')
        return con

    @classmethod
    def _require_owner(cls, owner_id: str | None) -> str:
        owner = str(owner_id or '').strip()
        if owner != cls.CANONICAL_OWNER:
            raise PermissionError('Personal Memory is scoped to the canonical owner')
        return owner

    def _emit(self, name: str, **payload):
        if self.events:
            self.events.emit(name, **payload)

    def context(self, *args, **kwargs):
        if not self.is_enabled():
            return []
        return self._brain.context(*args, **kwargs)

    def ambient_settings(self, *, owner_id: str = CANONICAL_OWNER):
        owner = self._require_owner(owner_id)
        defaults = {'enabled': True, 'sources': {'chats': True, 'projects': False, 'files': False},
                    'pause_until': None, 'retention': 'forever'}
        with self._con() as con:
            rows = con.execute('SELECT key,value FROM ambient_memory_settings WHERE owner_id=?', (owner,)).fetchall()
            exclusions = con.execute('SELECT conversation_id FROM ambient_memory_exclusions WHERE owner_id=? ORDER BY created_at DESC', (owner,)).fetchall()
        values = {row['key']: json.loads(row['value']) for row in rows}
        settings = {**defaults, **values}
        settings['sources'] = {**defaults['sources'], **(settings.get('sources') or {})}
        base_preferences = self._brain.store.preferences()
        settings['memory_enabled'] = bool(base_preferences.get('memory_enabled', True))
        settings['capture_active'] = bool(settings['enabled'] and settings['memory_enabled'] and
            any(settings['sources'].get(key, False) for key in ('chats', 'projects', 'files')) and
            not (settings.get('pause_until') and float(settings['pause_until']) > time.time()))
        settings['excluded_conversation_ids'] = [row['conversation_id'] for row in exclusions]
        settings['capabilities'] = {'chats': True, 'projects': True, 'files': True}
        settings['unavailable_sources'] = {}
        return settings

    def update_ambient_settings(self, changes: dict, *, owner_id: str = CANONICAL_OWNER):
        owner = self._require_owner(owner_id)
        allowed = {'enabled', 'sources', 'pause_until', 'retention'}
        if not changes or set(changes) - allowed:
            raise ValueError('Unsupported Ambient Memory setting')
        current = self.ambient_settings(owner_id=owner)
        updated = {key: current[key] for key in allowed}
        for key, value in changes.items():
            if key == 'sources':
                if not isinstance(value, dict) or set(value) - {'chats', 'projects', 'files'}:
                    raise ValueError('Invalid source settings')
                updated[key] = {**current['sources'], **{name: bool(enabled) for name, enabled in value.items()}}
            elif key == 'pause_until':
                if value is not None and (not isinstance(value, (int, float)) or value < time.time() or value > time.time() + 30 * 86400):
                    raise ValueError('Pause duration must be within the next 30 days')
                updated[key] = value
            elif key == 'retention':
                if value not in {'6_months', '1_year', 'forever'}:
                    raise ValueError('Choose a supported memory retention period')
                updated[key] = value
            elif key == 'enabled':
                if not isinstance(value, bool): raise ValueError('Enabled must be a boolean')
                updated[key] = value
        with self._con() as con:
            for key, value in changes.items():
                stored = updated[key]
                con.execute('INSERT INTO ambient_memory_settings(owner_id,key,value,updated_at) VALUES(?,?,?,?) '
                            'ON CONFLICT(owner_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                            (owner, key, json.dumps(stored), time.time()))
        if 'retention' in changes:
            self._apply_ambient_retention_setting(updated['retention'])
        return self.ambient_settings(owner_id=owner)

    def _apply_ambient_retention_setting(self, retention: str):
        store = self._brain.store
        days = {'6_months': 183, '1_year': 365}.get(retention)
        with store.lock, store.con() as con:
            rows = con.execute(f"SELECT id FROM memories WHERE {store.STORABLE_SQL} AND removed_at IS NULL").fetchall()
            ids = [str(row['id']) for row in rows]
        for memory_id in ids:
            memory = store.get(memory_id)
            if memory is None:
                continue
            try: metadata = json.loads(memory.get('metadata_json') or '{}')
            except (TypeError, ValueError): continue
            if not metadata.get('ambient'): continue
            if days:
                try: created = datetime.fromisoformat(str(memory['created_at']).replace('Z', '+00:00')).timestamp()
                except (TypeError, ValueError): created = time.time()
                metadata['ambient_expires_at'] = created + days * 86400
            else:
                metadata.pop('ambient_expires_at', None)
            store.update_memory(memory_id, metadata=metadata)

    def ambient_can_capture(self, source: str = 'chats', conversation_id: str | None = None, *, owner_id: str = CANONICAL_OWNER):
        settings = self.ambient_settings(owner_id=owner_id)
        if not settings['enabled'] or not settings['memory_enabled'] or not settings['sources'].get(source, False): return False
        if settings['pause_until'] and float(settings['pause_until']) > time.time(): return False
        if source == 'chats' and conversation_id:
            return str(conversation_id) not in settings['excluded_conversation_ids']
        return True

    def exclude_conversation(self, conversation_id: str, *, owner_id: str = CANONICAL_OWNER):
        owner = self._require_owner(owner_id)
        if not conversation_id or len(str(conversation_id)) > 200: raise ValueError('Invalid conversation ID')
        with self._con() as con:
            con.execute('INSERT OR IGNORE INTO ambient_memory_exclusions(owner_id,conversation_id,created_at) VALUES(?,?,?)', (owner, str(conversation_id), time.time()))
        return self.ambient_settings(owner_id=owner)

    def include_conversation(self, conversation_id: str, *, owner_id: str = CANONICAL_OWNER):
        owner = self._require_owner(owner_id)
        with self._con() as con:
            con.execute('DELETE FROM ambient_memory_exclusions WHERE owner_id=? AND conversation_id=?', (owner, str(conversation_id)))
        return self.ambient_settings(owner_id=owner)

    def remember_ambient(self, candidate: MemoryCandidate, *, source_type: str = 'chats', conversation_id: str | None = None,
                         project_id: str | None = None, source_id: str | None = None, request_id: str | None = None,
                         owner_id: str = CANONICAL_OWNER):
        if source_type not in {'chats', 'projects', 'files'} or not self.ambient_can_capture(source_type, conversation_id, owner_id=owner_id): return None
        data = self._normalize(candidate)
        metadata = {**data.get('metadata', {}), 'ambient': True, 'ambient_source': source_type}
        if conversation_id: metadata['conversation_id'] = str(conversation_id)
        if project_id: metadata.update({'scope': 'project', 'project_id': str(project_id)})
        if source_id: metadata['source_id'] = str(source_id)
        candidate = MemoryCandidate(type=data['type'], subject=data['subject'], content=data['content'],
            confidence=data['confidence'], source={'chats':'chat-conversation','projects':'project-context','files':'project-file'}[source_type], verified=False, tags=data['tags'],
            importance=data['importance'], sensitivity=data['sensitivity'], occurred_at=data['occurred_at'],
            evidence=data['evidence'], metadata=metadata, relationships=data['relationships'])
        return self.remember(candidate, owner_id=owner_id, request_id=request_id, force_review=True)

    def expire_ambient_memories(self, *, owner_id: str = CANONICAL_OWNER, now_ts: float | None = None) -> int:
        """Permanently expire only memories explicitly approved from Ambient Memory."""
        self._require_owner(owner_id)
        current = float(now_ts if now_ts is not None else time.time())
        store = self._brain.store
        with store.lock, store.con() as con:
            rows = con.execute(f"SELECT id FROM memories WHERE {store.STORABLE_SQL} AND removed_at IS NULL").fetchall()
        expired = []
        for row in rows:
            memory = store.get(str(row['id']))
            if memory is None:
                continue
            try: metadata = json.loads(memory.get('metadata_json') or '{}')
            except (TypeError, ValueError): continue
            value = metadata.get('ambient_expires_at') if metadata.get('ambient') else None
            if value is not None:
                try:
                    if float(value) <= current: expired.append(str(row['id']))
                except (TypeError, ValueError): pass
        for memory_id in expired:
            self._brain.delete(memory_id)
        if expired:
            try: self._brain.store.audit('memory', 'memory.ambient.retention_expired', {'count': len(expired)})
            except Exception: pass
        return len(expired)

    def temporal(self, *args, **kwargs):
        if not self.is_enabled():
            return []
        return self._brain.temporal(*args, **kwargs)

    def context_at(self, *args, **kwargs):
        if not self.is_enabled():
            return []
        return self._brain.context_at(*args, **kwargs)

    @staticmethod
    def _normalize(candidate: MemoryCandidate) -> dict:
        return {
            'type': str(candidate.type),
            'subject': str(candidate.subject),
            'content': str(candidate.content),
            'confidence': max(0.0, min(1.0, float(candidate.confidence))),
            'source': str(candidate.source or 'unknown'),
            'verified': bool(candidate.verified),
            'tags': list(candidate.tags or []),
            'importance': max(0.0, min(1.0, float(candidate.importance))),
            'sensitivity': str(candidate.sensitivity or 'normal').strip().lower(),
            'occurred_at': candidate.occurred_at,
            'evidence': list(candidate.evidence or []),
            'metadata': dict(candidate.metadata or {}),
            'relationships': list(candidate.relationships or []),
        }

    @staticmethod
    def _fingerprint(data: dict) -> str:
        stable = {
            'type': str(data.get('type') or '').strip().lower(),
            'subject': str(data.get('subject') or '').strip().lower(),
            'content': str(data.get('content') or '').strip(),
            'source': str(data.get('source') or '').strip().lower(),
            'sensitivity': str(data.get('sensitivity') or 'normal').strip().lower(),
        }
        return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @classmethod
    def _authoritative(cls, data: dict) -> bool:
        source = str(data.get('source') or '').strip().lower()
        return bool(data.get('verified')) and (
            source in cls.EXPLICIT_SOURCES
            or source.startswith('owner-confirmed:')
            or source.startswith('owner-import:')
        )

    @staticmethod
    def _candidate(data: dict, *, confirmed: bool = False) -> MemoryCandidate:
        source = str(data.get('source') or 'candidate')
        if confirmed:
            source = f'owner-confirmed:{source}'
        return MemoryCandidate(
            type=data['type'], subject=data['subject'], content=data['content'],
            confidence=float(data.get('confidence', 1.0)), source=source,
            verified=True if confirmed else bool(data.get('verified')),
            tags=list(data.get('tags') or []), importance=float(data.get('importance', 0.5)),
            sensitivity=str(data.get('sensitivity') or 'normal'), occurred_at=data.get('occurred_at'),
            evidence=list(data.get('evidence') or []), metadata=dict(data.get('metadata') or {}),
            relationships=list(data.get('relationships') or []),
        )

    def remember(self, candidate: MemoryCandidate, *, owner_id: str = CANONICAL_OWNER, request_id: str | None = None, force_review: bool = False) -> str | None:
        owner = self._require_owner(owner_id)
        if not self.is_enabled():
            self._emit('memory.candidate.blocked', reason='memory_disabled', source=str(candidate.source or 'unknown'))
            return None
        data = self._normalize(candidate)
        sensitivity = data['sensitivity']
        if is_never_store(sensitivity=sensitivity, metadata=data.get('metadata')):
            self._emit('memory.candidate.blocked', reason='never_store', source=data['source'])
            return None
        if self._authoritative(data):
            memory_id = self._brain.remember(candidate)
            self._emit('memory.committed', memory_id=memory_id, source=data['source'], verified=True)
            return memory_id
        if sensitivity != 'normal':
            self._emit('memory.candidate.blocked', reason='sensitive_requires_explicit_owner_write', source=data['source'])
            return None

        read_preferences = getattr(self._brain.store, 'preferences', None)
        preferences = read_preferences() if callable(read_preferences) else {
            'memory_enabled': True,
            'review_before_saving': True,
        }
        if not preferences['memory_enabled']:
            self._emit('memory.candidate.blocked', reason='memory_disabled', source=data['source'])
            return None
        if not preferences['review_before_saving'] and not force_review:
            memory_id = self._brain.remember(candidate)
            self._emit('memory.committed', memory_id=memory_id, source=data['source'], verified=False, review_skipped=True)
            return memory_id

        fingerprint = self._fingerprint(data)
        stamp = time.time()
        candidate_id = str(uuid.uuid4())
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            if request_id:
                existing = con.execute(
                    "SELECT * FROM memory_candidates WHERE owner_id=? AND request_id=? AND fingerprint=? ORDER BY created_at DESC LIMIT 1",
                    (owner, str(request_id), fingerprint),
                ).fetchone()
            else:
                existing = con.execute(
                    "SELECT * FROM memory_candidates WHERE owner_id=? AND fingerprint=? AND status IN ('pending','promoting','approved') ORDER BY created_at DESC LIMIT 1",
                    (owner, fingerprint),
                ).fetchone()
            if existing:
                return existing['memory_id'] if existing['status'] == 'approved' and existing['memory_id'] else existing['id']
            con.execute(
                '''INSERT INTO memory_candidates(
                    id,candidate_json,source,status,reason,created_at,updated_at,owner_id,request_id,fingerprint,memory_id)
                   VALUES(?,?,?,'pending','owner_confirmation_required',?,?,?,?,?,NULL)''',
                (candidate_id, json.dumps(data, sort_keys=True, default=str), data['source'], stamp, stamp, owner, str(request_id) if request_id else None, fingerprint),
            )
        self._emit('memory.candidate.pending', candidate_id=candidate_id, source=data['source'])
        return candidate_id

    def candidates(self, *, status: str = 'pending', limit: int = 100, owner_id: str = CANONICAL_OWNER) -> list[dict]:
        owner = self._require_owner(owner_id)
        bounded = max(1, min(int(limit), 500))
        with self._con() as con:
            rows = con.execute(
                '''SELECT id,candidate_json,source,status,reason,created_at,updated_at,owner_id,request_id,fingerprint,memory_id
                   FROM memory_candidates WHERE owner_id=? AND status=? ORDER BY created_at DESC,id DESC LIMIT ?''',
                (owner, str(status), bounded),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            candidate = json.loads(item.pop('candidate_json'))
            output.append({**item, 'candidate': candidate})
        return output

    def candidate(self, candidate_id: str, *, owner_id: str = CANONICAL_OWNER) -> dict | None:
        owner = self._require_owner(owner_id)
        with self._con() as con:
            row = con.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_id=?', (str(candidate_id), owner)).fetchone()
        if not row:
            return None
        item = dict(row)
        item['candidate'] = json.loads(item.pop('candidate_json'))
        return item

    def update_candidate(self, candidate_id: str, changes: dict, *, owner_id: str = CANONICAL_OWNER) -> dict:
        """Let the owner correct a pending suggestion before approving it."""
        owner = self._require_owner(owner_id)
        if not changes or set(changes) - {'subject', 'content', 'type'}:
            raise ValueError('Unsupported candidate changes')
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute(
                "SELECT candidate_json FROM memory_candidates WHERE id=? AND owner_id=? AND status='pending'",
                (str(candidate_id), owner),
            ).fetchone()
            if not row:
                raise KeyError('Pending memory candidate not found')
            data = json.loads(row['candidate_json'])
            data.update({key: str(value).strip() for key, value in changes.items()})
            if not data.get('subject') or not data.get('content') or not data.get('type'):
                raise ValueError('Candidate title, content and category are required')
            normalized = self._normalize(self._candidate(data))
            fingerprint = self._fingerprint(normalized)
            duplicate = con.execute(
                "SELECT id FROM memory_candidates WHERE owner_id=? AND fingerprint=? AND status IN ('pending','promoting','approved') AND id<>? LIMIT 1",
                (owner, fingerprint, str(candidate_id)),
            ).fetchone()
            if duplicate:
                raise ValueError('This suggestion duplicates another pending or saved memory')
            con.execute(
                'UPDATE memory_candidates SET candidate_json=?,fingerprint=?,updated_at=? WHERE id=? AND owner_id=? AND status=\'pending\'',
                (json.dumps(normalized, sort_keys=True, default=str), fingerprint, time.time(), str(candidate_id), owner),
            )
        self._emit('memory.candidate.edited', candidate_id=str(candidate_id))
        return self.candidate(candidate_id, owner_id=owner)

    def approve_candidate(self, candidate_id: str, *, owner_id: str = CANONICAL_OWNER) -> str:
        owner = self._require_owner(owner_id)
        candidate_id = str(candidate_id)
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM memory_candidates WHERE id=? AND owner_id=?', (candidate_id, owner)).fetchone()
            if row is None:
                raise KeyError('memory candidate not found')
            if row['status'] == 'approved' and row['memory_id']:
                return row['memory_id']
            if row['status'] == 'rejected':
                raise KeyError('memory candidate was rejected')
            if row['status'] not in {'pending', 'promoting'}:
                raise KeyError('memory candidate is not approvable')
            data = json.loads(row['candidate_json'])
            if is_never_store(sensitivity=data.get('sensitivity'), metadata=data.get('metadata')):
                con.execute("UPDATE memory_candidates SET status='rejected',reason='never_store',updated_at=? WHERE id=?", (time.time(), candidate_id))
                raise PermissionError('NEVER_STORE content cannot become canonical Memory')
            metadata = dict(data.get('metadata') or {})
            if metadata.get('ambient'):
                retention = self.ambient_settings(owner_id=owner).get('retention', 'forever')
                days = {'6_months': 183, '1_year': 365}.get(retention)
                if days:
                    metadata['ambient_expires_at'] = time.time() + days * 86400
                else:
                    metadata.pop('ambient_expires_at', None)
                data['metadata'] = metadata
            con.execute("UPDATE memory_candidates SET status='promoting',updated_at=? WHERE id=?", (time.time(), candidate_id))

        memory_id = self._brain.remember(self._candidate(data, confirmed=True))
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute(
                "UPDATE memory_candidates SET status='approved',reason='owner_confirmed',memory_id=?,updated_at=? WHERE id=? AND owner_id=?",
                (memory_id, time.time(), candidate_id, owner),
            )
        self._emit('memory.candidate.approved', candidate_id=candidate_id, memory_id=memory_id)
        return memory_id

    def reject_candidate(self, candidate_id: str, *, owner_id: str = CANONICAL_OWNER) -> bool:
        owner = self._require_owner(owner_id)
        with self._con() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT status FROM memory_candidates WHERE id=? AND owner_id=?', (str(candidate_id), owner)).fetchone()
            if not row:
                return False
            if row['status'] == 'approved':
                return False
            con.execute(
                "UPDATE memory_candidates SET status='rejected',reason='owner_rejected',updated_at=? WHERE id=? AND owner_id=?",
                (time.time(), str(candidate_id), owner),
            )
        self._emit('memory.candidate.rejected', candidate_id=str(candidate_id))
        return True
