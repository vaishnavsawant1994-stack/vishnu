"""Comparable provider/model result analysis for Voice Lab."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComparisonCandidate:
    candidate_id: str
    fixture_ids: tuple[str, ...]
    metrics: tuple[tuple[str, float], ...]

    def metric_map(self) -> dict[str, float]:
        return dict(self.metrics)


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
            return {"comparable": False, "reason": "candidates must use the exact same ordered fixtures"}
        missing = {c.candidate_id: [m for m in self.metric_names if m not in c.metric_map()] for c in self.candidates}
        missing = {key: value for key, value in missing.items() if value}
        if missing:
            return {"comparable": False, "reason": "metrics are incomplete", "missing": missing}
        winners = {}
        for metric in self.metric_names:
            values = [(c.candidate_id, c.metric_map()[metric]) for c in self.candidates]
            chooser = min if metric in self.lower_is_better else max
            winners[metric] = chooser(values, key=lambda pair: pair[1])[0]
        return {"comparable": True, "fixtures": fixtures, "winners": winners,
                "values": {c.candidate_id: c.metric_map() for c in self.candidates}}
