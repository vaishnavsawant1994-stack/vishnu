from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


class ProceduralMemory:
    """Owner-saved procedures learned from one or more demonstrations."""

    COMPONENT = "sensorium_v3_procedural_memory"

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "procedural-memory", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS procedures(
                procedure_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                prerequisites_json TEXT NOT NULL,
                safety_json TEXT NOT NULL,
                checkpoints_json TEXT NOT NULL,
                demonstration_count INTEGER NOT NULL,
                source_devices_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS procedure_steps(
                step_id TEXT PRIMARY KEY,
                procedure_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                action TEXT NOT NULL,
                objects_json TEXT NOT NULL,
                expected_state_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                UNIQUE(procedure_id,step_index),
                FOREIGN KEY(procedure_id) REFERENCES procedures(procedure_id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 128 * 1024:
            raise ValueError("procedure payload too large")
        return encoded

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    @staticmethod
    def _extract_steps(demonstration: dict[str, Any]) -> list[dict[str, Any]]:
        raw_steps = demonstration.get("steps") or demonstration.get("events") or []
        if not isinstance(raw_steps, list):
            raise ValueError("demonstration steps must be a list")
        result: list[dict[str, Any]] = []
        for raw in raw_steps[:256]:
            if not isinstance(raw, dict):
                continue
            action = str(raw.get("action") or raw.get("description") or "").strip()
            if not action:
                continue
            result.append(
                {
                    "action": action[:1000],
                    "objects": list(raw.get("objects") or [])[:32],
                    "expected_state": dict(raw.get("expected_state") or {}),
                }
            )
        return result

    def learn(
        self,
        name: str,
        *,
        demonstrations: list[dict[str, Any]],
        description: str = "",
        prerequisites: list[str] | None = None,
        safety_conditions: list[str] | None = None,
        checkpoints: list[str] | None = None,
        source_devices: list[str] | None = None,
        explicit_owner_save: bool = False,
    ) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("procedure name is required")
        if not explicit_owner_save:
            raise PermissionError("explicit owner save is required for procedural memory")
        if not demonstrations or len(demonstrations) > 32:
            raise ValueError("one to 32 demonstrations are required")
        extracted = [self._extract_steps(item) for item in demonstrations]
        if not any(extracted):
            raise ValueError("demonstrations contain no learnable steps")

        max_steps = max(len(sequence) for sequence in extracted)
        learned: list[dict[str, Any]] = []
        for index in range(max_steps):
            candidates = [sequence[index] for sequence in extracted if index < len(sequence)]
            actions = Counter(item["action"] for item in candidates)
            action, count = actions.most_common(1)[0]
            representative = next(item for item in candidates if item["action"] == action)
            learned.append(
                {
                    "action": action,
                    "objects": representative["objects"],
                    "expected_state": representative["expected_state"],
                    "confidence": count / len(candidates),
                }
            )

        procedure_id = str(uuid.uuid4())
        now = time.time()
        with self._con() as con:
            con.execute(
                """INSERT INTO procedures(
                    procedure_id,name,description,prerequisites_json,safety_json,checkpoints_json,
                    demonstration_count,source_devices_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    procedure_id,
                    clean_name[:240],
                    str(description or "")[:4000],
                    self._json((prerequisites or [])[:128]),
                    self._json((safety_conditions or [])[:128]),
                    self._json((checkpoints or [])[:128]),
                    len(demonstrations),
                    self._json((source_devices or [])[:64]),
                    now,
                    now,
                ),
            )
            for index, step in enumerate(learned, start=1):
                con.execute(
                    "INSERT INTO procedure_steps VALUES(?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        procedure_id,
                        index,
                        step["action"],
                        self._json(step["objects"]),
                        self._json(step["expected_state"]),
                        float(step["confidence"]),
                    ),
                )
        self._emit(
            "sensorium.v3.procedure.learned",
            procedure_id=procedure_id,
            demonstration_count=len(demonstrations),
            execution_authority=False,
        )
        return self.get(procedure_id)

    def get(self, procedure_id: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM procedures WHERE procedure_id=?", (procedure_id,)
            ).fetchone()
            if row is None:
                raise KeyError("procedure not found")
            steps = [
                dict(item)
                for item in con.execute(
                    "SELECT * FROM procedure_steps WHERE procedure_id=? ORDER BY step_index",
                    (procedure_id,),
                ).fetchall()
            ]
        procedure = dict(row)
        procedure["prerequisites"] = json.loads(procedure.pop("prerequisites_json"))
        procedure["safety_conditions"] = json.loads(procedure.pop("safety_json"))
        procedure["checkpoints"] = json.loads(procedure.pop("checkpoints_json"))
        procedure["source_devices"] = json.loads(procedure.pop("source_devices_json"))
        for step in steps:
            step["objects"] = json.loads(step.pop("objects_json"))
            step["expected_state"] = json.loads(step.pop("expected_state_json"))
        return {
            "procedure": procedure,
            "steps": steps,
            "execution_authority": False,
            "note": "Learning a procedure does not authorize Vishnu to execute it.",
        }

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 500))
        with self._con() as con:
            rows = con.execute(
                "SELECT procedure_id FROM procedures ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self.get(str(row["procedure_id"])) for row in rows]
