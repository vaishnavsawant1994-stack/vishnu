from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityForgeLifecycle:
    """Additive build/activation/invocation lineage stored beside F1 state."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS forge_builds(
                    id TEXT PRIMARY KEY,
                    spec_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    work_order_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    candidate_revision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_builds_spec
                    ON forge_builds(spec_id, updated_at);

                CREATE TABLE IF NOT EXISTS forge_activations(
                    id TEXT PRIMARY KEY,
                    capability_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    package_ref TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    build_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    previous_activation_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_activations_capability
                    ON forge_activations(capability_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_forge_activation_version
                    ON forge_activations(capability_id, version);

                CREATE TABLE IF NOT EXISTS forge_invocations(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_invocations_capability
                    ON forge_invocations(capability_id, created_at);
                """
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def record_build(
        self,
        *,
        build_id: str,
        spec_id: str,
        plan_id: str,
        work_order_id: str,
        attempt_id: str,
        candidate_revision: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        with self._con() as con:
            con.execute(
                """
                INSERT INTO forge_builds(
                    id,spec_id,plan_id,work_order_id,attempt_id,candidate_revision,
                    status,payload_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    candidate_revision=excluded.candidate_revision,
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    str(build_id), str(spec_id), str(plan_id), str(work_order_id),
                    str(attempt_id), str(candidate_revision), str(status),
                    json.dumps(dict(payload), sort_keys=True, default=str),
                    now, now,
                ),
            )
        return self.get_build(build_id) or {}

    def get_build(self, build_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_builds WHERE id=?", (str(build_id),)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def record_activation(
        self,
        *,
        activation_id: str,
        capability_id: str,
        version: str,
        package_ref: str,
        manifest_digest: str,
        build_id: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        with self._con() as con:
            previous = con.execute(
                """
                SELECT id FROM forge_activations
                WHERE capability_id=? AND status='active'
                ORDER BY created_at DESC LIMIT 1
                """,
                (str(capability_id),),
            ).fetchone()
            previous_id = str(previous["id"]) if previous else None
            if status == "active":
                con.execute(
                    "UPDATE forge_activations SET status='superseded',updated_at=? WHERE capability_id=? AND status='active'",
                    (now, str(capability_id)),
                )
            con.execute(
                """
                INSERT INTO forge_activations(
                    id,capability_id,version,package_ref,manifest_digest,build_id,
                    status,previous_activation_id,payload_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,payload_json=excluded.payload_json,updated_at=excluded.updated_at
                """,
                (
                    str(activation_id), str(capability_id), str(version), str(package_ref),
                    str(manifest_digest), str(build_id), str(status), previous_id,
                    json.dumps(dict(payload), sort_keys=True, default=str), now, now,
                ),
            )
        return self.get_activation(activation_id) or {}

    def get_activation(self, activation_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_activations WHERE id=?", (str(activation_id),)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def active_activation(self, capability_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                """
                SELECT id FROM forge_activations
                WHERE capability_id=? AND status='active'
                ORDER BY created_at DESC LIMIT 1
                """,
                (str(capability_id),),
            ).fetchone()
        return self.get_activation(str(row["id"])) if row else None

    def previous_activation(self, capability_id: str) -> dict[str, Any] | None:
        active = self.active_activation(capability_id)
        if not active:
            return None
        previous_id = active.get("previous_activation_id")
        return self.get_activation(previous_id) if previous_id else None

    def disable_active(self, capability_id: str) -> dict[str, Any] | None:
        now = _now()
        active = self.active_activation(capability_id)
        if not active:
            return None
        with self._con() as con:
            con.execute(
                "UPDATE forge_activations SET status='disabled',updated_at=? WHERE id=? AND status='active'",
                (now, str(active["id"])),
            )
        return self.get_activation(str(active["id"]))

    def rollback_to(self, capability_id: str, target_activation_id: str) -> dict[str, Any]:
        now = _now()
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute(
                "SELECT id FROM forge_activations WHERE capability_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
                (str(capability_id),),
            ).fetchone()
            target = con.execute(
                "SELECT id,capability_id FROM forge_activations WHERE id=?",
                (str(target_activation_id),),
            ).fetchone()
            if target is None or str(target["capability_id"]) != str(capability_id):
                con.rollback()
                raise KeyError(target_activation_id)
            if current and str(current["id"]) != str(target_activation_id):
                con.execute(
                    "UPDATE forge_activations SET status='rolled_back',updated_at=? WHERE id=?",
                    (now, str(current["id"])),
                )
            con.execute(
                "UPDATE forge_activations SET status='active',updated_at=? WHERE id=?",
                (now, str(target_activation_id)),
            )
            con.commit()
        result = self.get_activation(str(target_activation_id))
        if result is None:
            raise KeyError(target_activation_id)
        return result

    def record_invocation(
        self,
        *,
        capability_id: str,
        version: str,
        ok: bool,
        duration_ms: float,
        error_code: str | None = None,
    ) -> None:
        with self._con() as con:
            con.execute(
                """
                INSERT INTO forge_invocations(capability_id,version,ok,duration_ms,error_code,created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    str(capability_id), str(version), 1 if ok else 0,
                    max(0.0, float(duration_ms)),
                    None if error_code is None else str(error_code)[:120],
                    _now(),
                ),
            )

    def metrics(self, capability_id: str, *, limit: int = 500) -> dict[str, Any]:
        limit = max(1, min(int(limit), 5000))
        with self._con() as con:
            rows = con.execute(
                """
                SELECT ok,duration_ms,error_code FROM forge_invocations
                WHERE capability_id=? ORDER BY id DESC LIMIT ?
                """,
                (str(capability_id), limit),
            ).fetchall()
        count = len(rows)
        successes = sum(int(row["ok"]) for row in rows)
        durations = [float(row["duration_ms"]) for row in rows]
        return {
            "capability_id": str(capability_id),
            "samples": count,
            "successes": successes,
            "failures": count - successes,
            "success_rate": (successes / count) if count else None,
            "average_duration_ms": (sum(durations) / count) if count else None,
            "recent_error_codes": [str(row["error_code"]) for row in rows if row["error_code"]][:20],
        }
