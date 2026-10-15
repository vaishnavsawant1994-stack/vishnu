from __future__ import annotations

from collections import defaultdict, deque
import json
import sqlite3
import threading
import time
from typing import Any, Iterable

from .memory import LabMemory
from .models import Observation
from .world_model import CausalRelation, PersistentTemporalCausalWorldModel, TemporalFact


class IndexedWorldGraph:
    """Persistent SQL + in-memory indexes over the Phase-2 world model."""

    def __init__(self, world: PersistentTemporalCausalWorldModel, memory: LabMemory):
        self.world = world
        self.memory = memory
        self._lock = threading.RLock()
        self._outgoing: dict[str, list[CausalRelation]] = defaultdict(list)
        self._incoming: dict[str, list[CausalRelation]] = defaultdict(list)
        self._source_reliability: dict[str, float] = {}
        self._fact_count = 0
        self._relation_count = 0
        self._initialize()
        self.rebuild()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.memory.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=15000")
        return con

    def _initialize(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS lab_world_fact_index(
                    fact_id TEXT PRIMARY KEY,
                    fact_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    valid_until REAL,
                    confidence REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lab_world_fact_key_time
                    ON lab_world_fact_index(fact_key, observed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_lab_world_fact_source_time
                    ON lab_world_fact_index(source, observed_at DESC);

                CREATE TABLE IF NOT EXISTS lab_world_edge_index(
                    relation_id TEXT PRIMARY KEY,
                    cause TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    strength REAL NOT NULL,
                    source TEXT NOT NULL,
                    observed_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lab_world_edge_cause
                    ON lab_world_edge_index(cause, strength DESC);
                CREATE INDEX IF NOT EXISTS idx_lab_world_edge_effect
                    ON lab_world_edge_index(effect, strength DESC);

                CREATE TABLE IF NOT EXISTS lab_world_source_reliability(
                    source TEXT PRIMARY KEY,
                    reliability REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def rebuild(self) -> dict[str, int]:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM lab_world_fact_index")
            con.execute("DELETE FROM lab_world_edge_index")
            facts = 0
            for key, history in self.world._facts.items():
                for fact in history:
                    con.execute(
                        """INSERT OR REPLACE INTO lab_world_fact_index
                           (fact_id,fact_key,source,observed_at,valid_until,confidence)
                           VALUES(?,?,?,?,?,?)""",
                        (
                            fact.id,
                            key,
                            fact.source,
                            fact.observed_at,
                            fact.valid_until,
                            fact.confidence,
                        ),
                    )
                    facts += 1
            self._outgoing = defaultdict(list)
            self._incoming = defaultdict(list)
            for relation in self.world._relations:
                con.execute(
                    """INSERT OR REPLACE INTO lab_world_edge_index
                       (relation_id,cause,effect,strength,source,observed_at)
                       VALUES(?,?,?,?,?,?)""",
                    (
                        relation.id,
                        relation.cause,
                        relation.effect,
                        relation.strength,
                        relation.source,
                        relation.observed_at,
                    ),
                )
                self._outgoing[relation.cause].append(relation)
                self._incoming[relation.effect].append(relation)
            self._source_reliability = {
                str(row["source"]): float(row["reliability"])
                for row in con.execute(
                    "SELECT source,reliability FROM lab_world_source_reliability"
                )
            }
            self._fact_count = sum(len(history) for history in self.world._facts.values())
            self._relation_count = len(self.world._relations)
        return {"facts": facts, "relations": self._relation_count}

    def _ensure_fresh(self) -> None:
        fact_count = sum(len(history) for history in self.world._facts.values())
        relation_count = len(self.world._relations)
        if fact_count != self._fact_count or relation_count != self._relation_count:
            self.rebuild()

    def sync_fact(self, fact: TemporalFact) -> None:
        with self._lock:
            self._fact_count += 1
        with self._connect() as con:
            con.execute(
                """INSERT OR REPLACE INTO lab_world_fact_index
                   (fact_id,fact_key,source,observed_at,valid_until,confidence)
                   VALUES(?,?,?,?,?,?)""",
                (
                    fact.id,
                    fact.key,
                    fact.source,
                    fact.observed_at,
                    fact.valid_until,
                    fact.confidence,
                ),
            )

    def sync_relation(self, relation: CausalRelation) -> None:
        with self._lock:
            self._outgoing[relation.cause].append(relation)
            self._incoming[relation.effect].append(relation)
            self._relation_count += 1
        with self._connect() as con:
            con.execute(
                """INSERT OR REPLACE INTO lab_world_edge_index
                   (relation_id,cause,effect,strength,source,observed_at)
                   VALUES(?,?,?,?,?,?)""",
                (
                    relation.id,
                    relation.cause,
                    relation.effect,
                    relation.strength,
                    relation.source,
                    relation.observed_at,
                ),
            )

    def ingest(self, observation: Observation, *, ttl_seconds: float | None = None):
        facts = self.world.ingest(observation, ttl_seconds=ttl_seconds)
        for fact in facts:
            self.sync_fact(fact)
        return facts

    def assert_fact(self, *args: Any, **kwargs: Any) -> TemporalFact:
        fact = self.world.assert_fact(*args, **kwargs)
        self.sync_fact(fact)
        return fact

    def relate(self, *args: Any, **kwargs: Any) -> CausalRelation:
        relation = self.world.relate(*args, **kwargs)
        self.sync_relation(relation)
        return relation

    def set_source_reliability(self, source: str, reliability: float) -> None:
        source = str(source).strip()[:500]
        if not source:
            raise ValueError("source is required")
        score = max(0.0, min(float(reliability), 1.0))
        with self._lock:
            self._source_reliability[source] = score
        with self._connect() as con:
            con.execute(
                """INSERT INTO lab_world_source_reliability(source,reliability,updated_at)
                   VALUES(?,?,?)
                   ON CONFLICT(source) DO UPDATE SET
                     reliability=excluded.reliability,
                     updated_at=excluded.updated_at""",
                (source, score, time.time()),
            )

    def source_reliability(self, source: str) -> float:
        with self._lock:
            return self._source_reliability.get(str(source), 0.5)

    def causal_path(
        self,
        cause: str,
        effect: str,
        *,
        max_depth: int = 6,
        minimum_strength: float = 0.5,
    ) -> tuple[CausalRelation, ...]:
        self._ensure_fresh()
        cause = str(cause)
        effect = str(effect)
        max_depth = max(1, min(int(max_depth), 12))
        queue = deque([(cause, tuple())])
        visited = {cause}
        with self._lock:
            outgoing = {key: tuple(value) for key, value in self._outgoing.items()}
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for relation in outgoing.get(node, ()):
                effective = relation.strength * self.source_reliability(relation.source)
                if effective < minimum_strength:
                    continue
                next_path = (*path, relation)
                if relation.effect == effect:
                    return next_path
                if relation.effect not in visited:
                    visited.add(relation.effect)
                    queue.append((relation.effect, next_path))
        return ()

    def predict(self, effect: str) -> dict[str, Any]:
        self._ensure_fresh()
        with self._lock:
            incoming = tuple(self._incoming.get(str(effect), ()))
        contributions = []
        for relation in incoming:
            fact = self.world.current(relation.cause)
            if fact is None:
                continue
            source_weight = self.source_reliability(relation.source)
            support = relation.strength * fact.confidence * source_weight
            contributions.append(
                {
                    "relation_id": relation.id,
                    "cause": relation.cause,
                    "support": support,
                    "source_reliability": source_weight,
                    "evidence": list(relation.evidence),
                }
            )
        confidence = min(
            0.9,
            sum(item["support"] for item in contributions) / max(1, len(contributions)),
        )
        return {
            "effect": str(effect),
            "contributors": contributions,
            "confidence": confidence,
            "causality_proven": False,
            "indexed": True,
        }

    def stats(self) -> dict[str, Any]:
        self._ensure_fresh()
        with self._connect() as con:
            facts = con.execute("SELECT COUNT(*) FROM lab_world_fact_index").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM lab_world_edge_index").fetchone()[0]
        return {
            "facts_indexed": int(facts),
            "edges_indexed": int(edges),
            "sources_scored": len(self._source_reliability),
            "persistent_sql_indexes": True,
        }
