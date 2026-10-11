from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import EngineeringSpec


class DefectDetector(Protocol):
    def detect(self, *, spec: EngineeringSpec) -> tuple[Any, ...]: ...


class RepairProvider(Protocol):
    def repair(self, *, spec: EngineeringSpec, defects: tuple[Any, ...], cycle: int) -> Any: ...


class RepairVerifier(Protocol):
    def verify(self, *, spec: EngineeringSpec, cycle: int) -> bool: ...


@dataclass(frozen=True)
class RepairCycle:
    cycle: int
    defect_count: int
    repaired: bool
    verified: bool


@dataclass(frozen=True)
class RepairOutcome:
    status: str
    cycles: tuple[RepairCycle, ...]
    remaining_defects: int
    needs_attention: bool


class BoundedEngineeringRepairLoop:
    """Defect -> repair -> verify loop; never approves, merges, deploys or activates."""

    def __init__(self, *, detector: DefectDetector, repairer: RepairProvider, verifier: RepairVerifier) -> None:
        self.detector = detector
        self.repairer = repairer
        self.verifier = verifier

    def run(self, spec: EngineeringSpec) -> RepairOutcome:
        maximum = spec.budget.max_repair_cycles
        history: list[RepairCycle] = []
        defects = tuple(self.detector.detect(spec=spec))
        if not defects:
            return RepairOutcome("clean", (), 0, False)
        if maximum <= 0:
            return RepairOutcome("needs_attention", (), len(defects), True)
        for cycle in range(1, maximum + 1):
            result = self.repairer.repair(spec=spec, defects=defects, cycle=cycle)
            repaired = result is not False and result is not None
            verified = bool(self.verifier.verify(spec=spec, cycle=cycle)) if repaired else False
            history.append(RepairCycle(cycle, len(defects), repaired, verified))
            if not repaired:
                return RepairOutcome("needs_attention", tuple(history), len(defects), True)
            defects = tuple(self.detector.detect(spec=spec))
            if verified and not defects:
                return RepairOutcome("repaired", tuple(history), 0, False)
        return RepairOutcome("needs_attention", tuple(history), len(defects), True)
