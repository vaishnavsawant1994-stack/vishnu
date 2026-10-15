from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Iterable, Mapping

from .memory import LabMemory
from .models import Plan, PlanStep, new_id
from .performance import PerformanceTelemetry


@dataclass(frozen=True)
class DAGNode:
    id: str
    index: int
    objective: str
    kind: str
    depends_on: tuple[str, ...]
    reversible: bool
    parallel_safe: bool


@dataclass(frozen=True)
class DAGPlan:
    goal: str
    nodes: tuple[DAGNode, ...]
    waves: tuple[tuple[str, ...], ...]
    id: str = field(default_factory=lambda: new_id("dag"))

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "nodes": [
                {
                    "id": item.id,
                    "index": item.index,
                    "objective": item.objective,
                    "kind": item.kind,
                    "depends_on": list(item.depends_on),
                    "reversible": item.reversible,
                    "parallel_safe": item.parallel_safe,
                }
                for item in self.nodes
            ],
            "waves": [list(wave) for wave in self.waves],
        }


class ParallelDAGPlanner:
    """Dependency-aware parallel planner; execution authority stays outside."""

    DEFAULT_PARALLEL_SAFE = frozenset(
        {"observe", "read", "reason", "research", "verify", "simulate", "analysis"}
    )

    def __init__(
        self,
        memory: LabMemory,
        telemetry: PerformanceTelemetry,
        *,
        max_workers: int = 4,
        parallel_safe_kinds: Iterable[str] | None = None,
    ):
        self.memory = memory
        self.telemetry = telemetry
        self.max_workers = max(1, min(int(max_workers), 32))
        self.parallel_safe_kinds = frozenset(
            str(item)
            for item in (parallel_safe_kinds or self.DEFAULT_PARALLEL_SAFE)
        )

    def from_plan(self, plan: Plan) -> DAGPlan:
        id_by_index = {step.index: f"{plan.id}:{step.index}" for step in plan.steps}
        nodes = tuple(
            DAGNode(
                id=id_by_index[step.index],
                index=step.index,
                objective=step.objective,
                kind=str(step.kind),
                depends_on=tuple(
                    id_by_index[value]
                    for value in step.depends_on
                    if value in id_by_index
                ),
                reversible=bool(step.reversible),
                parallel_safe=(
                    bool(step.reversible)
                    and str(step.kind).lower() in self.parallel_safe_kinds
                ),
            )
            for step in plan.steps
        )
        waves = self._waves(nodes)
        dag = DAGPlan(goal=plan.goal, nodes=nodes, waves=waves)
        self.memory.put(dag.id, "dag_plan", dag.public_dict())
        return dag

    @staticmethod
    def _waves(nodes: tuple[DAGNode, ...]) -> tuple[tuple[str, ...], ...]:
        by_id = {node.id: node for node in nodes}
        remaining = set(by_id)
        completed: set[str] = set()
        waves: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(
                sorted(
                    (
                        node_id
                        for node_id in remaining
                        if set(by_id[node_id].depends_on).issubset(completed)
                    ),
                    key=lambda node_id: by_id[node_id].index,
                )
            )
            if not ready:
                raise ValueError("plan dependency graph contains a cycle or missing dependency")
            waves.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)
        return tuple(waves)

    def run(
        self,
        dag: DAGPlan,
        worker: Callable[[DAGNode], Any],
        *,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        by_id = {node.id: node for node in dag.nodes}
        results: dict[str, Any] = {}
        failures: dict[str, str] = {}
        started = time.perf_counter()
        for wave in dag.waves:
            nodes = [by_id[node_id] for node_id in wave]
            parallel = [node for node in nodes if node.parallel_safe]
            serial = [node for node in nodes if not node.parallel_safe]
            if parallel:
                with ThreadPoolExecutor(
                    max_workers=min(self.max_workers, len(parallel))
                ) as pool:
                    futures = {pool.submit(worker, node): node for node in parallel}
                    for future in as_completed(futures):
                        node = futures[future]
                        try:
                            results[node.id] = future.result()
                        except Exception as exc:
                            failures[node.id] = type(exc).__name__
            for node in serial:
                try:
                    results[node.id] = worker(node)
                except Exception as exc:
                    failures[node.id] = type(exc).__name__
            if failures and stop_on_failure:
                break
        latency_ms = (time.perf_counter() - started) * 1000.0
        self.telemetry.record(
            "dag_run",
            latency_ms,
            success=not failures,
            metadata={
                "nodes": len(dag.nodes),
                "waves": len(dag.waves),
                "max_workers": self.max_workers,
            },
        )
        outcome = {
            "dag_id": dag.id,
            "results": results,
            "failures": failures,
            "completed": len(results),
            "total": len(dag.nodes),
            "parallel_execution_authority": False,
            "worker_must_use_core_for_real_actions": True,
        }
        self.memory.audit(
            "planning",
            "dag_run_completed",
            {
                "dag_id": dag.id,
                "completed": len(results),
                "failures": len(failures),
                "core_authority_bypassed": False,
            },
        )
        return outcome
