from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .migrations import migrate_work_schema
from .models import GoalSpec, WorkOrder, WorkPlan


def _json(data: dict) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


class WorkStore:
    """Normalized additive persistence for strategic work projections.

    Vishnu builds the runtime on the desktop/main thread and serves trusted
    control APIs from a dedicated server thread. Canonical Work therefore owns
    a SQLite connection that is deliberately allowed to cross those runtime
    threads. SQLite's serialized connection mode plus the store's transactional
    write paths remain authoritative; callers must still use the WorkStore APIs
    rather than sharing cursors or holding transactions outside the store.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is not None and db_path is not None:
            raise ValueError("provide db_path or connection, not both")
        self._owns_connection = connection is None
        self.connection = connection or sqlite3.connect(
            str(db_path or ":memory:"),
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        migrate_work_schema(self.connection)

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> "WorkStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def upsert_goal(self, goal: GoalSpec, *, source_p10_goal_id: str | None = None) -> GoalSpec:
        payload = _json(goal.to_dict())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO work_goals(
                    id, project_id, source_p10_goal_id, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    source_p10_goal_id = excluded.source_p10_goal_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    goal.id,
                    goal.project_id,
                    source_p10_goal_id,
                    payload,
                    goal.created_at,
                    goal.updated_at,
                ),
            )
        return goal

    def get_goal(self, goal_id: str) -> GoalSpec | None:
        row = self.connection.execute(
            "SELECT payload_json FROM work_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        return GoalSpec.from_dict(json.loads(row[0])) if row else None

    def project_goal_records(self, project_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT payload_json, source_p10_goal_id
            FROM work_goals
            WHERE project_id = ?
            ORDER BY updated_at, created_at, id
            """,
            (str(project_id),),
        ).fetchall()
        return [
            {
                "goal": GoalSpec.from_dict(json.loads(row["payload_json"])),
                "source_p10_goal_id": row["source_p10_goal_id"],
            }
            for row in rows
        ]

    def latest_project_goal_record(self, project_id: str) -> dict | None:
        records = self.project_goal_records(project_id)
        return records[-1] if records else None

    def next_plan_version(self, goal_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM work_plans WHERE goal_id = ?",
            (goal_id,),
        ).fetchone()
        return int(row[0])

    def latest_plan_for_source(self, source_p10_plan_id: str) -> WorkPlan | None:
        row = self.connection.execute(
            """
            SELECT payload_json
            FROM work_plans
            WHERE source_p10_plan_id = ?
            ORDER BY version DESC, created_at DESC
            LIMIT 1
            """,
            (source_p10_plan_id,),
        ).fetchone()
        return WorkPlan.from_dict(json.loads(row[0])) if row else None

    def project_plan_records(self, project_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT payload_json, source_p10_plan_id
            FROM work_plans
            WHERE project_id = ?
            ORDER BY created_at, version, id
            """,
            (str(project_id),),
        ).fetchall()
        return [
            {
                "plan": WorkPlan.from_dict(json.loads(row["payload_json"])),
                "source_p10_plan_id": row["source_p10_plan_id"],
            }
            for row in rows
        ]

    def latest_project_plan_record(self, project_id: str) -> dict | None:
        records = self.project_plan_records(project_id)
        return records[-1] if records else None

    def get_plan(self, plan_id: str) -> WorkPlan | None:
        row = self.connection.execute(
            "SELECT payload_json FROM work_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        return WorkPlan.from_dict(json.loads(row[0])) if row else None

    def save_plan(self, plan: WorkPlan, *, source_p10_plan_id: str | None = None) -> WorkPlan:
        payload = _json(plan.to_dict())
        order_ids = [order.id for order in plan.work_orders]
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO work_plans(
                    id, goal_id, project_id, source_p10_plan_id,
                    version, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    source_p10_plan_id = excluded.source_p10_plan_id,
                    status = excluded.status,
                    payload_json = excluded.payload_json
                """,
                (
                    plan.id,
                    plan.goal_id,
                    plan.project_id,
                    source_p10_plan_id,
                    plan.version,
                    plan.status.value,
                    payload,
                    plan.created_at,
                ),
            )
            if order_ids:
                marks = ",".join("?" for _ in order_ids)
                self.connection.execute(
                    f"DELETE FROM work_orders WHERE plan_id = ? AND id NOT IN ({marks})",
                    (plan.id, *order_ids),
                )
            else:
                self.connection.execute("DELETE FROM work_orders WHERE plan_id = ?", (plan.id,))
            for order in plan.work_orders:
                self._upsert_order(order)
            if order_ids:
                marks = ",".join("?" for _ in order_ids)
                self.connection.execute(
                    f"DELETE FROM work_order_dependencies WHERE work_order_id IN ({marks})",
                    tuple(order_ids),
                )
            for order in plan.work_orders:
                for dependency in order.dependencies:
                    self.connection.execute(
                        """
                        INSERT INTO work_order_dependencies(work_order_id, depends_on_id)
                        VALUES (?, ?)
                        ON CONFLICT(work_order_id, depends_on_id) DO NOTHING
                        """,
                        (order.id, dependency),
                    )
        return plan

    def _upsert_order(self, order: WorkOrder) -> None:
        self.connection.execute(
            """
            INSERT INTO work_orders(
                id, plan_id, project_id, project_task_id, worker_type,
                status, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                project_id = excluded.project_id,
                project_task_id = excluded.project_task_id,
                worker_type = excluded.worker_type,
                status = excluded.status,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                order.id,
                order.plan_id,
                order.project_id,
                order.project_task_id,
                order.worker_type,
                order.status.value,
                _json(order.to_dict()),
                order.created_at,
                order.updated_at,
            ),
        )

    def get_order(self, order_id: str) -> WorkOrder | None:
        row = self.connection.execute(
            "SELECT payload_json FROM work_orders WHERE id = ?", (order_id,)
        ).fetchone()
        return WorkOrder.from_dict(json.loads(row[0])) if row else None

    def list_orders(self, plan_id: str) -> list[WorkOrder]:
        return [
            WorkOrder.from_dict(json.loads(row[0]))
            for row in self.connection.execute(
                "SELECT payload_json FROM work_orders WHERE plan_id = ? ORDER BY created_at, id",
                (plan_id,),
            ).fetchall()
        ]

    def status(self) -> dict[str, int]:
        return {
            "goals": int(self.connection.execute("SELECT COUNT(*) FROM work_goals").fetchone()[0]),
            "plans": int(self.connection.execute("SELECT COUNT(*) FROM work_plans").fetchone()[0]),
            "orders": int(self.connection.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]),
        }
