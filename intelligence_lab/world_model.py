from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import time
from typing import Any, Iterable

from .memory import LabMemory
from .models import Observation, new_id


@dataclass(frozen=True)
class TemporalFact:
    key: str
    value: Any
    confidence: float
    source: str
    evidence: tuple[str, ...] = ()
    observed_at: float = field(default_factory=time.time)
    valid_until: float | None = None
    id: str = field(default_factory=lambda: new_id("fact"))

    @property
    def expired(self) -> bool:
        return self.valid_until is not None and time.time() >= self.valid_until

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expired"] = self.expired
        return data


@dataclass(frozen=True)
class CausalRelation:
    cause: str
    effect: str
    relation: str
    strength: float
    evidence: tuple[str, ...]
    source: str = "lab"
    observed_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: new_id("relation"))

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class PersistentTemporalCausalWorldModel:
    """Lab-local temporal and evidence-labelled causal world model.

    Facts and relations are hypotheses/evidence records, never trusted Core
    state. Causal links require explicit evidence and are not treated as proof.
    """

    def __init__(self, memory: LabMemory, *, history_limit: int = 500):
        self.memory = memory
        self.history_limit = max(20, min(int(history_limit), 500))
        self._facts: dict[str, list[TemporalFact]] = {}
        self._relations: list[CausalRelation] = []
        self._load()

    def _load(self) -> None:
        for row in reversed(self.memory.recent("world_fact", self.history_limit)):
            payload = row.get("payload", {})
            try:
                fact = TemporalFact(
                    id=str(payload["id"]),
                    key=str(payload["key"]),
                    value=payload.get("value"),
                    confidence=float(payload.get("confidence", 0.0)),
                    source=str(payload.get("source", "unknown")),
                    evidence=tuple(payload.get("evidence") or ()),
                    observed_at=float(payload.get("observed_at", row.get("created_at", time.time()))),
                    valid_until=(
                        float(payload["valid_until"])
                        if payload.get("valid_until") is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._facts.setdefault(fact.key, []).append(fact)
        for row in reversed(self.memory.recent("world_relation", self.history_limit)):
            payload = row.get("payload", {})
            try:
                relation = CausalRelation(
                    id=str(payload["id"]),
                    cause=str(payload["cause"]),
                    effect=str(payload["effect"]),
                    relation=str(payload.get("relation", "influences")),
                    strength=float(payload.get("strength", 0.0)),
                    evidence=tuple(payload.get("evidence") or ()),
                    source=str(payload.get("source", "lab")),
                    observed_at=float(payload.get("observed_at", row.get("created_at", time.time()))),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._relations.append(relation)

    def ingest(self, observation: Observation, *, ttl_seconds: float | None = None) -> tuple[TemporalFact, ...]:
        valid_until = None
        if ttl_seconds is not None:
            ttl = max(0.0, float(ttl_seconds))
            valid_until = observation.created_at + ttl
        facts = []
        for key, value in observation.payload.items():
            facts.append(
                self.assert_fact(
                    str(key),
                    value,
                    confidence=observation.confidence,
                    source=observation.source,
                    evidence=(observation.id,),
                    observed_at=observation.created_at,
                    valid_until=valid_until,
                )
            )
        return tuple(facts)

    def assert_fact(
        self,
        key: str,
        value: Any,
        *,
        confidence: float,
        source: str,
        evidence: Iterable[str] = (),
        observed_at: float | None = None,
        valid_until: float | None = None,
    ) -> TemporalFact:
        key = str(key).strip()
        if not key:
            raise ValueError("world fact key is required")
        confidence = max(0.0, min(float(confidence), 1.0))
        clean_evidence = tuple(str(item).strip() for item in evidence if str(item).strip())
        fact = TemporalFact(
            key=key,
            value=value,
            confidence=confidence,
            source=str(source or "unknown")[:500],
            evidence=clean_evidence,
            observed_at=float(observed_at if observed_at is not None else time.time()),
            valid_until=valid_until,
        )
        previous = self.current(key)
        if previous is not None and previous.value != fact.value and previous.confidence >= 0.6 and fact.confidence >= 0.6:
            self.memory.audit(
                "world_model",
                "contradiction_observed",
                {"key": key, "previous_fact_id": previous.id, "new_fact_id": fact.id},
            )
        self._facts.setdefault(key, []).append(fact)
        self._facts[key] = self._facts[key][-self.history_limit :]
        self.memory.put(fact.id, "world_fact", fact.public_dict())
        return fact

    def relate(
        self,
        cause: str,
        effect: str,
        *,
        relation: str = "influences",
        strength: float,
        evidence: Iterable[str],
        source: str = "lab",
    ) -> CausalRelation:
        cause = str(cause).strip()
        effect = str(effect).strip()
        if not cause or not effect or cause == effect:
            raise ValueError("causal relation requires distinct cause and effect keys")
        clean_evidence = tuple(str(item).strip() for item in evidence if str(item).strip())
        if not clean_evidence:
            raise ValueError("causal relation requires explicit evidence")
        strength = max(0.0, min(float(strength), 1.0))
        item = CausalRelation(
            cause=cause,
            effect=effect,
            relation=str(relation or "influences")[:120],
            strength=strength,
            evidence=clean_evidence,
            source=str(source or "lab")[:500],
        )
        self._relations.append(item)
        self._relations = self._relations[-self.history_limit :]
        self.memory.put(item.id, "world_relation", item.public_dict())
        self.memory.audit(
            "world_model",
            "causal_relation_recorded",
            {"id": item.id, "cause": cause, "effect": effect, "strength": strength, "causality_proven": False},
        )
        return item

    def current(self, key: str) -> TemporalFact | None:
        active = [item for item in self._facts.get(str(key), ()) if not item.expired]
        if not active:
            return None
        return max(active, key=lambda item: (item.observed_at, item.confidence))

    def history(self, key: str, *, limit: int = 20) -> tuple[TemporalFact, ...]:
        return tuple(self._facts.get(str(key), ())[-max(1, min(int(limit), 100)) :])

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key in self._facts:
            fact = self.current(key)
            if fact is not None:
                result[key] = fact.public_dict()
        return result

    def contradictions(self, key: str | None = None) -> tuple[dict[str, Any], ...]:
        keys = (str(key),) if key is not None else tuple(self._facts)
        output: list[dict[str, Any]] = []
        for candidate in keys:
            facts = [item for item in self._facts.get(candidate, ()) if not item.expired and item.confidence >= 0.6]
            values: dict[str, list[str]] = {}
            for fact in facts:
                values.setdefault(repr(fact.value), []).append(fact.id)
            if len(values) > 1:
                output.append({"key": candidate, "competing_values": values, "resolved": False})
        return tuple(output)

    def causal_path(self, cause: str, effect: str, *, max_depth: int = 4, minimum_strength: float = 0.5) -> tuple[CausalRelation, ...]:
        cause = str(cause)
        effect = str(effect)
        max_depth = max(1, min(int(max_depth), 8))
        graph: dict[str, list[CausalRelation]] = {}
        for relation in self._relations:
            if relation.strength >= minimum_strength:
                graph.setdefault(relation.cause, []).append(relation)
        queue = deque([(cause, tuple())])
        visited = {cause}
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for relation in graph.get(node, ()): 
                next_path = (*path, relation)
                if relation.effect == effect:
                    return next_path
                if relation.effect not in visited:
                    visited.add(relation.effect)
                    queue.append((relation.effect, next_path))
        return ()

    def predict(self, effect: str) -> dict[str, Any]:
        incoming = [item for item in self._relations if item.effect == str(effect)]
        contributions = []
        for relation in incoming:
            fact = self.current(relation.cause)
            if fact is None:
                continue
            contributions.append(
                {
                    "relation_id": relation.id,
                    "cause": relation.cause,
                    "support": relation.strength * fact.confidence,
                    "evidence": list(relation.evidence),
                }
            )
        confidence = min(0.9, sum(item["support"] for item in contributions) / max(1, len(contributions)))
        return {
            "effect": str(effect),
            "contributors": contributions,
            "confidence": confidence,
            "causality_proven": False,
            "caveat": "This is an evidence-weighted Lab hypothesis, not proof of causation or a guaranteed future outcome.",
        }
