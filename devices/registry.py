from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.security import hash_secret, new_bearer_secret, verify_secret
from core.sqlite import Migration, connect_sqlite, run_migrations


logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


class DeviceRegistry:
    """Trusted-device registry and coarse capability-request authority.

    ``sensor:*`` scopes permit requesting a local sensor consent ceremony. They
    never grant capture by themselves; SensorPermissionStore still requires an
    explicit, short-lived session for each concrete sensor/resource.
    """

    LEGACY_DEFAULT_SCOPES = {
        "ai:chat", "memory:read", "memory:write", "knowledge:read",
        "knowledge:write", "activities:read", "workflow:read",
        "workflow:write", "device:read",
    }
    LEGACY_OWNER_SCOPES = LEGACY_DEFAULT_SCOPES | {
        "device:admin", "workflow:approve", "knowledge:private",
        "memory:sensitive", "qualification:read", "qualification:record",
    }
    PRE_SENSOR_DEFAULT_SCOPES = LEGACY_DEFAULT_SCOPES | {"data:read", "data:sync"}
    PRE_SENSOR_OWNER_SCOPES = LEGACY_OWNER_SCOPES | {"data:read", "data:sync", "data:admin"}
    VISION_DEFAULT_SCOPES = PRE_SENSOR_DEFAULT_SCOPES | {"sensor:camera"}
    VISION_OWNER_SCOPES = PRE_SENSOR_OWNER_SCOPES | {"sensor:camera", "sensor:biometric"}
    SENSORIUM_REQUEST_SCOPES = {
        "sensor:camera",
        "sensor:microphone",
        "sensor:screen",
        "sensor:location",
        "sensor:motion",
        "sensor:clipboard",
        "sensor:network",
        "sensor:environment",
        "sensor:spatial",
        "sensor:document",
        "sensor:wearable",
        "sensor:iot",
    }
    DEFAULT_SCOPES = PRE_SENSOR_DEFAULT_SCOPES | SENSORIUM_REQUEST_SCOPES
    OWNER_SCOPES = PRE_SENSOR_OWNER_SCOPES | SENSORIUM_REQUEST_SCOPES | {"sensor:biometric"}

    def __init__(self, path: Path, events=None):
        self.path = Path(path)
        self.events = events
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = self._con()
        try:
            run_migrations(
                con,
                component="device_registry",
                migrations=(
                    Migration(1, "initial-device-registry", self._migration_001_initial),
                    Migration(2, "canonical-data-permissions", self._migration_002_permissions),
                    Migration(3, "canonical-sensor-permissions", self._migration_003_sensor_permissions),
                    Migration(4, "sensorium-2-request-scopes", self._migration_004_sensorium2_permissions),
                    Migration(5, "secure-pending-device-joins", self._migration_005_pending_joins),
                ),
            )
            with con:
                self._repair_permission_invariants(con)
        finally:
            con.close()

    def _migration_001_initial(self, con):
        con.execute(
            """CREATE TABLE IF NOT EXISTS devices(
                id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,
                salt TEXT NOT NULL,token_hash TEXT NOT NULL,created_at TEXT NOT NULL,
                last_seen_at TEXT,revoked INTEGER NOT NULL DEFAULT 0
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS device_metadata(
                device_id TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,updated_at TEXT NOT NULL,
                PRIMARY KEY(device_id,key),FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS device_permissions(
                device_id TEXT PRIMARY KEY,scopes_json TEXT NOT NULL,updated_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )"""
        )

    def _migration_002_permissions(self, con):
        self._repair_permission_invariants(con)

    def _migration_003_sensor_permissions(self, con):
        self._upgrade_untouched_scopes(con)

    def _migration_004_sensorium2_permissions(self, con):
        self._upgrade_untouched_scopes(con)

    def _migration_005_pending_joins(self, con):
        con.execute(
            """CREATE TABLE IF NOT EXISTS pending_device_joins(
                id TEXT PRIMARY KEY, device_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, platform TEXT NOT NULL,
                credential_salt TEXT NOT NULL, credential_hash TEXT NOT NULL,
                verification_code TEXT NOT NULL, status TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL NOT NULL,
                decided_at REAL, decided_by TEXT
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_pending_joins_status ON pending_device_joins(status,expires_at)")

    def _repair_permission_invariants(self, con):
        con.execute(
            """INSERT INTO device_permissions(device_id,scopes_json,updated_at)
               SELECT d.id,?,? FROM devices d LEFT JOIN device_permissions p ON p.device_id=d.id
               WHERE d.platform='ios-pwa' AND p.device_id IS NULL""",
            (json.dumps(sorted(self.OWNER_SCOPES)), now()),
        )
        con.execute(
            """INSERT INTO device_permissions(device_id,scopes_json,updated_at)
               SELECT d.id,?,? FROM devices d LEFT JOIN device_permissions p ON p.device_id=d.id
               WHERE d.platform!='ios-pwa' AND p.device_id IS NULL""",
            (json.dumps(sorted(self.DEFAULT_SCOPES)), now()),
        )
        self._upgrade_untouched_scopes(con)

    def _upgrade_untouched_scopes(self, con):
        rows = con.execute(
            """SELECT p.device_id,p.scopes_json,d.platform
               FROM device_permissions p JOIN devices d ON d.id=p.device_id"""
        ).fetchall()
        default_historical = (
            self.LEGACY_DEFAULT_SCOPES,
            self.PRE_SENSOR_DEFAULT_SCOPES,
            self.VISION_DEFAULT_SCOPES,
        )
        owner_historical = (
            self.LEGACY_OWNER_SCOPES,
            self.PRE_SENSOR_OWNER_SCOPES,
            self.VISION_OWNER_SCOPES,
        )
        for row in rows:
            try:
                scopes = {str(value) for value in json.loads(row["scopes_json"])}
            except Exception:
                logger.warning("Unable to decode legacy device permissions for %s", row["device_id"], exc_info=True)
                continue
            target = None
            if any(scopes == historical for historical in default_historical):
                target = self.DEFAULT_SCOPES
            elif any(scopes == historical for historical in owner_historical):
                target = self.OWNER_SCOPES
            if target is not None:
                con.execute(
                    "UPDATE device_permissions SET scopes_json=?,updated_at=? WHERE device_id=?",
                    (json.dumps(sorted(target)), now(), row["device_id"]),
                )

    def _con(self):
        return connect_sqlite(self.path)

    def enroll(self, name, platform):
        did = str(uuid.uuid4())
        token, salt, token_hash = new_bearer_secret()
        return self._insert_enrollment(did, token, salt, token_hash, name, platform)

    def request_join(self, name, platform="web-pwa", *, ttl_seconds=600):
        """Create a short-lived, untrusted device request. No device is enrolled yet."""
        from core.security import hash_secret
        import time

        join_id = str(uuid.uuid4())
        device_id = str(uuid.uuid4())
        token = new_bearer_secret()[0]
        salt = uuid.uuid4().hex
        credential_hash = hash_secret(token, salt)
        code = f"{secrets.randbelow(1_000_000):06d}"
        stamp = time.time()
        ttl = max(60, min(int(ttl_seconds), 900))
        with self._con() as con:
            con.execute(
                """INSERT INTO pending_device_joins
                   (id,device_id,name,platform,credential_salt,credential_hash,verification_code,status,created_at,expires_at)
                   VALUES(?,?,?,?,?,?,?,'pending',?,?)""",
                (join_id, device_id, str(name or "Owner browser")[:120], str(platform or "web-pwa")[:40],
                 salt, credential_hash, code, stamp, stamp + ttl),
            )
        return {"request_id": join_id, "device_id": device_id, "device_token": token,
                "verification_code": code, "expires_at": stamp + ttl}

    def pending_joins(self):
        import time
        stamp = time.time()
        with self._con() as con:
            con.execute("UPDATE pending_device_joins SET status='expired' WHERE status='pending' AND expires_at<?", (stamp,))
            rows = con.execute(
                """SELECT id,device_id,name,platform,verification_code,created_at,expires_at
                   FROM pending_device_joins WHERE status='pending' AND expires_at>=? ORDER BY created_at""",
                (stamp,),
            ).fetchall()
        return [{**dict(row), "request_id": row["id"]} for row in rows]

    def decide_join(self, request_id, *, approve, decided_by):
        """Atomically approve or deny one unexpired join, recording its trusted reviewer."""
        import time
        stamp = time.time()
        status = "approved" if approve else "denied"
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status,expires_at FROM pending_device_joins WHERE id=?", (str(request_id),)).fetchone()
            if not row or row["status"] != "pending" or float(row["expires_at"]) < stamp:
                con.rollback()
                return False
            changed = con.execute(
                "UPDATE pending_device_joins SET status=?,decided_at=?,decided_by=? WHERE id=? AND status='pending'",
                (status, stamp, str(decided_by), str(request_id)),
            ).rowcount == 1
            con.commit()
        return changed

    def join_status(self, request_id, token):
        from core.security import verify_secret
        import time
        with self._con() as con:
            row = con.execute("SELECT * FROM pending_device_joins WHERE id=?", (str(request_id),)).fetchone()
        if not row or not verify_secret(str(token or ""), row["credential_salt"], row["credential_hash"]):
            return None
        if row["status"] in {"pending", "approved"} and float(row["expires_at"]) < time.time():
            with self._con() as con:
                con.execute("UPDATE pending_device_joins SET status='expired' WHERE id=? AND status IN ('pending','approved')", (str(request_id),))
            return {"status": "expired"}
        return {"status": row["status"]}

    def complete_join(self, request_id, token):
        """Enroll the exact approved credential once; denied, expired, or replayed joins fail."""
        from core.security import verify_secret
        import time
        stamp = time.time()
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM pending_device_joins WHERE id=?", (str(request_id),)).fetchone()
            if (not row or row["status"] != "approved" or float(row["expires_at"]) < stamp
                    or not verify_secret(str(token or ""), row["credential_salt"], row["credential_hash"])):
                con.rollback()
                return None
            scopes = sorted(self.DEFAULT_SCOPES)
            con.execute(
                "INSERT INTO devices VALUES(?,?,?,?,?,?,?,0)",
                (row["device_id"], row["name"], row["platform"], row["credential_salt"],
                 row["credential_hash"], now(), None),
            )
            con.execute("INSERT INTO device_permissions VALUES(?,?,?)",
                        (row["device_id"], json.dumps(scopes), now()))
            con.execute("UPDATE pending_device_joins SET status='completed' WHERE id=? AND status='approved'", (str(request_id),))
            con.commit()
        return {"id": row["device_id"], "name": row["name"], "platform": row["platform"]}

    def enroll_with_credential(self, device_id, token, name, platform):
        did = str(device_id or "").strip()
        secret = str(token or "")
        native_platform = str(platform or "").strip()[:40]
        if len(did) < 16 or len(did) > 80:
            raise ValueError("Invalid device ID")
        if len(secret) < 32 or len(secret) > 256:
            raise ValueError("Device credential must contain at least 32 characters")
        salt = uuid.uuid4().hex
        token_hash = hash_secret(secret, salt)
        owner_scoped = native_platform in {"android", "ios"}
        requested_scopes = self.OWNER_SCOPES if owner_scoped else self.DEFAULT_SCOPES
        with self._con() as con:
            row = con.execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone()
            if row is not None:
                if row["revoked"] or not verify_secret(secret, row["salt"], row["token_hash"]):
                    raise ValueError("Device ID is already registered")
                if str(row["platform"]) in {"android", "ios"}:
                    con.execute(
                        """INSERT INTO device_permissions(device_id,scopes_json,updated_at) VALUES(?,?,?)
                           ON CONFLICT(device_id) DO UPDATE SET scopes_json=excluded.scopes_json,
                           updated_at=excluded.updated_at""",
                        (did, json.dumps(sorted(self.OWNER_SCOPES)), now()),
                    )
                return {"id": did, "name": row["name"], "platform": row["platform"]}, secret
            return self._insert_enrollment(
                did,
                secret,
                salt,
                token_hash,
                name,
                native_platform,
                scopes=requested_scopes,
            )

    def _insert_enrollment(self, did, token, salt, token_hash, name, platform, *, scopes=None):
        enrollment_scopes = set(scopes or self.DEFAULT_SCOPES)
        if not enrollment_scopes.issubset(self.OWNER_SCOPES):
            raise ValueError("Unsupported device permission scope")
        with self._con() as con:
            inserted = con.execute(
                "INSERT OR IGNORE INTO devices VALUES(?,?,?,?,?,?,?,0)",
                (did, str(name)[:120], str(platform)[:40], salt, token_hash, now(), None),
            ).rowcount
            if inserted:
                con.execute(
                    "INSERT INTO device_permissions VALUES(?,?,?)",
                    (did, json.dumps(sorted(enrollment_scopes)), now()),
                )
            else:
                row = con.execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone()
                if row is None or row["revoked"] or not verify_secret(token, row["salt"], row["token_hash"]):
                    raise ValueError("Device ID is already registered")
                return {"id": did, "name": row["name"], "platform": row["platform"]}, token
        return {"id": did, "name": str(name)[:120], "platform": str(platform)[:40]}, token

    def authenticate(self, device_id, token):
        with self._con() as con:
            row = con.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not row or row["revoked"]:
                return False
            ok = verify_secret(token, row["salt"], row["token_hash"])
            if ok:
                con.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (now(), device_id))
            return ok

    def is_active(self, device_id):
        with self._con() as con:
            return con.execute(
                "SELECT 1 FROM devices WHERE id=? AND revoked=0", (device_id,)
            ).fetchone() is not None

    def set_metadata(self, device_id, key, value):
        with self._con() as con:
            if not con.execute(
                "SELECT 1 FROM devices WHERE id=? AND revoked=0", (device_id,)
            ).fetchone():
                return False
            con.execute(
                """INSERT INTO device_metadata(device_id,key,value,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(device_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (device_id, key, value, now()),
            )
            return True

    def metadata(self, device_id):
        with self._con() as con:
            return {
                row["key"]: row["value"]
                for row in con.execute(
                    "SELECT key,value FROM device_metadata WHERE device_id=?", (device_id,)
                )
            }

    def _report_revoke_cleanup_failure(self, device_id, exc):
        logger.error(
            "Device %s was revoked but connector transaction cleanup failed",
            device_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        if self.events is None:
            return
        try:
            self.events.emit(
                "device.revoke_cleanup_failed",
                device_id=str(device_id),
                cleanup="connector_transactions",
                error_type=type(exc).__name__,
            )
        except Exception:
            logger.error("Unable to emit device revocation cleanup failure", exc_info=True)

    def revoke(self, device_id):
        with self._con() as con:
            cur = con.execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,))
        if cur.rowcount:
            try:
                connector_path = self.path.parent / "connectors.sqlite3"
                if connector_path.exists():
                    from integrations.state import ConnectorStateStore

                    ConnectorStateStore(connector_path).invalidate_device(str(device_id))
            except Exception as exc:
                self._report_revoke_cleanup_failure(device_id, exc)
        return cur.rowcount == 1

    def permissions(self, device_id):
        with self._con() as con:
            row = con.execute(
                "SELECT scopes_json,updated_at FROM device_permissions WHERE device_id=?",
                (device_id,),
            ).fetchone()
        if not row:
            return {"scopes": [], "updated_at": None}
        try:
            scopes = sorted({str(value) for value in json.loads(row["scopes_json"])})
        except Exception:
            logger.warning("Unable to decode device permissions for %s; denying all scopes", device_id, exc_info=True)
            scopes = []
        return {"scopes": scopes, "updated_at": row["updated_at"]}

    def authorize(self, device_id, scope):
        return self.is_active(device_id) and scope in set(self.permissions(device_id)["scopes"])

    def set_permissions(self, device_id, scopes):
        allowed = set(self.OWNER_SCOPES)
        clean = sorted({str(value).strip() for value in scopes if str(value).strip()})
        if not set(clean).issubset(allowed):
            raise ValueError("Unsupported device permission scope")
        with self._con() as con:
            if not con.execute(
                "SELECT 1 FROM devices WHERE id=? AND revoked=0", (device_id,)
            ).fetchone():
                raise KeyError("Active device not found")
            con.execute(
                """INSERT INTO device_permissions(device_id,scopes_json,updated_at) VALUES(?,?,?)
                   ON CONFLICT(device_id) DO UPDATE SET scopes_json=excluded.scopes_json,updated_at=excluded.updated_at""",
                (device_id, json.dumps(clean), now()),
            )
        return self.permissions(device_id)

    def list(self):
        with self._con() as con:
            rows = [
                dict(row)
                for row in con.execute(
                    "SELECT id,name,platform,created_at,last_seen_at,revoked FROM devices ORDER BY created_at DESC"
                )
            ]
        for row in rows:
            row["permissions"] = self.permissions(row["id"])["scopes"]
            row["metadata"] = self.metadata(row["id"])
        return rows
