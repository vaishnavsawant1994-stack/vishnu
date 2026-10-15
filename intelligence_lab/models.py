from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import time
import uuid
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ExperimentStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PromotionStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    EVALUATED = "evaluated"
    VERIFIED = "verified"
    OWNER_APPROVED = "owner_approved"
    ELIGIBLE = "eligible"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Observation:
    source: str
    payload: dict[str, Any]
    sensitivity: str = "internal"
    confidence: float = 1.0
    id: str = field(default_factory=lambda: new_id("obs"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Thought:
    goal: str
    summary: str
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    confidence: float = 0.5
    strategy: str = "baseline"
    id: str = field(default_factory=lambda: new_id("thought"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanStep:
    index: int
    objective: str
    kind: str
    depends_on: tuple[int, ...] = ()
    reversible: bool = True


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: tuple[PlanStep, ...]
    horizon: str = "long"
    id: str = field(default_factory=lambda: new_id("plan"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        return data


@dataclass(frozen=True)
class ActionProposal:
    action: str
    parameters: dict[str, Any]
    rationale: str
    risk: str = "unknown"
    requested_by: str = "intelligence_lab"
    id: str = field(default_factory=lambda: new_id("proposal"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationResult:
    proposal_id: str
    predicted_effects: tuple[str, ...]
    risks: tuple[str, ...]
    assumptions: tuple[str, ...]
    confidence: float
    executed: bool = False
    id: str = field(default_factory=lambda: new_id("sim"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AffectEstimate:
    labels: tuple[str, ...]
    valence: float
    arousal: float
    confidence: float
    evidence: tuple[str, ...]
    caveat: str = "This is an uncertain context estimate, not a fact about the person's feelings."
    subjective_experience_claimed: bool = False

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationResult:
    subject_id: str
    scores: dict[str, float]
    passed: bool
    evidence: tuple[str, ...]
    failures: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: new_id("eval"))
    created_at: float = field(default_factory=time.time)

    @property
    def aggregate_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["aggregate_score"] = self.aggregate_score
        return data


@dataclass(frozen=True)
class PromotionRecord:
    subject_id: str
    evaluation_id: str | None = None
    verification_evidence: tuple[str, ...] = ()
    owner_approved: bool = False
    status: PromotionStatus = PromotionStatus.EXPERIMENTAL
    rejection_reason: str | None = None
    id: str = field(default_factory=lambda: new_id("promotion"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class Experiment:
    name: str
    hypothesis: str
    inputs: dict[str, Any]
    status: ExperimentStatus = ExperimentStatus.CREATED
    result: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: new_id("experiment"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
