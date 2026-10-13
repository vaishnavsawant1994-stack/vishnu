from __future__ import annotations

from typing import Any, Mapping

from .gap_detector import CapabilityGapDetector
from .models import CapabilityGap, CapabilityPlan, CapabilitySpec, GapSource
from .planner import CapabilityPlanner
from .spec_builder import CapabilitySpecBuilder
from .store import CapabilityForgeStore


class CapabilityForgeService:
    """F1 facade for non-executing capability-gap intelligence.

    F1 may observe, specify, classify and persist proposals. It deliberately has
    no method that installs, attaches, executes, activates, merges, or deploys a
    capability. Later Forge phases must cross existing Vishnu governance.
    """

    activation_allowed = False

    def __init__(self, store: CapabilityForgeStore, *, catalog=None, events=None):
        self.store = store
        self.events = events
        self.detector = CapabilityGapDetector(store)
        self.spec_builder = CapabilitySpecBuilder()
        self.planner = CapabilityPlanner(catalog=catalog)

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def observe_gap(self, source: str | GapSource, payload: Mapping[str, Any]) -> CapabilityGap | None:
        gap = self.detector.observe(source, payload)
        if gap is not None:
            self._emit(
                "capability_forge.gap_detected",
                gap_id=gap.id,
                source=gap.source.value,
                occurrences=gap.occurrences,
                summary=gap.summary,
            )
        return gap

    def specify(self, gap_id: str, requirements: Mapping[str, Any] | None = None) -> CapabilitySpec:
        gap = self.store.get_gap(str(gap_id))
        if gap is None:
            raise KeyError(gap_id)
        spec = self.spec_builder.build(gap, requirements)
        self.store.save_spec(spec)
        self._emit("capability_forge.spec_created", gap_id=gap.id, spec_id=spec.id, name=spec.name)
        return spec

    def plan(self, spec_id: str) -> CapabilityPlan:
        spec = self.store.get_spec(str(spec_id))
        if spec is None:
            raise KeyError(spec_id)
        plan = self.planner.plan(spec)
        self.store.save_plan(plan)
        self._emit(
            "capability_forge.plan_created",
            spec_id=spec.id,
            plan_id=plan.id,
            route=plan.route.value,
            risk=plan.risk.risk.value if plan.risk else None,
        )
        return plan

    def propose(
        self,
        source: str | GapSource,
        payload: Mapping[str, Any],
        *,
        requirements: Mapping[str, Any] | None = None,
    ) -> tuple[CapabilityGap, CapabilitySpec, CapabilityPlan] | None:
        gap = self.observe_gap(source, payload)
        if gap is None:
            return None
        spec = self.specify(gap.id, requirements)
        plan = self.plan(spec.id)
        return gap, spec, plan
