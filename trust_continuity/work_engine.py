from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


TERMINAL_STATES = {"completed", "failed", "cancelled"}
RUNNABLE_STATES = {"planned", "waiting", "retry", "running"}


class WorkEngineV2:
    """Durable plans/checkpoints/dependencies/retries/budgets without new action authority."""

    def __init__(
        self,
        store: TrustContinuityStore,
        *,
        approval_check: Callable[[str, dict[str, Any]], bool] | None = None,
    ):
        self.store = store
        self.approval_check = approval_check or (lambda _job_id, _step: False)

    def create_job(
        self,
        *,
        owner_id: str,
        title: str,
        steps: list[dict[str, Any]],
        deadline: str | None = None,
        max_retries: int = 3,
        budget: dict[str, float] | None = None,
        schedule: dict[str, Any] | None = None,
    ) -> str:
        if not steps:
            raise ValueError("at least one step is required")
        if len(steps) > 200:
            raise ValueError("too many work steps")
        if deadline:
            parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("deadline must include a timezone")
        normalized = []
        ids: set[str] = set()
        for index, raw in enumerate(steps):
            step = dict(raw)
            step_id = str(step.get("id") or f"step-{index + 1}")[:120]
            if step_id in ids:
                raise ValueError("duplicate step id")
            ids.add(step_id)
            normalized.append(
                {
                    "id": step_id,
                    "title": str(step.get("title") or step_id)[:240],
                    "depends_on": [str(item)[:120] for item in step.get("depends_on", [])],
                    "requires_approval": bool(step.get("requires_approval", False)),
                    "action": dict(step.get("action") or {}),
                    "status": "pending",
                    "attempts": 0,
                    "checkpoint": {},
                    "last_error": None,
                }
            )
        for step in normalized:
            unknown = set(step["depends_on"]) - ids
            if unknown:
                raise ValueError(f"unknown dependencies: {sorted(unknown)}")
        job_id = uuid4().hex
        payload = {
            "title": title[:240],
            "steps": normalized,
            "deadline": deadline,
            "max_retries": max(0, min(int(max_retries), 20)),
            "budget": dict(budget or {}),
            "budget_used": {key: 0.0 for key in (budget or {})},
            "schedule": dict(schedule or {}),
            "stop_reason": None,
            "created_at": utcnow(),
        }
        self.store.put("work_v2", job_id, payload, status="planned", owner_id=owner_id)
        self.store.audit("work", "job_created", actor=owner_id, subject=job_id, payload={"steps": len(normalized)})
        return job_id

    def next_step(self, job_id: str) -> dict[str, Any] | None:
        row = self._job(job_id)
        if row["status"] in TERMINAL_STATES:
            return None
        payload = row["payload"]
        if self._deadline_passed(payload.get("deadline")):
            self.stop(job_id, "deadline_exceeded", status="failed")
            return None
        completed = {step["id"] for step in payload["steps"] if step["status"] == "completed"}
        for step in payload["steps"]:
            if step["status"] in {"completed", "failed", "cancelled", "running"}:
                continue
            if not set(step["depends_on"]).issubset(completed):
                continue
            if step["requires_approval"] and not self.approval_check(job_id, step):
                self._set_status(job_id, "waiting", "approval_required")
                return {**step, "blocked": "approval_required"}
            return dict(step)
        if all(step["status"] == "completed" for step in payload["steps"]):
            self._set_status(job_id, "completed", None)
        return None

    def start_step(self, job_id: str, step_id: str) -> dict[str, Any]:
        row, payload, step = self._step(job_id, step_id)
        if step["status"] == "completed":
            return dict(step)
        if step["requires_approval"] and not self.approval_check(job_id, step):
            raise PermissionError("step requires existing Vishnu approval authority")
        step["status"] = "running"
        step["attempts"] = int(step.get("attempts", 0)) + 1
        step["started_at"] = utcnow()
        self.store.put("work_v2", job_id, payload, status="running", owner_id=row["owner_id"])
        self.store.audit("work", "step_started", subject=job_id, payload={"step_id": step_id, "attempt": step["attempts"]})
        return dict(step)

    def checkpoint(self, job_id: str, step_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        row, payload, step = self._step(job_id, step_id)
        if step["status"] != "running":
            raise RuntimeError("only a running step can checkpoint")
        step["checkpoint"] = dict(checkpoint)
        step["checkpointed_at"] = utcnow()
        self.store.put("work_v2", job_id, payload, status=row["status"], owner_id=row["owner_id"])
        self.store.audit("work", "checkpoint", subject=job_id, payload={"step_id": step_id})
        return dict(step)

    def complete_step(self, job_id: str, step_id: str, *, result: dict[str, Any] | None = None, cost: dict[str, float] | None = None) -> dict[str, Any]:
        row, payload, step = self._step(job_id, step_id)
        if step["status"] != "running":
            raise RuntimeError("step is not running")
        self._apply_cost(payload, cost or {})
        step.update({"status": "completed", "result": dict(result or {}), "completed_at": utcnow(), "last_error": None})
        new_status = "completed" if all(item["status"] == "completed" for item in payload["steps"]) else "planned"
        self.store.put("work_v2", job_id, payload, status=new_status, owner_id=row["owner_id"])
        self.store.audit("work", "step_completed", subject=job_id, payload={"step_id": step_id})
        return dict(step)

    def fail_step(self, job_id: str, step_id: str, *, error: str, retryable: bool = True) -> dict[str, Any]:
        row, payload, step = self._step(job_id, step_id)
        step["last_error"] = error[:4000]
        max_retries = int(payload["max_retries"])
        if retryable and int(step["attempts"]) <= max_retries:
            step["status"] = "retry"
            status = "retry"
            payload["stop_reason"] = f"retrying:{step_id}"
        else:
            step["status"] = "failed"
            status = "failed"
            payload["stop_reason"] = f"step_failed:{step_id}"
        self.store.put("work_v2", job_id, payload, status=status, owner_id=row["owner_id"])
        self.store.audit("work", "step_failed", subject=job_id, payload={"step_id": step_id, "retryable": retryable, "error": error[:1000]})
        return dict(step)

    def stop(self, job_id: str, reason: str, *, status: str = "cancelled") -> dict[str, Any]:
        if status not in TERMINAL_STATES | {"waiting"}:
            raise ValueError("invalid stop status")
        row = self._job(job_id)
        payload = dict(row["payload"])
        payload["stop_reason"] = reason[:1000]
        payload["stopped_at"] = utcnow()
        result = self.store.put("work_v2", job_id, payload, status=status, owner_id=row["owner_id"])
        self.store.audit("work", "stopped", subject=job_id, payload={"reason": reason[:1000], "status": status})
        return result

    def explain_stop(self, job_id: str) -> dict[str, Any]:
        row = self._job(job_id)
        payload = row["payload"]
        blocked = [
            {"id": step["id"], "status": step["status"], "last_error": step.get("last_error")}
            for step in payload["steps"]
            if step["status"] != "completed"
        ]
        return {"job_id": job_id, "status": row["status"], "reason": payload.get("stop_reason"), "blocked_steps": blocked}

    def _apply_cost(self, payload: dict[str, Any], cost: dict[str, float]) -> None:
        budget = payload.get("budget", {})
        used = payload.setdefault("budget_used", {})
        for key, raw in cost.items():
            amount = max(0.0, float(raw))
            next_value = float(used.get(key, 0.0)) + amount
            limit = budget.get(key)
            if limit is not None and next_value > float(limit):
                raise RuntimeError(f"work budget exceeded: {key}")
            used[key] = next_value

    @staticmethod
    def _deadline_passed(deadline: str | None) -> bool:
        if not deadline:
            return False
        parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > parsed.astimezone(timezone.utc)

    def _set_status(self, job_id: str, status: str, reason: str | None) -> None:
        row = self._job(job_id)
        payload = dict(row["payload"])
        payload["stop_reason"] = reason
        self.store.put("work_v2", job_id, payload, status=status, owner_id=row["owner_id"])

    def _job(self, job_id: str) -> dict[str, Any]:
        row = self.store.get("work_v2", job_id)
        if row is None:
            raise KeyError(job_id)
        return row

    def _step(self, job_id: str, step_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        row = self._job(job_id)
        payload = dict(row["payload"])
        payload["steps"] = [dict(item) for item in payload["steps"]]
        for step in payload["steps"]:
            if step["id"] == step_id:
                return row, payload, step
        raise KeyError(step_id)
