from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


def _get_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in str(path).split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_path(value: dict[str, Any], path: str, new_value: Any) -> None:
    parts = str(path).split(".")
    current = value
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = new_value


class OutcomeSimulator:
    """Bounded digital-twin action models. Simulation never invokes an action."""

    COMPONENT = "sensorium_v3_outcome_simulator"

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "outcome-models", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS outcome_models(
                action_type TEXT PRIMARY KEY,
                preconditions_json TEXT NOT NULL,
                effects_json TEXT NOT NULL,
                reversible INTEGER NOT NULL,
                hazards_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )

    @staticmethod
    def _json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 128 * 1024:
            raise ValueError("outcome model is too large")
        return encoded

    def register_model(
        self,
        action_type: str,
        *,
        preconditions: list[dict[str, Any]],
        effects: list[dict[str, Any]],
        reversible: bool,
        hazards: list[str] | None = None,
        confidence: float = 0.7,
    ) -> dict[str, Any]:
        action = str(action_type or "").strip()
        if not action:
            raise ValueError("action type is required")
        if len(preconditions) > 128 or len(effects) > 128:
            raise ValueError("outcome model is too complex")
        for rule in [*preconditions, *effects]:
            if not isinstance(rule, dict) or not str(rule.get("path") or "").strip():
                raise ValueError("every precondition/effect requires a path")
        score = max(0.0, min(float(confidence), 1.0))
        with self._con() as con:
            con.execute(
                """INSERT INTO outcome_models(
                    action_type,preconditions_json,effects_json,reversible,hazards_json,confidence,updated_at
                ) VALUES(?,?,?,?,?,?,?) ON CONFLICT(action_type) DO UPDATE SET
                preconditions_json=excluded.preconditions_json,effects_json=excluded.effects_json,
                reversible=excluded.reversible,hazards_json=excluded.hazards_json,
                confidence=excluded.confidence,updated_at=excluded.updated_at""",
                (
                    action[:200],
                    self._json(preconditions),
                    self._json(effects),
                    int(bool(reversible)),
                    self._json((hazards or [])[:128]),
                    score,
                    time.time(),
                ),
            )
        return {"action_type": action[:200], "registered": True, "execution_authority": False}

    def simulate(
        self,
        action_type: str,
        *,
        current_state: dict[str, Any],
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = str(action_type or "").strip()
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM outcome_models WHERE action_type=?", (action,)
            ).fetchone()
        if row is None:
            raise KeyError("outcome model not found")
        preconditions = json.loads(row["preconditions_json"])
        effects = json.loads(row["effects_json"])
        failures: list[dict[str, Any]] = []
        for rule in preconditions:
            actual = _get_path(current_state, str(rule["path"]))
            expected = rule.get("equals")
            if actual != expected:
                failures.append({"path": rule["path"], "expected": expected, "actual": actual})
        predicted = copy.deepcopy(current_state)
        applied: list[dict[str, Any]] = []
        if not failures:
            for effect in effects:
                path = str(effect["path"])
                operation = str(effect.get("op") or "set")
                before = _get_path(predicted, path)
                if operation == "set":
                    after = effect.get("value")
                elif operation == "toggle":
                    after = not bool(before)
                elif operation == "increment":
                    after = float(before or 0) + float(effect.get("value", 1))
                else:
                    raise ValueError(f"unsupported effect operation: {operation}")
                _set_path(predicted, path, after)
                applied.append({"path": path, "before": before, "after": after})
        return {
            "action_type": action,
            "parameters": parameters or {},
            "preconditions_satisfied": not failures,
            "precondition_failures": failures,
            "predicted_state": predicted,
            "predicted_effects": applied,
            "reversible": bool(row["reversible"]),
            "hazards": json.loads(row["hazards_json"]),
            "confidence": float(row["confidence"]),
            "simulated_only": True,
            "action_authorized": False,
            "execution_authority": False,
        }

    @staticmethod
    def compare_expected_observed(
        expected_effects: list[dict[str, Any]],
        observed_state: dict[str, Any],
    ) -> dict[str, Any]:
        comparisons = []
        matched = 0
        for effect in expected_effects:
            path = str(effect.get("path") or "")
            expected = effect.get("after", effect.get("value"))
            observed = _get_path(observed_state, path)
            ok = observed == expected
            matched += int(ok)
            comparisons.append(
                {"path": path, "expected": expected, "observed": observed, "matched": ok}
            )
        return {
            "matched": matched,
            "total": len(comparisons),
            "success_ratio": matched / len(comparisons) if comparisons else 1.0,
            "comparisons": comparisons,
            "execution_authority": False,
        }
