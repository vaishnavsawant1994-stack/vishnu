from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


class SemanticSceneGraph:
    """Persistent entity identity and semantic relations with source provenance."""

    COMPONENT = "sensorium_v3_scene_graph"

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "semantic-scene-graph", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS scene_entities(
                entity_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                stable_key TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_scene_stable_key ON scene_entities(stable_key) "
            "WHERE stable_key IS NOT NULL"
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS scene_aliases(
                alias TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                source_device_id TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES scene_entities(entity_id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS scene_relations(
                relation_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL,
                source_device_id TEXT,
                source_modality TEXT NOT NULL,
                captured_at REAL NOT NULL,
                confidence REAL NOT NULL,
                freshness_seconds REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_scene_relation_subject "
            "ON scene_relations(subject_id,predicate,captured_at DESC)"
        )

    @staticmethod
    def _clean(value: str, field: str, limit: int = 200) -> str:
        text = str(value or "").strip()
        if not text or len(text) > limit or any(ord(ch) < 32 for ch in text):
            raise ValueError(f"invalid {field}")
        return text

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def resolve_or_create(
        self,
        observed_id: str,
        *,
        kind: str = "object",
        label: str | None = None,
        stable_key: str | None = None,
        source_device_id: str | None = None,
    ) -> dict[str, Any]:
        alias = self._clean(observed_id, "observed entity ID")
        entity_kind = self._clean(kind, "entity kind", 80)
        entity_label = self._clean(label or alias, "entity label", 240)
        stable = self._clean(stable_key, "stable key", 240) if stable_key else None
        source = self._clean(source_device_id, "source device", 200) if source_device_id else None
        now = time.time()
        with self._con() as con:
            existing_alias = con.execute("SELECT entity_id FROM scene_aliases WHERE alias=?", (alias,)).fetchone()
            if existing_alias is not None:
                entity_id = str(existing_alias["entity_id"])
                con.execute("UPDATE scene_entities SET updated_at=? WHERE entity_id=?", (now, entity_id))
                return {"entity_id": entity_id, "matched_by": "alias", "execution_authority": False}
            if stable:
                existing_stable = con.execute("SELECT entity_id FROM scene_entities WHERE stable_key=?", (stable,)).fetchone()
                if existing_stable is not None:
                    entity_id = str(existing_stable["entity_id"])
                    con.execute(
                        "INSERT OR REPLACE INTO scene_aliases(alias,entity_id,source_device_id,created_at) "
                        "VALUES(?,?,?,?)",
                        (alias, entity_id, source, now),
                    )
                    con.execute("UPDATE scene_entities SET updated_at=? WHERE entity_id=?", (now, entity_id))
                    return {"entity_id": entity_id, "matched_by": "stable_key", "execution_authority": False}
            entity_id = f"scene-{uuid.uuid4()}"
            con.execute(
                "INSERT INTO scene_entities(entity_id,kind,label,stable_key,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (entity_id, entity_kind, entity_label, stable, now, now),
            )
            con.execute(
                "INSERT INTO scene_aliases(alias,entity_id,source_device_id,created_at) VALUES(?,?,?,?)",
                (alias, entity_id, source, now),
            )
        self._emit(
            "sensorium.v3.scene.entity_resolved",
            entity_id=entity_id,
            source_device_id=source,
            matched_by="new",
            execution_authority=False,
        )
        return {"entity_id": entity_id, "matched_by": "new", "execution_authority": False}

    def add_alias(self, entity_id: str, alias: str, *, source_device_id: str | None = None) -> dict[str, Any]:
        entity = self._clean(entity_id, "entity ID")
        observed = self._clean(alias, "alias")
        source = self._clean(source_device_id, "source device", 200) if source_device_id else None
        with self._con() as con:
            if con.execute("SELECT 1 FROM scene_entities WHERE entity_id=?", (entity,)).fetchone() is None:
                raise KeyError("scene entity not found")
            conflict = con.execute("SELECT entity_id FROM scene_aliases WHERE alias=?", (observed,)).fetchone()
            if conflict is not None and str(conflict["entity_id"]) != entity:
                raise ValueError("alias already belongs to another scene entity")
            con.execute(
                "INSERT OR REPLACE INTO scene_aliases(alias,entity_id,source_device_id,created_at) VALUES(?,?,?,?)",
                (observed, entity, source, time.time()),
            )
        return {"entity_id": entity, "alias": observed, "execution_authority": False}

    def relate(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        *,
        source_device_id: str | None,
        source_modality: str,
        confidence: float = 0.7,
        freshness_seconds: float = 60.0,
        captured_at: float | None = None,
    ) -> dict[str, Any]:
        subject = self._clean(subject_id, "subject ID")
        obj = self._clean(object_id, "object ID")
        pred = self._clean(predicate, "predicate", 120)
        modality = self._clean(source_modality, "source modality", 80)
        source = self._clean(source_device_id, "source device", 200) if source_device_id else None
        score = max(0.0, min(float(confidence), 1.0))
        freshness = max(0.1, min(float(freshness_seconds), 86_400.0))
        timestamp = float(captured_at or time.time())
        with self._con() as con:
            known = {
                str(row["entity_id"])
                for row in con.execute(
                    "SELECT entity_id FROM scene_entities WHERE entity_id IN (?,?)", (subject, obj)
                ).fetchall()
            }
            if {subject, obj} - known:
                raise KeyError("scene relation references an unknown entity")
            con.execute(
                "UPDATE scene_relations SET active=0 "
                "WHERE subject_id=? AND predicate=? AND object_id!=? AND active=1",
                (subject, pred, obj),
            )
            relation_id = str(uuid.uuid4())
            con.execute(
                """INSERT INTO scene_relations(
                    relation_id,subject_id,predicate,object_id,source_device_id,source_modality,
                    captured_at,confidence,freshness_seconds,active
                ) VALUES(?,?,?,?,?,?,?,?,?,1)""",
                (relation_id, subject, pred, obj, source, modality, timestamp, score, freshness),
            )
        self._emit(
            "sensorium.v3.scene.related",
            relation_id=relation_id,
            subject_id=subject,
            predicate=pred,
            object_id=obj,
            source_device_id=source,
            execution_authority=False,
        )
        return {
            "relation_id": relation_id,
            "subject_id": subject,
            "predicate": pred,
            "object_id": obj,
            "execution_authority": False,
        }

    def snapshot(self, *, now: float | None = None, limit: int = 500) -> dict[str, Any]:
        current = float(now or time.time())
        bounded = max(1, min(int(limit), 2000))
        with self._con() as con:
            entities = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM scene_entities ORDER BY updated_at DESC LIMIT ?", (bounded,)
                ).fetchall()
            ]
            relation_rows = con.execute(
                "SELECT * FROM scene_relations WHERE active=1 ORDER BY captured_at DESC LIMIT ?",
                (bounded * 4,),
            ).fetchall()
        relations: list[dict[str, Any]] = []
        for row in relation_rows:
            age = max(0.0, current - float(row["captured_at"]))
            freshness = pow(2.718281828, -age / max(float(row["freshness_seconds"]), 0.1))
            effective = float(row["confidence"]) * freshness
            if effective < 0.05:
                continue
            item = dict(row)
            item["age_seconds"] = age
            item["effective_confidence"] = effective
            relations.append(item)
        return {"entities": entities, "relations": relations, "execution_authority": False}
