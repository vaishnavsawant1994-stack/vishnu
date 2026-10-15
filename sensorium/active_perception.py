from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    sensor: str
    query: str
    expected_information_gain: float
    uncertainty_reduction: float
    privacy_cost: float = 0.0
    battery_cost: float = 0.0
    latency_ms: float = 0.0
    available: bool = True
    permitted: bool = False
    active_session: bool = False
    source_device_id: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ObservationCandidate":
        sensor = str(value.get("sensor") or "").strip().lower()
        query = str(value.get("query") or "").strip()
        if not sensor or not query:
            raise ValueError("observation candidate requires sensor and query")
        return cls(
            sensor=sensor[:80],
            query=query[:1000],
            expected_information_gain=max(0.0, min(float(value.get("expected_information_gain", 0.0)), 1.0)),
            uncertainty_reduction=max(0.0, min(float(value.get("uncertainty_reduction", 0.0)), 1.0)),
            privacy_cost=max(0.0, min(float(value.get("privacy_cost", 0.0)), 1.0)),
            battery_cost=max(0.0, min(float(value.get("battery_cost", 0.0)), 1.0)),
            latency_ms=max(0.0, min(float(value.get("latency_ms", 0.0)), 120_000.0)),
            available=bool(value.get("available", True)),
            permitted=bool(value.get("permitted", False)),
            active_session=bool(value.get("active_session", False)),
            source_device_id=(str(value.get("source_device_id")).strip()[:200] if value.get("source_device_id") else None),
        )


@dataclass(frozen=True, slots=True)
class RankedObservation:
    candidate: ObservationCandidate
    utility: float
    reasons: tuple[str, ...]

    def public(self) -> dict[str, Any]:
        return {
            "sensor": self.candidate.sensor,
            "query": self.candidate.query,
            "source_device_id": self.candidate.source_device_id,
            "utility": round(self.utility, 6),
            "expected_information_gain": self.candidate.expected_information_gain,
            "uncertainty_reduction": self.candidate.uncertainty_reduction,
            "privacy_cost": self.candidate.privacy_cost,
            "battery_cost": self.candidate.battery_cost,
            "latency_ms": self.candidate.latency_ms,
            "active_session": self.candidate.active_session,
            "reasons": list(self.reasons),
            "activation_authorized": False,
            "execution_authority": False,
        }


class ActivePerceptionPlanner:
    """Ranks the next useful observation without activating a sensor."""

    def __init__(self, *, events=None) -> None:
        self.events = events

    @staticmethod
    def _utility(candidate: ObservationCandidate, *, urgency: float) -> tuple[float, tuple[str, ...]]:
        latency_penalty = min(candidate.latency_ms / 10_000.0, 1.0)
        utility = (
            0.38 * candidate.expected_information_gain
            + 0.32 * candidate.uncertainty_reduction
            + 0.08 * urgency
            + (0.07 if candidate.active_session else 0.0)
            + (0.05 if candidate.available else -0.5)
            - 0.10 * candidate.privacy_cost
            - 0.07 * candidate.battery_cost
            - 0.05 * latency_penalty
        )
        reasons: list[str] = []
        if candidate.expected_information_gain >= 0.7:
            reasons.append("high information gain")
        if candidate.uncertainty_reduction >= 0.7:
            reasons.append("strong uncertainty reduction")
        if candidate.active_session:
            reasons.append("already has a temporary sensor session")
        if candidate.privacy_cost >= 0.6:
            reasons.append("high privacy cost")
        if candidate.battery_cost >= 0.6:
            reasons.append("high battery cost")
        if candidate.latency_ms >= 5_000:
            reasons.append("high latency")
        return max(-1.0, min(utility, 1.0)), tuple(reasons)

    def plan(
        self,
        question: str,
        *,
        candidates: Iterable[ObservationCandidate | dict[str, Any]],
        uncertainty: float = 0.5,
        urgency: float = 0.5,
        max_observations: int = 3,
    ) -> dict[str, Any]:
        purpose = str(question or "").strip()
        if not purpose:
            raise ValueError("active perception question is required")
        current_uncertainty = max(0.0, min(float(uncertainty), 1.0))
        urgency_score = max(0.0, min(float(urgency), 1.0))
        limit = max(1, min(int(max_observations), 8))

        ranked: list[RankedObservation] = []
        rejected: list[dict[str, Any]] = []
        for raw in candidates:
            candidate = raw if isinstance(raw, ObservationCandidate) else ObservationCandidate.from_mapping(raw)
            if not candidate.available:
                rejected.append({"sensor": candidate.sensor, "query": candidate.query, "reason": "unavailable"})
                continue
            if not candidate.permitted and not candidate.active_session:
                rejected.append(
                    {
                        "sensor": candidate.sensor,
                        "query": candidate.query,
                        "reason": "no current permission/session; planner cannot grant one",
                    }
                )
                continue
            utility, reasons = self._utility(candidate, urgency=urgency_score)
            utility -= (1.0 - current_uncertainty) * (candidate.privacy_cost + candidate.battery_cost) * 0.08
            ranked.append(RankedObservation(candidate, utility, reasons))

        ranked.sort(
            key=lambda row: (
                -row.utility,
                row.candidate.privacy_cost,
                row.candidate.battery_cost,
                row.candidate.latency_ms,
                row.candidate.sensor,
            )
        )
        selected = [row for row in ranked if row.utility > 0][:limit]
        result = {
            "question": purpose[:2000],
            "uncertainty": current_uncertainty,
            "selected": [row.public() for row in selected],
            "alternatives": [row.public() for row in ranked[len(selected): len(selected) + 8]],
            "rejected": rejected[:32],
            "activation_authorized": False,
            "execution_authority": False,
            "next_step": (
                "Request or use only the separately permitted sensor sessions in selected order; "
                "stop when uncertainty is sufficiently reduced."
                if selected
                else "Use memory/current world state or request explicit permission for a useful sensor; no sensor was activated."
            ),
        }
        if self.events is not None:
            self.events.emit(
                "sensorium.v3.active_perception.planned",
                question=purpose[:240],
                selected=[row.candidate.sensor for row in selected],
                activation_authorized=False,
                execution_authority=False,
            )
        return result
