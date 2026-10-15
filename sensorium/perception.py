from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def confidence_band(value: float) -> ConfidenceBand:
    score = max(0.0, min(float(value), 1.0))
    if score >= 0.8:
        return ConfidenceBand.HIGH
    if score >= 0.5:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


@dataclass(frozen=True, slots=True)
class PerceptionEvidence:
    modality: str
    source: str
    payload: dict[str, Any]
    captured_at: float = field(default_factory=time.time)
    confidence: float = 0.5
    freshness_seconds: float = 30.0
    uncertainty: tuple[str, ...] = ()
    sensitivity: str = "sensitive"
    instruction_trust: str = "untrusted"
    execution_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "modality", str(self.modality or "").strip().lower()[:80])
        object.__setattr__(self, "source", str(self.source or "unknown").strip()[:160])
        object.__setattr__(self, "confidence", max(0.0, min(float(self.confidence), 1.0)))
        object.__setattr__(self, "freshness_seconds", max(0.1, min(float(self.freshness_seconds), 86_400.0)))
        object.__setattr__(self, "captured_at", float(self.captured_at))
        object.__setattr__(self, "uncertainty", tuple(str(item)[:240] for item in self.uncertainty[:16]))
        object.__setattr__(self, "execution_authority", False)

    def age_seconds(self, *, now: float | None = None) -> float:
        return max(0.0, float(now or time.time()) - self.captured_at)

    def freshness(self, *, now: float | None = None) -> float:
        age = self.age_seconds(now=now)
        return math.exp(-age / self.freshness_seconds)

    def effective_confidence(self, *, now: float | None = None) -> float:
        return max(0.0, min(self.confidence * self.freshness(now=now), 1.0))

    def public(self, *, now: float | None = None) -> dict[str, Any]:
        effective = self.effective_confidence(now=now)
        return {
            "modality": self.modality,
            "source": self.source,
            "payload": dict(self.payload),
            "captured_at": self.captured_at,
            "age_seconds": self.age_seconds(now=now),
            "freshness": self.freshness(now=now),
            "confidence": self.confidence,
            "effective_confidence": effective,
            "confidence_band": confidence_band(effective).value,
            "uncertainty": list(self.uncertainty),
            "sensitivity": self.sensitivity,
            "instruction_trust": self.instruction_trust,
            "execution_authority": False,
        }


def bounded_evidence(
    *,
    modality: str,
    source: str,
    payload: dict[str, Any] | None,
    confidence: float = 0.5,
    freshness_seconds: float = 30.0,
    uncertainty: list[str] | tuple[str, ...] | None = None,
    captured_at: float | None = None,
    sensitivity: str = "sensitive",
) -> PerceptionEvidence:
    safe: dict[str, Any] = {}
    for key, value in list((payload or {}).items())[:128]:
        name = str(key)[:120]
        if name.lower() in {"base64", "data_url", "token", "credential", "secret", "api_key"}:
            continue
        if isinstance(value, str):
            safe[name] = value[:12_000]
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[name] = value
        elif isinstance(value, list):
            safe[name] = value[:64]
        elif isinstance(value, dict):
            safe[name] = dict(list(value.items())[:64])
    return PerceptionEvidence(
        modality=modality,
        source=source,
        payload=safe,
        captured_at=float(captured_at or time.time()),
        confidence=confidence,
        freshness_seconds=freshness_seconds,
        uncertainty=tuple(uncertainty or ()),
        sensitivity=str(sensitivity or "sensitive")[:40],
    )
