from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


class TaskStateTracker:
    """Durable task progress, checkpoints and troubleshooting hypotheses."""

    COMPONENT = "sensorium_v3_task_state"
    STEP_STATES = {"pending", "active", "completed", "blocked", "skipped"}

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "task-state", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_tasks(
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                purpose TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_task_steps(
                step_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                expected_state_json TEXT NOT NULL,
                checkpoint_json TEXT NOT NULL,
                uncertainty REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(task_id,step_index),
                FOREIGN KEY(task_id) REFERENCES sensorium_tasks(task_id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_task_hypotheses(
                hypothesis_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                description TEXT NOT NULL,
                probability REAL NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(task_id) REFERENCES sensorium_tasks(task_id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("task state payload too large")
        return encoded

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def create(self, title: str, *, purpose: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        clean_title = str(title or "").strip()
        clean_purpose = str(purpose or "").strip()
        if not clean_title or not clean_purpose or not steps:
            raise ValueError("task requires title, purpose and at least one step")
        if len(steps) > 256:
            raise ValueError("task has too many steps")
        task_id = str(uuid.uuid4())
        now = time.time()
        with self._con() as con:
            con.execute(
                "INSERT INTO sensorium_tasks VALUES(?,?,?,?,?,?)",
                (task_id, clean_title[:240], clean_purpose[:2000], "planned", now, now),
            )
            for index, step in enumerate(steps, start=1):
                step_title = str(step.get("title") or step.get("action") or "").strip()
                if not step_title:
                    raise ValueError("each task step requires a title")
                con.execute(
                    """INSERT INTO sensorium_task_steps(
                        step_id,task_id,step_index,title,state,expected_state_json,
                        checkpoint_json,uncertainty,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()),
                        task_id,
                        index,
                        step_title[:500],
                        "pending",
                        self._json(step.get("expected_state") or {}),
                        self._json(step.get("checkpoint") or {}),
                        max(0.0, min(float(step.get("uncertainty", 0.5)), 1.0)),
                        now,
                    ),
                )
        self._emit("sensorium.v3.task.created", task_id=task_id, execution_authority=False)
        return self.state(task_id)

    def update_step(
        self,
        task_id: str,
        step_index: int,
        *,
        state: str,
        uncertainty: float | None = None,
        observed_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        step_state = str(state or "").strip().lower()
        if step_state not in self.STEP_STATES:
            raise ValueError("invalid task step state")
        now = time.time()
        with self._con() as con:
            row = con.execute(
                "SELECT step_id,checkpoint_json FROM sensorium_task_steps WHERE task_id=? AND step_index=?",
                (task_id, int(step_index)),
            ).fetchone()
            if row is None:
                raise KeyError("task step not found")
            uncertainty_value = (
                max(0.0, min(float(uncertainty), 1.0))
                if uncertainty is not None
                else None
            )
            checkpoint = json.loads(row["checkpoint_json"])
            if observed_state is not None:
                checkpoint["last_observed_state"] = observed_state
            if uncertainty_value is None:
                con.execute(
                    "UPDATE sensorium_task_steps SET state=?,checkpoint_json=?,updated_at=? WHERE step_id=?",
                    (step_state, self._json(checkpoint), now, row["step_id"]),
                )
            else:
                con.execute(
                    "UPDATE sensorium_task_steps SET state=?,uncertainty=?,checkpoint_json=?,updated_at=? "
                    "WHERE step_id=?",
                    (step_state, uncertainty_value, self._json(checkpoint), now, row["step_id"]),
                )
            aggregate = con.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END) AS completed,
                          SUM(CASE WHEN state='blocked' THEN 1 ELSE 0 END) AS blocked,
                          SUM(CASE WHEN state='active' THEN 1 ELSE 0 END) AS active
                   FROM sensorium_task_steps WHERE task_id=?""",
                (task_id,),
            ).fetchone()
            if aggregate["completed"] == aggregate["total"]:
                task_state = "completed"
            elif aggregate["blocked"]:
                task_state = "blocked"
            elif aggregate["active"] or aggregate["completed"]:
                task_state = "active"
            else:
                task_state = "planned"
            con.execute(
                "UPDATE sensorium_tasks SET state=?,updated_at=? WHERE task_id=?",
                (task_state, now, task_id),
            )
        self._emit(
            "sensorium.v3.task.step_updated",
            task_id=task_id,
            step_index=int(step_index),
            state=step_state,
            execution_authority=False,
        )
        return self.state(task_id)

    def record_hypothesis(
        self,
        task_id: str,
        *,
        description: str,
        probability: float,
        evidence: list[dict[str, Any]] | None = None,
        status: str = "open",
    ) -> dict[str, Any]:
        detail = str(description or "").strip()
        if not detail:
            raise ValueError("task hypothesis description is required")
        hypothesis_id = str(uuid.uuid4())
        score = max(0.0, min(float(probability), 1.0))
        with self._con() as con:
            if con.execute("SELECT 1 FROM sensorium_tasks WHERE task_id=?", (task_id,)).fetchone() is None:
                raise KeyError("task not found")
            con.execute(
                "INSERT INTO sensorium_task_hypotheses VALUES(?,?,?,?,?,?,?)",
                (
                    hypothesis_id,
                    task_id,
                    detail[:2000],
                    score,
                    str(status)[:40],
                    self._json(evidence or []),
                    time.time(),
                ),
            )
        return {"hypothesis_id": hypothesis_id, "task_id": task_id, "execution_authority": False}

    def state(self, task_id: str) -> dict[str, Any]:
        with self._con() as con:
            task = con.execute("SELECT * FROM sensorium_tasks WHERE task_id=?", (task_id,)).fetchone()
            if task is None:
                raise KeyError("task not found")
            steps = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM sensorium_task_steps WHERE task_id=? ORDER BY step_index",
                    (task_id,),
                ).fetchall()
            ]
            hypotheses = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM sensorium_task_hypotheses WHERE task_id=? "
                    "ORDER BY probability DESC,updated_at DESC",
                    (task_id,),
                ).fetchall()
            ]
        completed = sum(1 for row in steps if row["state"] == "completed")
        for row in steps:
            row["expected_state"] = json.loads(row.pop("expected_state_json"))
            row["checkpoint"] = json.loads(row.pop("checkpoint_json"))
        for row in hypotheses:
            row["evidence"] = json.loads(row.pop("evidence_json"))
        return {
            "task": dict(task),
            "progress": completed / len(steps) if steps else 0.0,
            "steps": steps,
            "hypotheses": hypotheses,
            "execution_authority": False,
        }
