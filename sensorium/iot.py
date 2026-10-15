from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


class IoTSensorRegistry:
    """Registers owner-approved IoT sources while separating observe from act.

    This registry can ingest bounded sensor state and can create an action
    proposal. It deliberately cannot execute device changes; proposals must be
    handed to existing Device/Tool Control and ApprovalManager authorities.
    """

    COMPONENT = "sensorium_iot"

    def __init__(self, path: Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self._con() as con:
            run_migrations(con, component=self.COMPONENT, migrations=(Migration(1, "iot-sources", self._migration_001),))

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS iot_sources(
                source_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                kind TEXT NOT NULL,
                observe_capabilities_json TEXT NOT NULL,
                action_capabilities_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS iot_observations(
                observation_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                captured_at REAL NOT NULL,
                payload_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                FOREIGN KEY(source_id) REFERENCES iot_sources(source_id) ON DELETE CASCADE
            )"""
        )

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    @staticmethod
    def _caps(values) -> list[str]:
        return sorted({str(value).strip().lower()[:120] for value in (values or ()) if str(value).strip()})[:64]

    def register(
        self,
        *,
        label: str,
        kind: str,
        observe_capabilities,
        action_capabilities=(),
        source_id: str | None = None,
    ) -> dict:
        source = str(source_id or uuid.uuid4())
        title = str(label or "").strip()[:160]
        source_kind = str(kind or "sensor").strip().lower()[:80]
        if not title:
            raise ValueError("IoT source label is required")
        observe = self._caps(observe_capabilities)
        actions = self._caps(action_capabilities)
        if not observe:
            raise ValueError("IoT source must expose at least one observation capability")
        now = time.time()
        with self._con() as con:
            con.execute(
                """INSERT INTO iot_sources VALUES(?,?,?,?,?,1,?,?)
                   ON CONFLICT(source_id) DO UPDATE SET label=excluded.label,kind=excluded.kind,
                   observe_capabilities_json=excluded.observe_capabilities_json,
                   action_capabilities_json=excluded.action_capabilities_json,enabled=1,updated_at=excluded.updated_at""",
                (source, title, source_kind, json.dumps(observe), json.dumps(actions), now, now),
            )
        self._emit("sensorium.iot.registered", source_id=source, kind=source_kind)
        return self.get(source)

    def get(self, source_id: str) -> dict:
        with self._con() as con:
            row = con.execute("SELECT * FROM iot_sources WHERE source_id=?", (str(source_id),)).fetchone()
        if row is None:
            raise KeyError("IoT source not found")
        return {
            "source_id": row["source_id"],
            "label": row["label"],
            "kind": row["kind"],
            "observe_capabilities": json.loads(row["observe_capabilities_json"]),
            "action_capabilities": json.loads(row["action_capabilities_json"]),
            "enabled": bool(row["enabled"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def list(self) -> list[dict]:
        with self._con() as con:
            ids = [row["source_id"] for row in con.execute("SELECT source_id FROM iot_sources ORDER BY label").fetchall()]
        return [self.get(source_id) for source_id in ids]

    def observe(self, source_id: str, *, capability: str, payload: dict[str, Any], confidence: float = 0.8) -> dict:
        source = self.get(source_id)
        cap = str(capability or "").strip().lower()
        if not source["enabled"] or cap not in source["observe_capabilities"]:
            raise PermissionError("IoT observation capability is not enabled")
        safe = dict(list((payload or {}).items())[:128])
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("IoT observation is too large")
        observation_id = str(uuid.uuid4())
        captured_at = time.time()
        score = max(0.0, min(float(confidence), 1.0))
        with self._con() as con:
            con.execute(
                "INSERT INTO iot_observations VALUES(?,?,?,?,?)",
                (observation_id, source["source_id"], captured_at, encoded, score),
            )
        self._emit(
            "sensorium.iot.observed",
            source_id=source["source_id"],
            capability=cap,
            confidence=score,
            execution_authority=False,
        )
        return {
            "observation_id": observation_id,
            "source_id": source["source_id"],
            "capability": cap,
            "payload": safe,
            "captured_at": captured_at,
            "confidence": score,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }

    def propose_action(self, source_id: str, *, capability: str, parameters: dict[str, Any] | None = None) -> dict:
        source = self.get(source_id)
        cap = str(capability or "").strip().lower()
        if not source["enabled"] or cap not in source["action_capabilities"]:
            raise PermissionError("IoT action capability is not registered")
        proposal_id = str(uuid.uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "source_id": source["source_id"],
            "capability": cap,
            "parameters": dict(list((parameters or {}).items())[:64]),
            "requires_approval": True,
            "execution_authority": False,
            "handoff": "ToolRegistry/ApprovalManager/Device Control",
        }
        self._emit(
            "sensorium.iot.action_proposed",
            proposal_id=proposal_id,
            source_id=source["source_id"],
            capability=cap,
            requires_approval=True,
            execution_authority=False,
        )
        return proposal
