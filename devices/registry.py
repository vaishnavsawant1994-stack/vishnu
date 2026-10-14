from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.security import new_bearer_secret, verify_secret
from core.sqlite import Migration, connect_sqlite, run_migrations


logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


class DeviceRegistry:
    # Keep the legacy sets explicit so upgrades can grant the new data-plane
    # scopes only to devices whose permissions were never customized by owner.
    LEGACY_DEFAULT_SCOPES = {
        'ai:chat', 'memory:read', 'memory:write', 'knowledge:read',
        'knowledge:write', 'activities:read', 'workflow:read',
        'workflow:write', 'device:read',
    }
    LEGACY_OWNER_SCOPES = LEGACY_DEFAULT_SCOPES | {
        'device:admin', 'workflow:approve', 'knowledge:private',
        'memory:sensitive', 'qualification:read', 'qualification:record',
    }
    DEFAULT_SCOPES = LEGACY_DEFAULT_SCOPES | {'data:read', 'data:sync'}
    OWNER_SCOPES = LEGACY_OWNER_SCOPES | {'data:read', 'data:sync', 'data:admin'}

    def __init__(self, path: Path, events=None):
        self.path = Path(path)
        self.events = events
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = self._con()
        try:
            run_migrations(
                con,
                component='device_registry',
                migrations=(
                    Migration(1, 'initial-device-registry', self._migration_001_initial),
                    Migration(2, 'canonical-data-permissions', self._migration_002_permissions),
                ),
            )
        finally:
            con.close()

    def _migration_001_initial(self, con):
        con.execute('''CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,salt TEXT NOT NULL,token_hash TEXT NOT NULL,created_at TEXT NOT NULL,last_seen_at TEXT,revoked INTEGER NOT NULL DEFAULT 0)''')
        con.execute('''CREATE TABLE IF NOT EXISTS device_metadata(device_id TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(device_id,key),FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE)''')
        con.execute('''CREATE TABLE IF NOT EXISTS device_permissions(device_id TEXT PRIMARY KEY,scopes_json TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE)''')

    def _migration_002_permissions(self, con):
        con.execute(
            '''INSERT INTO device_permissions(device_id,scopes_json,updated_at)
               SELECT d.id,?,? FROM devices d LEFT JOIN device_permissions p ON p.device_id=d.id
               WHERE d.platform='ios-pwa' AND p.device_id IS NULL''',
            (json.dumps(sorted(self.OWNER_SCOPES)), now()),
        )
        con.execute(
            '''INSERT INTO device_permissions(device_id,scopes_json,updated_at)
               SELECT d.id,?,? FROM devices d LEFT JOIN device_permissions p ON p.device_id=d.id
               WHERE d.platform!='ios-pwa' AND p.device_id IS NULL''',
            (json.dumps(sorted(self.DEFAULT_SCOPES)), now()),
        )
        self._upgrade_untouched_legacy_scopes(con)

    def _upgrade_untouched_legacy_scopes(self, con):
        rows = con.execute(
            '''SELECT p.device_id,p.scopes_json,d.platform
               FROM device_permissions p JOIN devices d ON d.id=p.device_id'''
        ).fetchall()
        for row in rows:
            try:
                scopes = {str(value) for value in json.loads(row['scopes_json'])}
            except Exception:
                logger.warning('Unable to decode legacy device permissions for %s', row['device_id'], exc_info=True)
                continue
            target = None
            if scopes == self.LEGACY_DEFAULT_SCOPES:
                target = self.DEFAULT_SCOPES
            elif scopes == self.LEGACY_OWNER_SCOPES:
                target = self.OWNER_SCOPES
            if target is not None:
                con.execute(
                    'UPDATE device_permissions SET scopes_json=?,updated_at=? WHERE device_id=?',
                    (json.dumps(sorted(target)), now(), row['device_id']),
                )

    def _con(self):
        return connect_sqlite(self.path)

    def enroll(self, name, platform):
        did = str(uuid.uuid4())
        token, salt, token_hash = new_bearer_secret()
        with self._con() as c:
            c.execute(
                'INSERT INTO devices VALUES(?,?,?,?,?,?,?,0)',
                (did, name, platform, salt, token_hash, now(), None),
            )
            c.execute(
                'INSERT INTO device_permissions VALUES(?,?,?)',
                (did, json.dumps(sorted(self.DEFAULT_SCOPES)), now()),
            )
        return {'id': did, 'name': name, 'platform': platform}, token

    def authenticate(self, device_id, token):
        with self._con() as c:
            row = c.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
            if not row or row['revoked']:
                return False
            ok = verify_secret(token, row['salt'], row['token_hash'])
            if ok:
                c.execute('UPDATE devices SET last_seen_at=? WHERE id=?', (now(), device_id))
            return ok

    def is_active(self, device_id):
        with self._con() as c:
            return c.execute(
                'SELECT 1 FROM devices WHERE id=? AND revoked=0', (device_id,)
            ).fetchone() is not None

    def set_metadata(self, device_id, key, value):
        with self._con() as c:
            if not c.execute(
                'SELECT 1 FROM devices WHERE id=? AND revoked=0', (device_id,)
            ).fetchone():
                return False
            c.execute(
                '''INSERT INTO device_metadata(device_id,key,value,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(device_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at''',
                (device_id, key, value, now()),
            )
            return True

    def metadata(self, device_id):
        with self._con() as c:
            return {
                row['key']: row['value']
                for row in c.execute(
                    'SELECT key,value FROM device_metadata WHERE device_id=?', (device_id,)
                )
            }

    def _report_revoke_cleanup_failure(self, device_id, exc):
        logger.error(
            'Device %s was revoked but connector transaction cleanup failed',
            device_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        if self.events is None:
            return
        try:
            self.events.emit(
                'device.revoke_cleanup_failed',
                device_id=str(device_id),
                cleanup='connector_transactions',
                error_type=type(exc).__name__,
            )
        except Exception:
            logger.error('Unable to emit device revocation cleanup failure', exc_info=True)

    def revoke(self, device_id):
        with self._con() as c:
            cur = c.execute('UPDATE devices SET revoked=1 WHERE id=?', (device_id,))
        if cur.rowcount:
            try:
                connector_path = self.path.parent / 'connectors.sqlite3'
                if connector_path.exists():
                    from integrations.state import ConnectorStateStore
                    ConnectorStateStore(connector_path).invalidate_device(str(device_id))
            except Exception as exc:
                self._report_revoke_cleanup_failure(device_id, exc)
        return cur.rowcount == 1

    def permissions(self, device_id):
        with self._con() as c:
            row = c.execute(
                'SELECT scopes_json,updated_at FROM device_permissions WHERE device_id=?',
                (device_id,),
            ).fetchone()
        if not row:
            return {'scopes': [], 'updated_at': None}
        try:
            scopes = sorted({str(value) for value in json.loads(row['scopes_json'])})
        except Exception:
            logger.warning('Unable to decode device permissions for %s; denying all scopes', device_id, exc_info=True)
            scopes = []
        return {'scopes': scopes, 'updated_at': row['updated_at']}

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in set(self.permissions(device_id)['scopes'])

    def set_permissions(self, device_id, scopes):
        allowed = set(self.OWNER_SCOPES)
        clean = sorted({str(value).strip() for value in scopes if str(value).strip()})
        if not set(clean).issubset(allowed):
            raise ValueError('Unsupported device permission scope')
        with self._con() as c:
            if not c.execute(
                'SELECT 1 FROM devices WHERE id=? AND revoked=0', (device_id,)
            ).fetchone():
                raise KeyError('Active device not found')
            c.execute(
                '''INSERT INTO device_permissions(device_id,scopes_json,updated_at) VALUES(?,?,?)
                   ON CONFLICT(device_id) DO UPDATE SET scopes_json=excluded.scopes_json,updated_at=excluded.updated_at''',
                (device_id, json.dumps(clean), now()),
            )
        return self.permissions(device_id)

    def list(self):
        with self._con() as c:
            rows = [
                dict(row)
                for row in c.execute(
                    'SELECT id,name,platform,created_at,last_seen_at,revoked FROM devices ORDER BY created_at DESC'
                )
            ]
        for row in rows:
            row['permissions'] = self.permissions(row['id'])['scopes']
            row['metadata'] = self.metadata(row['id'])
        return rows
