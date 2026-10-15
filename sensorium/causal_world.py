from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


WEIGHTS = {
    "observation": 0.07,
    "temporal_precedence": 0.10,
    "mechanism": 0.12,
    "intervention": 0.22,
    "replication": 0.14,
    "counterexample": -0.22,
    "confounder": -0.14,
}


class CausalWorldModel:
    """Durable cause/effect hypotheses. Predictions never authorize actions."""

    COMPONENT = "sensorium_v3_causal_world"

    def __init__(self, path: Path, *, world=None, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.world = world
        self.events = events
        with connect_sqlite(self.path) as con:
            run_migrations(con, component=self.COMPONENT, migrations=(Migration(1, "causal-world", self._migrate),))

    @staticmethod
    def _migrate(con) -> None:
        con.execute("""CREATE TABLE IF NOT EXISTS causal_hypotheses(
            hypothesis_id TEXT PRIMARY KEY, cause_json TEXT NOT NULL, effect_json TEXT NOT NULL,
            description TEXT NOT NULL, prior REAL NOT NULL, score REAL NOT NULL, status TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS causal_evidence(
            evidence_id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, evidence_type TEXT NOT NULL,
            supports INTEGER NOT NULL, confidence REAL NOT NULL, source TEXT NOT NULL,
            details_json TEXT NOT NULL, captured_at REAL NOT NULL,
            FOREIGN KEY(hypothesis_id) REFERENCES causal_hypotheses(hypothesis_id) ON DELETE CASCADE)""")

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("causal payload too large")
        return encoded

    def propose(self, cause: dict[str, Any], effect: dict[str, Any], *, description: str, prior: float = 0.5) -> dict[str, Any]:
        if not str(description).strip():
            raise ValueError("description is required")
        hypothesis_id = str(uuid.uuid4())
        score = max(0.01, min(float(prior), 0.99))
        now = time.time()
        with self._con() as con:
            con.execute(
                "INSERT INTO causal_hypotheses VALUES(?,?,?,?,?,?,?,?,?)",
                (hypothesis_id, self._json(cause), self._json(effect), str(description)[:2000], score, score, "hypothesis", now, now),
            )
        return self.hypothesis(hypothesis_id)

    def add_evidence(
        self,
        hypothesis_id: str,
        *,
        evidence_type: str,
        supports: bool,
        confidence: float,
        source: str,
        details: dict[str, Any] | None = None,
        captured_at: float | None = None,
    ) -> dict[str, Any]:
        kind = str(evidence_type).strip().lower()
        if kind not in WEIGHTS:
            raise ValueError("unsupported causal evidence type")
        confidence = max(0.0, min(float(confidence), 1.0))
        with self._con() as con:
            row = con.execute("SELECT score FROM causal_hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()
            if row is None:
                raise KeyError("causal hypothesis not found")
            delta = WEIGHTS[kind] * confidence
            if not supports:
                delta = -abs(delta)
            score = max(0.01, min(float(row["score"]) + delta, 0.99))
            status = "supported" if score >= 0.75 else "weak" if score < 0.35 else "hypothesis"
            con.execute(
                "INSERT INTO causal_evidence VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), hypothesis_id, kind, int(bool(supports)), confidence, str(source)[:200], self._json(details or {}), float(captured_at or time.time())),
            )
            con.execute("UPDATE causal_hypotheses SET score=?,status=?,updated_at=? WHERE hypothesis_id=?", (score, status, time.time(), hypothesis_id))
        return self.hypothesis(hypothesis_id)

    def hypothesis(self, hypothesis_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM causal_hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()
            if row is None:
                raise KeyError("causal hypothesis not found")
            evidence_rows = con.execute("SELECT * FROM causal_evidence WHERE hypothesis_id=? ORDER BY captured_at", (hypothesis_id,)).fetchall()
        evidence = []
        intervention_supported = False
        for item in evidence_rows:
            public = dict(item)
            public["supports"] = bool(public["supports"])
            public["details"] = json.loads(public.pop("details_json"))
            intervention_supported |= public["evidence_type"] == "intervention" and public["supports"]
            evidence.append(public)
        return {
            "hypothesis_id": row["hypothesis_id"],
            "cause": json.loads(row["cause_json"]),
            "effect": json.loads(row["effect_json"]),
            "description": row["description"],
            "prior": row["prior"],
            "score": row["score"],
            "status": row["status"],
            "causal_basis": "intervention-supported" if intervention_supported else "observational-hypothesis",
            "evidence": evidence,
            "execution_authority": False,
        }

    def list_hypotheses(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT hypothesis_id FROM causal_hypotheses ORDER BY updated_at DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
        return [self.hypothesis(str(row["hypothesis_id"])) for row in rows]

    def counterfactual(self, hypothesis_id: str, *, intervention: dict[str, Any], assume_no_unmodeled_causes: bool = False) -> dict[str, Any]:
        hypothesis = self.hypothesis(hypothesis_id)
        matches = all(hypothesis["cause"].get(k) == v for k, v in intervention.items() if k in hypothesis["cause"])
        probability = float(hypothesis["score"]) if matches else 1.0 - float(hypothesis["score"])
        if not assume_no_unmodeled_causes:
            probability = 0.5 + (probability - 0.5) * 0.75
        return {
            "hypothesis_id": hypothesis_id,
            "intervention": intervention,
            "predicted_effect": hypothesis["effect"],
            "predicted_probability": max(0.01, min(probability, 0.99)),
            "causal_basis": hypothesis["causal_basis"],
            "action_authorized": False,
            "execution_authority": False,
        }
