from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations
from sensorium.perception import confidence_band


@dataclass(frozen=True, slots=True)
class WorldObservation:
    observation_id: str
    entity_id: str
    attribute: str
    value: Any
    source: str
    modality: str
    captured_at: float
    confidence: float
    freshness_seconds: float
    contradicted: bool

    def public(self, *, now: float | None = None) -> dict[str, Any]:
        current = float(now or time.time())
        age = max(0.0, current - self.captured_at)
        freshness = pow(2.718281828, -age / max(self.freshness_seconds, 0.1))
        effective = max(0.0, min(self.confidence * freshness, 1.0))
        return {
            "observation_id": self.observation_id,
            "entity_id": self.entity_id,
            "attribute": self.attribute,
            "value": self.value,
            "source": self.source,
            "modality": self.modality,
            "captured_at": self.captured_at,
            "age_seconds": age,
            "freshness": freshness,
            "confidence": self.confidence,
            "effective_confidence": effective,
            "confidence_band": confidence_band(effective).value,
            "contradicted": self.contradicted,
            "execution_authority": False,
        }


class TemporalWorldModel:
    """Durable semantic world state built from time-bounded sensor evidence.

    This model stores semantic observations and relationships, not raw camera or
    microphone media. New evidence may supersede or contradict older evidence;
    contradictions remain visible for audit and reasoning instead of being
    silently overwritten.
    """

    COMPONENT = "sensorium_world_model"

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "temporal-world-model", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS world_entities(
                entity_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS world_observations(
                observation_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source TEXT NOT NULL,
                modality TEXT NOT NULL,
                captured_at REAL NOT NULL,
                confidence REAL NOT NULL,
                freshness_seconds REAL NOT NULL,
                contradicted INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(entity_id) REFERENCES world_entities(entity_id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS world_relations(
                relation_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL,
                source TEXT NOT NULL,
                captured_at REAL NOT NULL,
                confidence REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_world_observation_lookup ON world_observations(entity_id,attribute,captured_at DESC)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_world_relation_lookup ON world_relations(subject_id,predicate,captured_at DESC)"
        )

    @staticmethod
    def _identifier(value: str, *, field: str, limit: int = 160) -> str:
        clean = str(value or "").strip()
        if not clean or len(clean) > limit or any(ord(ch) < 32 for ch in clean):
            raise ValueError(f"invalid {field}")
        return clean

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def ensure_entity(self, entity_id: str, *, kind: str = "object", label: str | None = None) -> dict:
        entity = self._identifier(entity_id, field="entity ID")
        entity_kind = self._identifier(kind, field="entity kind", limit=80)
        entity_label = self._identifier(label or entity, field="entity label", limit=240)
        now = time.time()
        with self._con() as con:
            con.execute(
                """INSERT INTO world_entities(entity_id,kind,label,created_at,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET
                   kind=excluded.kind,label=excluded.label,updated_at=excluded.updated_at""",
                (entity, entity_kind, entity_label, now, now),
            )
        return {"entity_id": entity, "kind": entity_kind, "label": entity_label}

    def observe(
        self,
        entity_id: str,
        *,
        attribute: str,
        value: Any,
        source: str,
        modality: str,
        confidence: float = 0.7,
        freshness_seconds: float = 30.0,
        captured_at: float | None = None,
        kind: str = "object",
        label: str | None = None,
    ) -> dict:
        entity = self.ensure_entity(entity_id, kind=kind, label=label)["entity_id"]
        attr = self._identifier(attribute, field="attribute", limit=120)
        src = self._identifier(source, field="source", limit=160)
        mode = self._identifier(modality, field="modality", limit=80)
        score = max(0.0, min(float(confidence), 1.0))
        freshness = max(0.1, min(float(freshness_seconds), 86_400.0))
        timestamp = float(captured_at or time.time())
        try:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("world observation value must be JSON serializable") from exc
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("world observation value is too large")
        observation_id = str(uuid.uuid4())
        contradictions: list[str] = []
        with self._con() as con:
            previous = con.execute(
                """SELECT observation_id,value_json,confidence,captured_at,freshness_seconds
                   FROM world_observations WHERE entity_id=? AND attribute=? AND contradicted=0
                   ORDER BY captured_at DESC LIMIT 8""",
                (entity, attr),
            ).fetchall()
            for row in previous:
                if row["value_json"] == encoded:
                    continue
                age = max(0.0, timestamp - float(row["captured_at"]))
                still_fresh = age <= float(row["freshness_seconds"]) * 2
                if still_fresh and float(row["confidence"]) >= 0.5 and score >= 0.5:
                    contradictions.append(str(row["observation_id"]))
                    con.execute(
                        "UPDATE world_observations SET contradicted=1 WHERE observation_id=?",
                        (row["observation_id"],),
                    )
            con.execute(
                """INSERT INTO world_observations(
                    observation_id,entity_id,attribute,value_json,source,modality,captured_at,
                    confidence,freshness_seconds,contradicted
                ) VALUES(?,?,?,?,?,?,?,?,?,0)""",
                (observation_id, entity, attr, encoded, src, mode, timestamp, score, freshness),
            )
            con.execute("UPDATE world_entities SET updated_at=? WHERE entity_id=?", (time.time(), entity))
        self._emit(
            "sensorium.world.observed",
            observation_id=observation_id,
            entity_id=entity,
            attribute=attr,
            source=src,
            modality=mode,
            confidence=score,
            contradictions=len(contradictions),
            execution_authority=False,
        )
        return {
            "observation_id": observation_id,
            "entity_id": entity,
            "attribute": attr,
            "contradictions": contradictions,
            "execution_authority": False,
        }

    def relate(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        source: str,
        confidence: float = 0.7,
        captured_at: float | None = None,
    ) -> dict:
        subject = self.ensure_entity(subject_id)["entity_id"]
        obj = self.ensure_entity(object_id)["entity_id"]
        pred = self._identifier(predicate, field="predicate", limit=120)
        src = self._identifier(source, field="source", limit=160)
        score = max(0.0, min(float(confidence), 1.0))
        timestamp = float(captured_at or time.time())
        relation_id = str(uuid.uuid4())
        with self._con() as con:
            con.execute(
                "UPDATE world_relations SET active=0 WHERE subject_id=? AND predicate=? AND object_id!=? AND active=1",
                (subject, pred, obj),
            )
            con.execute(
                "INSERT INTO world_relations VALUES(?,?,?,?,?,?,?,1)",
                (relation_id, subject, pred, obj, src, timestamp, score),
            )
        self._emit(
            "sensorium.world.related",
            relation_id=relation_id,
            subject_id=subject,
            predicate=pred,
            object_id=obj,
            confidence=score,
            execution_authority=False,
        )
        return {
            "relation_id": relation_id,
            "subject_id": subject,
            "predicate": pred,
            "object_id": obj,
            "execution_authority": False,
        }

    def _observation(self, row) -> WorldObservation:
        return WorldObservation(
            observation_id=str(row["observation_id"]),
            entity_id=str(row["entity_id"]),
            attribute=str(row["attribute"]),
            value=json.loads(row["value_json"]),
            source=str(row["source"]),
            modality=str(row["modality"]),
            captured_at=float(row["captured_at"]),
            confidence=float(row["confidence"]),
            freshness_seconds=float(row["freshness_seconds"]),
            contradicted=bool(row["contradicted"]),
        )

    def entity(self, entity_id: str, *, include_history: bool = False) -> dict:
        entity = self._identifier(entity_id, field="entity ID")
        with self._con() as con:
            record = con.execute("SELECT * FROM world_entities WHERE entity_id=?", (entity,)).fetchone()
            if record is None:
                raise KeyError("world entity not found")
            rows = con.execute(
                "SELECT * FROM world_observations WHERE entity_id=? ORDER BY captured_at DESC LIMIT 256",
                (entity,),
            ).fetchall()
            relations = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM world_relations WHERE subject_id=? AND active=1 ORDER BY captured_at DESC LIMIT 128",
                    (entity,),
                ).fetchall()
            ]
        current: dict[str, dict] = {}
        history: list[dict] = []
        for row in rows:
            observation = self._observation(row).public()
            if include_history:
                history.append(observation)
            if observation["contradicted"]:
                continue
            attr = observation["attribute"]
            if attr not in current or observation["effective_confidence"] > current[attr]["effective_confidence"]:
                current[attr] = observation
        return {
            "entity": {
                "entity_id": record["entity_id"],
                "kind": record["kind"],
                "label": record["label"],
                "updated_at": record["updated_at"],
            },
            "current": current,
            "relations": relations,
            "history": history if include_history else None,
            "execution_authority": False,
        }

    def snapshot(self, *, limit: int = 100) -> dict:
        bounded = max(1, min(int(limit), 500))
        with self._con() as con:
            rows = con.execute(
                "SELECT entity_id FROM world_entities ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return {
            "entities": [self.entity(row["entity_id"], include_history=False) for row in rows],
            "execution_authority": False,
        }

    def contradictions(self, *, limit: int = 100) -> list[dict]:
        bounded = max(1, min(int(limit), 500))
        with self._con() as con:
            rows = con.execute(
                "SELECT * FROM world_observations WHERE contradicted=1 ORDER BY captured_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self._observation(row).public() for row in rows]
