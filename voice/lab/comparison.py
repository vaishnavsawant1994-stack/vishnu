"""Comparable provider/model result analysis for Voice Lab."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComparisonCandidate:
    """One provider/model candidate evaluated against an identical fixture set.

    Numeric quality/latency metrics remain the ranking inputs.  Operational
    context is deliberately carried alongside those scores so a numerically
    strong candidate is never mistaken for an automatically suitable Vishnu
    runtime choice when its privacy, hardware, licensing, cost, or reliability
    characteristics are unknown.
    """

    candidate_id: str
    fixture_ids: tuple[str, ...]
    metrics: tuple[tuple[str, float], ...]
    privacy: str = "unspecified"
    hardware: str = "unspecified"
    licensing: str = "unspecified"
    cost: str = "unspecified"
    reliability: tuple[tuple[str, float], ...] = ()

    def metric_map(self) -> dict[str, float]:
        return dict(self.metrics)

    def reliability_map(self) -> dict[str, float]:
        return dict(self.reliability)

    def operational_context(self) -> dict[str, object]:
        return {
            "privacy": self.privacy,
            "hardware": self.hardware,
            "licensing": self.licensing,
            "cost": self.cost,
            "reliability": self.reliability_map(),
        }

    def missing_context(self) -> tuple[str, ...]:
        missing: list[str] = []
        values = {
            "privacy": self.privacy,
            "hardware": self.hardware,
            "licensing": self.licensing,
            "cost": self.cost,
        }
        for field, value in values.items():
            if value.strip().lower() in {"", "unspecified"}:
                missing.append(field)
        if not self.reliability:
            missing.append("reliability")
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class ProviderComparison:
    candidates: tuple[ComparisonCandidate, ...]
    metric_names: tuple[str, ...]
    lower_is_better: tuple[str, ...] = ()

    def evaluate(self) -> dict[str, object]:
        if len(self.candidates) < 2:
            return {"comparable": False, "reason": "at least two candidates are required"}
        fixtures = self.candidates[0].fixture_ids
        if any(item.fixture_ids != fixtures for item in self.candidates[1:]):
            return {
                "comparable": False,
                "reason": "candidates must use the exact same ordered fixtures",
            }
        missing = {
            candidate.candidate_id: [
                metric for metric in self.metric_names if metric not in candidate.metric_map()
            ]
            for candidate in self.candidates
        }
        missing = {key: value for key, value in missing.items() if value}
        if missing:
            return {"comparable": False, "reason": "metrics are incomplete", "missing": missing}

        winners: dict[str, str] = {}
        for metric in self.metric_names:
            values = [
                (candidate.candidate_id, candidate.metric_map()[metric])
                for candidate in self.candidates
            ]
            chooser = min if metric in self.lower_is_better else max
            winners[metric] = chooser(values, key=lambda pair: pair[1])[0]

        context = {
            candidate.candidate_id: candidate.operational_context()
            for candidate in self.candidates
        }
        missing_context: dict[str, tuple[str, ...]] = {}
        for candidate in self.candidates:
            missing_fields = candidate.missing_context()
            if missing_fields:
                missing_context[candidate.candidate_id] = missing_fields

        result: dict[str, object] = {
            "comparable": True,
            "fixtures": fixtures,
            "winners": winners,
            "values": {
                candidate.candidate_id: candidate.metric_map()
                for candidate in self.candidates
            },
            "context": context,
            "context_complete": not missing_context,
        }
        if missing_context:
            result["missing_context"] = missing_context
        return result
