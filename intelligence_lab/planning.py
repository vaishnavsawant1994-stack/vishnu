from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import time
from typing import Any, Iterable, Mapping

from .memory import LabMemory
from .models import Plan, PlanStep, Thought, new_id


@dataclass(frozen=True)
class PlanningBudget:
    max_cycles: int = 64
    max_failures: int = 8
    max_actions: int = 64
    deadline_at: float | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdaptivePlanSession:
    goal: str
    plan: Plan
    success_criteria: tuple[str, ...]
    budget: PlanningBudget
    current_step: int = 0
    cycles: int = 0
    failures: int = 0
    actions_proposed: int = 0
    status: str = "running"
    evidence: tuple[str, ...] = ()
    version: int = 1
    id: str = field(default_factory=lambda: new_id("longplan"))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "plan": self.plan.public_dict(),
            "success_criteria": list(self.success_criteria),
            "budget": self.budget.public_dict(),
            "current_step": self.current_step,
            "cycles": self.cycles,
            "failures": self.failures,
            "actions_proposed": self.actions_proposed,
            "status": self.status,
            "evidence": list(self.evidence),
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AdaptiveLongHorizonPlanner:
    """Persistent, bounded multi-session planning without autonomous looping.

    The planner can resume, checkpoint and replan, but it never executes a tool.
    A host must explicitly ask for the next step or send a proposal through the
    Core bridge.
    """

    def __init__(
        self,
        base_planner: Any,
        memory: LabMemory,
        *,
        max_cycles: int = 64,
        max_failures: int = 8,
        max_actions: int = 64,
    ):
        self.base_planner = base_planner
        self.memory = memory
        self.defaults = PlanningBudget(
            max_cycles=max(1, min(int(max_cycles), 512)),
            max_failures=max(1, min(int(max_failures), 64)),
            max_actions=max(1, min(int(max_actions), 512)),
        )

    @staticmethod
    def _criteria(values: Iterable[str]) -> tuple[str, ...]:
        return tuple(str(item).strip() for item in values if str(item).strip())

    def start(
        self,
        goal: str,
        *,
        thought: Thought | None = None,
        success_criteria: Iterable[str] = (),
        budget: PlanningBudget | None = None,
    ) -> AdaptivePlanSession:
        goal = str(goal).strip()
        if not goal:
            raise ValueError("goal is required")
        criteria = self._criteria(success_criteria)
        plan = self.base_planner.plan(goal, thought)
        session = AdaptivePlanSession(
            goal=goal,
            plan=plan,
            success_criteria=criteria,
            budget=budget or self.defaults,
        )
        self._store(session, "started")
        return session

    def next_step(self, session: AdaptivePlanSession) -> PlanStep | None:
        self._assert_live(session)
        if session.current_step >= len(session.plan.steps):
            return None
        return session.plan.steps[session.current_step]

    def checkpoint(
        self,
        session: AdaptivePlanSession,
        *,
        evidence: Iterable[str],
        success_criteria_met: bool = False,
        action_proposed: bool = False,
    ) -> AdaptivePlanSession:
        self._assert_live(session)
        clean = self._criteria(evidence)
        if not clean:
            raise ValueError("checkpoint evidence is required")
        cycles = session.cycles + 1
        actions = session.actions_proposed + int(bool(action_proposed))
        next_index = min(session.current_step + 1, len(session.plan.steps))
        status = "completed" if success_criteria_met or next_index >= len(session.plan.steps) else "running"
        updated = replace(
            session,
            current_step=next_index,
            cycles=cycles,
            actions_proposed=actions,
            status=status,
            evidence=(*session.evidence, *clean)[-200:],
            updated_at=time.time(),
        )
        updated = self._enforce_budget(updated)
        self._store(updated, "checkpoint")
        return updated

    def fail_and_replan(
        self,
        session: AdaptivePlanSession,
        *,
        reason: str,
        evidence: Iterable[str] = (),
    ) -> AdaptivePlanSession:
        self._assert_live(session)
        reason = str(reason).strip()
        if not reason:
            raise ValueError("failure reason is required")
        failures = session.failures + 1
        cycles = session.cycles + 1
        if failures > session.budget.max_failures:
            blocked = replace(
                session,
                failures=failures,
                cycles=cycles,
                status="blocked",
                evidence=(*session.evidence, *self._criteria(evidence))[-200:],
                updated_at=time.time(),
            )
            self._store(blocked, "failure_budget_exhausted")
            return blocked
        replanned = self.base_planner.replan(
            session.plan,
            failed_step=min(session.current_step, max(0, len(session.plan.steps) - 1)),
            reason=reason,
        )
        updated = replace(
            session,
            plan=replanned,
            current_step=0,
            failures=failures,
            cycles=cycles,
            version=session.version + 1,
            evidence=(*session.evidence, *self._criteria(evidence))[-200:],
            updated_at=time.time(),
        )
        updated = self._enforce_budget(updated)
        self._store(updated, "replanned")
        return updated

    def pause(self, session: AdaptivePlanSession, *, evidence: Iterable[str] = ()) -> AdaptivePlanSession:
        if session.status not in {"running", "paused"}:
            raise PermissionError("only a running or paused plan can be paused")
        updated = replace(
            session,
            status="paused",
            evidence=(*session.evidence, *self._criteria(evidence))[-200:],
            updated_at=time.time(),
        )
        self._store(updated, "paused")
        return updated

    def resume(self, session: AdaptivePlanSession) -> AdaptivePlanSession:
        if session.status != "paused":
            raise PermissionError("only a paused plan can be resumed")
        updated = replace(session, status="running", updated_at=time.time())
        updated = self._enforce_budget(updated)
        self._store(updated, "resumed")
        return updated

    def _assert_live(self, session: AdaptivePlanSession) -> None:
        if session.status not in {"running", "paused"}:
            raise PermissionError(f"plan is {session.status}")
        if session.status == "paused":
            raise PermissionError("plan is paused")

    def _enforce_budget(self, session: AdaptivePlanSession) -> AdaptivePlanSession:
        exhausted = (
            session.cycles > session.budget.max_cycles
            or session.actions_proposed > session.budget.max_actions
            or (
                session.budget.deadline_at is not None
                and time.time() >= float(session.budget.deadline_at)
            )
        )
        if exhausted and session.status == "running":
            return replace(session, status="blocked", updated_at=time.time())
        return session

    def _store(self, session: AdaptivePlanSession, action: str) -> None:
        self.memory.put(session.id, "adaptive_plan", session.public_dict())
        self.memory.audit(
            "planning",
            action,
            {
                "id": session.id,
                "version": session.version,
                "status": session.status,
                "cycles": session.cycles,
                "failures": session.failures,
                "tool_executed": False,
            },
        )

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> AdaptivePlanSession:
        plan_payload = payload["plan"]
        plan = Plan(
            id=str(plan_payload["id"]),
            goal=str(plan_payload["goal"]),
            horizon=str(plan_payload.get("horizon", "long")),
            created_at=float(plan_payload.get("created_at", time.time())),
            steps=tuple(
                PlanStep(
                    index=int(item["index"]),
                    objective=str(item["objective"]),
                    kind=str(item["kind"]),
                    depends_on=tuple(int(value) for value in item.get("depends_on", ())),
                    reversible=bool(item.get("reversible", True)),
                )
                for item in plan_payload.get("steps", ())
            ),
        )
        budget_payload = payload.get("budget", {})
        budget = PlanningBudget(
            max_cycles=int(budget_payload.get("max_cycles", 64)),
            max_failures=int(budget_payload.get("max_failures", 8)),
            max_actions=int(budget_payload.get("max_actions", 64)),
            deadline_at=budget_payload.get("deadline_at"),
        )
        return AdaptivePlanSession(
            id=str(payload["id"]),
            goal=str(payload["goal"]),
            plan=plan,
            success_criteria=tuple(payload.get("success_criteria", ())),
            budget=budget,
            current_step=int(payload.get("current_step", 0)),
            cycles=int(payload.get("cycles", 0)),
            failures=int(payload.get("failures", 0)),
            actions_proposed=int(payload.get("actions_proposed", 0)),
            status=str(payload.get("status", "running")),
            evidence=tuple(payload.get("evidence", ())),
            version=int(payload.get("version", 1)),
            created_at=float(payload.get("created_at", time.time())),
            updated_at=float(payload.get("updated_at", time.time())),
        )
