from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


_BLOCKING_IMPACT = {"critical", "serious"}


@dataclass(frozen=True)
class AccessibilityViolation:
    rule_id: str
    impact: str
    description: str
    targets: tuple[str, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.impact.lower() in _BLOCKING_IMPACT


@dataclass(frozen=True)
class AccessibilityResult:
    violations: tuple[AccessibilityViolation, ...]
    passes: int = 0
    incomplete: int = 0

    @property
    def passed(self) -> bool:
        return not any(item.blocking for item in self.violations)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "passes": self.passes,
            "incomplete": self.incomplete,
            "violations": [
                {"rule_id": item.rule_id, "impact": item.impact, "description": item.description, "targets": list(item.targets), "blocking": item.blocking}
                for item in self.violations
            ],
        }

    @classmethod
    def from_axe(cls, payload: Mapping[str, object]) -> "AccessibilityResult":
        violations: list[AccessibilityViolation] = []
        for item in payload.get("violations", ()):  # type: ignore[union-attr]
            if not isinstance(item, Mapping):
                continue
            targets: list[str] = []
            for node in item.get("nodes", ()):  # type: ignore[union-attr]
                if isinstance(node, Mapping):
                    target = node.get("target", ())
                    if isinstance(target, (list, tuple)):
                        targets.extend(str(value) for value in target)
            violations.append(AccessibilityViolation(
                rule_id=str(item.get("id") or "unknown"),
                impact=str(item.get("impact") or "unknown"),
                description=str(item.get("description") or item.get("help") or ""),
                targets=tuple(dict.fromkeys(targets)),
            ))
        return cls(tuple(violations), passes=len(tuple(payload.get("passes", ()))), incomplete=len(tuple(payload.get("incomplete", ()))))
