from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations
from sensorium.outcome_simulator import OutcomeSimulator


class ActionObservationLoop:
    """Post-action verification triggered by the existing approval completion event.

    This component never dispatches tools or activates sensors. It only changes
    a registered verification from awaiting_execution to awaiting_observation
    after the durable executor emits approval.completed.
    """

    COMPONENT = "sensorium_v3_action_feedback"

    def __init__(self, path: Path, *, world=None, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.world = world
        self.events = events
        self._unsubscribe = None
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "action-observation-feedback", self._migration_001),),
            )
        if events is not None and hasattr(events, "subscribe"):
            self._unsubscribe = events.subscribe("approval.completed", self._approval_completed)

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS action_verifications(
                verification_id TEXT PRIMARY KEY,
                proposed_action_id TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                expected_json TEXT NOT NULL,
                verification_sensors_json TEXT NOT NULL,
                observations_json TEXT NOT NULL,
                state TEXT NOT NULL,
                result_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_verification_approval "
            "ON action_verifications(approval_reference,state)"
        )

    @staticmethod
    def _json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 128 * 1024:
            raise ValueError("verification payload too large")
        return encoded

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def begin(
        self,
        proposed_action_id: str,
        *,
        approval_reference: str,
        expected_effects: list[dict[str, Any]],
        verification_sensors: list[str],
    ) -> dict[str, Any]:
        action_id = str(proposed_action_id or "").strip()
        approval = str(approval_reference or "").strip()
        sensors = [str(sensor).strip().lower() for sensor in verification_sensors if str(sensor).strip()]
        if not action_id or not approval:
            raise ValueError("verification requires proposed action and approval reference")
        if not expected_effects:
            raise ValueError("verification requires expected effects")
        if not sensors:
            raise ValueError("verification requires separately permitted sensor choices")
        verification_id = str(uuid.uuid4())
        now = time.time()
        with self._con() as con:
            con.execute(
                "INSERT INTO action_verifications VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    verification_id,
                    action_id[:240],
                    approval[:240],
                    self._json(expected_effects),
                    self._json(sensors[:32]),
                    self._json([]),
                    "awaiting_execution",
                    None,
                    now,
                    now,
                ),
            )
        self._emit(
            "sensorium.v3.feedback.registered",
            verification_id=verification_id,
            proposed_action_id=action_id[:240],
            approval_reference=approval[:240],
            action_executed_here=False,
            execution_authority=False,
        )
        return self.get(verification_id)

    def _approval_completed(self, message: dict[str, Any]) -> None:
        approval_id = str(message.get("approval_id") or "").strip()
        execution_id = str(message.get("execution_id") or "").strip()
        if not approval_id:
            return
        with self._con() as con:
            rows = con.execute(
                """SELECT verification_id FROM action_verifications
                   WHERE state='awaiting_execution'
                     AND (approval_reference=? OR proposed_action_id=?)""",
                (approval_id, execution_id),
            ).fetchall()
            for row in rows:
                con.execute(
                    "UPDATE action_verifications SET state='awaiting_observation',updated_at=? "
                    "WHERE verification_id=?",
                    (time.time(), row["verification_id"]),
                )
        for row in rows:
            self._emit(
                "sensorium.v3.feedback.execution_completed",
                verification_id=row["verification_id"],
                approval_reference=approval_id,
                execution_id=execution_id or None,
                tool=message.get("tool"),
                action_executed_here=False,
                execution_authority=False,
            )

    def mark_execution_completed(
        self,
        verification_id: str,
        *,
        approval_reference: str,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Recovery/manual bridge using an already authoritative completion record."""
        with self._con() as con:
            row = con.execute(
                "SELECT approval_reference,state FROM action_verifications WHERE verification_id=?",
                (verification_id,),
            ).fetchone()
            if row is None:
                raise KeyError("action verification not found")
            if str(row["approval_reference"]) != str(approval_reference):
                raise PermissionError("approval reference does not match verification")
            if row["state"] == "completed":
                return self.get(verification_id)
            con.execute(
                "UPDATE action_verifications SET state='awaiting_observation',updated_at=? "
                "WHERE verification_id=?",
                (time.time(), verification_id),
            )
        self._emit(
            "sensorium.v3.feedback.execution_completed",
            verification_id=verification_id,
            approval_reference=str(approval_reference)[:240],
            execution_id=(str(execution_id)[:240] if execution_id else None),
            action_executed_here=False,
            execution_authority=False,
        )
        return self.get(verification_id)

    def observe(
        self,
        verification_id: str,
        *,
        sensor: str,
        observed_state: dict[str, Any],
        source_device_id: str,
        captured_at: float | None = None,
    ) -> dict[str, Any]:
        sensor_name = str(sensor).strip().lower()
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM action_verifications WHERE verification_id=?",
                (verification_id,),
            ).fetchone()
            if row is None:
                raise KeyError("action verification not found")
            if row["state"] == "awaiting_execution":
                raise PermissionError("verification cannot observe before approved execution completes")
            if row["state"] == "completed":
                raise ValueError("action verification is already complete")
            allowed = set(json.loads(row["verification_sensors_json"]))
            if sensor_name not in allowed:
                raise PermissionError("sensor was not selected for this verification")
            observations = json.loads(row["observations_json"])
            observations.append(
                {
                    "sensor": sensor_name[:80],
                    "source_device_id": str(source_device_id)[:200],
                    "captured_at": float(captured_at or time.time()),
                    "state": observed_state,
                }
            )
            if len(observations) > 64:
                observations = observations[-64:]
            con.execute(
                "UPDATE action_verifications SET observations_json=?,updated_at=? WHERE verification_id=?",
                (self._json(observations), time.time(), verification_id),
            )
        return self.get(verification_id)

    def complete(
        self,
        verification_id: str,
        *,
        final_observed_state: dict[str, Any],
    ) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM action_verifications WHERE verification_id=?",
                (verification_id,),
            ).fetchone()
            if row is None:
                raise KeyError("action verification not found")
            if row["state"] == "awaiting_execution":
                raise PermissionError("verification cannot complete before approved execution completes")
            expected = json.loads(row["expected_json"])
            result = OutcomeSimulator.compare_expected_observed(expected, final_observed_state)
            result["verification_state"] = (
                "verified" if result["success_ratio"] == 1.0 else "mismatch"
            )
            result["action_executed_here"] = False
            result["execution_authority"] = False
            con.execute(
                "UPDATE action_verifications SET state='completed',result_json=?,updated_at=? "
                "WHERE verification_id=?",
                (self._json(result), time.time(), verification_id),
            )
        self._emit(
            "sensorium.v3.feedback.completed",
            verification_id=verification_id,
            success_ratio=result["success_ratio"],
            action_executed_here=False,
            execution_authority=False,
        )
        return self.get(verification_id)

    def get(self, verification_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM action_verifications WHERE verification_id=?",
                (verification_id,),
            ).fetchone()
        if row is None:
            raise KeyError("action verification not found")
        return {
            "verification_id": row["verification_id"],
            "proposed_action_id": row["proposed_action_id"],
            "approval_reference": row["approval_reference"],
            "expected_effects": json.loads(row["expected_json"]),
            "verification_sensors": json.loads(row["verification_sensors_json"]),
            "observations": json.loads(row["observations_json"]),
            "state": row["state"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "action_executed_here": False,
            "execution_authority": False,
        }
