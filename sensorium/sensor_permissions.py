from __future__ import annotations

import time
import uuid
from pathlib import Path

from core.sqlite import Migration, connect_sqlite, run_migrations


class SensorPermissionStore:
    """Per-device sensor policy with fail-closed, session-only grants.

    Persistent policy is deliberately limited to ``never`` or ``ask``. A sensor
    can only become usable through a short-lived ``session`` grant created after
    an explicit local consent ceremony. Session grants are invalidated on process
    restart so an old database row can never silently re-arm a camera.
    """

    COMPONENT = "sensor_permissions"
    PERSISTENT_MODES = frozenset({"never", "ask"})
    SENSORS = frozenset({"camera", "biometric"})
    DEFAULTS = {"camera": "ask", "biometric": "never"}
    MAX_SESSION_SECONDS = 10 * 60

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "sensor-permission-policy", self._migration_001),),
            )
            # A restart invalidates every temporary grant. This is intentional:
            # there is no durable "always allow camera" state in Vishnu.
            con.execute(
                "UPDATE sensor_permissions SET mode='ask',session_id=NULL,expires_at=NULL,updated_at=? "
                "WHERE mode='session' AND sensor='camera'",
                (time.time(),),
            )
            con.execute(
                "UPDATE sensor_permissions SET mode='never',session_id=NULL,expires_at=NULL,updated_at=? "
                "WHERE mode='session' AND sensor='biometric'",
                (time.time(),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensor_permissions(
                device_id TEXT NOT NULL,
                sensor TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                session_id TEXT,
                expires_at REAL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(device_id,sensor,resource_id)
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sensor_permissions_session "
            "ON sensor_permissions(device_id,sensor,mode,expires_at)"
        )

    @classmethod
    def _sensor(cls, value: str) -> str:
        sensor = str(value or "").strip().lower()
        if sensor not in cls.SENSORS:
            raise ValueError("unsupported sensor permission")
        return sensor

    @staticmethod
    def _device(value: str) -> str:
        device = str(value or "").strip()
        if not device or len(device) > 200:
            raise ValueError("valid device ID is required")
        return device

    @staticmethod
    def _resource(value: str | None) -> str:
        resource = str(value or "*").strip()
        if not resource or len(resource) > 240 or any(ord(ch) < 32 for ch in resource):
            raise ValueError("invalid sensor resource ID")
        return resource

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def _row(self, device_id: str, sensor: str, resource_id: str):
        with self._con() as con:
            exact = con.execute(
                "SELECT * FROM sensor_permissions WHERE device_id=? AND sensor=? AND resource_id=?",
                (device_id, sensor, resource_id),
            ).fetchone()
            if exact is not None:
                return exact
            if resource_id != "*":
                return con.execute(
                    "SELECT * FROM sensor_permissions WHERE device_id=? AND sensor=? AND resource_id='*'",
                    (device_id, sensor),
                ).fetchone()
        return None

    def permission(self, device_id: str, sensor: str, resource_id: str | None = None) -> dict:
        device = self._device(device_id)
        kind = self._sensor(sensor)
        resource = self._resource(resource_id)
        row = self._row(device, kind, resource)
        if row is None:
            return {
                "device_id": device,
                "sensor": kind,
                "resource_id": resource,
                "mode": self.DEFAULTS[kind],
                "session_id": None,
                "expires_at": None,
                "default": True,
            }
        mode = str(row["mode"])
        expires_at = row["expires_at"]
        if mode == "session" and (expires_at is None or float(expires_at) <= time.time()):
            fallback = self.DEFAULTS[kind]
            with self._con() as con:
                con.execute(
                    "UPDATE sensor_permissions SET mode=?,session_id=NULL,expires_at=NULL,updated_at=? "
                    "WHERE device_id=? AND sensor=? AND resource_id=?",
                    (fallback, time.time(), row["device_id"], row["sensor"], row["resource_id"]),
                )
            mode = fallback
            expires_at = None
        return {
            "device_id": device,
            "sensor": kind,
            "resource_id": resource,
            "mode": mode,
            "session_id": row["session_id"] if mode == "session" else None,
            "expires_at": float(expires_at) if expires_at is not None and mode == "session" else None,
            "default": False,
        }

    def set_policy(self, device_id: str, sensor: str, mode: str, resource_id: str | None = None) -> dict:
        device = self._device(device_id)
        kind = self._sensor(sensor)
        resource = self._resource(resource_id)
        selected = str(mode or "").strip().lower()
        if selected not in self.PERSISTENT_MODES:
            raise ValueError("sensor policy must be never or ask; permanent allow is forbidden")
        with self._con() as con:
            con.execute(
                """INSERT INTO sensor_permissions(device_id,sensor,resource_id,mode,session_id,expires_at,updated_at)
                   VALUES(?,?,?,?,NULL,NULL,?)
                   ON CONFLICT(device_id,sensor,resource_id) DO UPDATE SET
                     mode=excluded.mode,session_id=NULL,expires_at=NULL,updated_at=excluded.updated_at""",
                (device, kind, resource, selected, time.time()),
            )
        self._emit(
            "sensorium.permission.changed",
            device_id=device,
            sensor=kind,
            resource_id=resource,
            mode=selected,
        )
        return self.permission(device, kind, resource)

    def can_request(self, device_id: str, sensor: str, resource_id: str | None = None) -> bool:
        return self.permission(device_id, sensor, resource_id)["mode"] != "never"

    def grant_session(
        self,
        device_id: str,
        sensor: str,
        resource_id: str | None = None,
        *,
        ttl_seconds: float = 5 * 60,
        session_id: str | None = None,
    ) -> dict:
        device = self._device(device_id)
        kind = self._sensor(sensor)
        resource = self._resource(resource_id)
        current = self.permission(device, kind, resource)
        if current["mode"] == "never":
            raise PermissionError(f"{kind} is disabled for this device")
        ttl = max(30.0, min(float(ttl_seconds), float(self.MAX_SESSION_SECONDS)))
        grant = str(session_id or uuid.uuid4())
        if len(grant) < 8 or len(grant) > 200:
            raise ValueError("invalid sensor session ID")
        expires_at = time.time() + ttl
        with self._con() as con:
            con.execute(
                """INSERT INTO sensor_permissions(device_id,sensor,resource_id,mode,session_id,expires_at,updated_at)
                   VALUES(?,?,?,'session',?,?,?)
                   ON CONFLICT(device_id,sensor,resource_id) DO UPDATE SET
                     mode='session',session_id=excluded.session_id,expires_at=excluded.expires_at,
                     updated_at=excluded.updated_at""",
                (device, kind, resource, grant, expires_at, time.time()),
            )
        self._emit(
            "sensorium.permission.session_granted",
            device_id=device,
            sensor=kind,
            resource_id=resource,
            session_id=grant,
            expires_at=expires_at,
        )
        return self.permission(device, kind, resource)

    def allows(self, device_id: str, sensor: str, resource_id: str | None = None, *, session_id: str | None = None) -> bool:
        state = self.permission(device_id, sensor, resource_id)
        if state["mode"] != "session":
            return False
        return not session_id or state["session_id"] == str(session_id)

    def revoke_session(self, device_id: str, sensor: str, resource_id: str | None = None) -> dict:
        device = self._device(device_id)
        kind = self._sensor(sensor)
        resource = self._resource(resource_id)
        state = self.permission(device, kind, resource)
        fallback = self.DEFAULTS[kind]
        if state["mode"] == "session":
            with self._con() as con:
                con.execute(
                    "UPDATE sensor_permissions SET mode=?,session_id=NULL,expires_at=NULL,updated_at=? "
                    "WHERE device_id=? AND sensor=? AND resource_id=?",
                    (fallback, time.time(), device, kind, resource),
                )
            self._emit(
                "sensorium.permission.session_revoked",
                device_id=device,
                sensor=kind,
                resource_id=resource,
            )
        return self.permission(device, kind, resource)

    def list_device(self, device_id: str, *, sensor: str | None = None) -> list[dict]:
        device = self._device(device_id)
        kind = self._sensor(sensor) if sensor is not None else None
        with self._con() as con:
            if kind:
                rows = con.execute(
                    "SELECT sensor,resource_id FROM sensor_permissions WHERE device_id=? AND sensor=? ORDER BY resource_id",
                    (device, kind),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT sensor,resource_id FROM sensor_permissions WHERE device_id=? ORDER BY sensor,resource_id",
                    (device,),
                ).fetchall()
        output = [self.permission(device, row["sensor"], row["resource_id"]) for row in rows]
        existing = {(row["sensor"], row["resource_id"]) for row in output}
        for default_sensor in sorted(self.SENSORS):
            if kind and default_sensor != kind:
                continue
            if (default_sensor, "*") not in existing:
                output.append(self.permission(device, default_sensor, "*"))
        return output
