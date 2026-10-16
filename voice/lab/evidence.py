"""Append-only SQLite evidence store for Vishnu Voice Lab."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from .evaluation import QualificationGate, VoiceLabReport


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    experiment_id: str
    baseline_key: str
    created_at: str
    provider: str
    model: str
    revision: str
    device: str
    device_class: str
    os_name: str
    language: str
    route: str
    fixture_refs: tuple[str, ...]
    configuration: tuple[tuple[str, str], ...]
    provenance: tuple[tuple[str, str], ...]
    metrics: tuple[tuple[str, float], ...]
    gates: tuple[QualificationGate, ...]
    regression_summary: tuple[tuple[str, str], ...] = ()
    artifact_digests: tuple[tuple[str, str], ...] = ()

    @property
    def digest(self) -> str:
        body = asdict(self)
        body.pop("evidence_id", None)
        return hashlib.sha256(_json(body).encode()).hexdigest()

    @classmethod
    def build(
        cls,
        *,
        experiment_id: str,
        provider: str,
        model: str,
        device: str,
        language: str,
        route: str,
        gates: tuple[QualificationGate, ...],
        baseline_key: str = "",
        fixture_refs: tuple[str, ...] = (),
        revision: str = "",
        device_class: str = "unknown",
        os_name: str = "",
        configuration: dict[str, str] | None = None,
        provenance: dict[str, str] | None = None,
        metrics: dict[str, float] | None = None,
        regression_summary: tuple[tuple[str, str], ...] = (),
        artifact_digests: dict[str, str] | None = None,
        created_at: str | None = None,
    ) -> "EvidenceRecord":
        stamp = created_at or _utc_now()
        key = baseline_key or f"unassigned:{experiment_id}"
        seed = _json(
            {
                "experiment": experiment_id,
                "created_at": stamp,
                "provider": provider,
                "model": model,
                "device": device,
                "gates": [asdict(gate) for gate in gates],
            }
        )
        evidence_id = "vle-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
        return cls(
            evidence_id,
            experiment_id,
            key,
            stamp,
            provider,
            model,
            revision,
            device,
            device_class,
            os_name,
            language,
            route,
            fixture_refs,
            tuple(sorted((configuration or {}).items())),
            tuple(sorted((provenance or {}).items())),
            tuple(sorted((metrics or {}).items())),
            gates,
            regression_summary,
            tuple(sorted((artifact_digests or {}).items())),
        )

    def report(self, required_gate_ids: tuple[str, ...]) -> VoiceLabReport:
        return VoiceLabReport(
            self.experiment_id,
            self.provider,
            self.model,
            self.device,
            self.language,
            self.gates,
            required_gate_ids,
        )


class EvidenceStore:
    """Explicitly-created local store. Raw audio bytes are not accepted or persisted."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS voice_lab_evidence(
                  evidence_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, created_at TEXT NOT NULL,
                  digest TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_voice_lab_experiment
                  ON voice_lab_evidence(experiment_id, created_at);
                CREATE TABLE IF NOT EXISTS voice_lab_baselines(
                  baseline_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, created_at TEXT NOT NULL,
                  FOREIGN KEY(evidence_id) REFERENCES voice_lab_evidence(evidence_id));
                """
            )

    @staticmethod
    def _payload(record: EvidenceRecord) -> str:
        data = asdict(record)
        data["gates"] = [{**asdict(gate), "status": gate.status.value} for gate in record.gates]
        return _json(data)

    def append(self, record: EvidenceRecord) -> str:
        payload = self._payload(record)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT digest,payload FROM voice_lab_evidence WHERE evidence_id=?",
                (record.evidence_id,),
            ).fetchone()
            if row:
                if row != (record.digest, payload):
                    raise ValueError("immutable Voice Lab evidence ID collision")
                return record.evidence_id
            conn.execute(
                "INSERT INTO voice_lab_evidence VALUES(?,?,?,?,?)",
                (record.evidence_id, record.experiment_id, record.created_at, record.digest, payload),
            )
        return record.evidence_id

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload,digest FROM voice_lab_evidence WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        payload["digest"] = row[1]
        return payload

    def list_for_experiment(self, experiment_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload,digest FROM voice_lab_evidence WHERE experiment_id=? ORDER BY created_at",
                (experiment_id,),
            ).fetchall()
        return self._decode_rows(rows)

    def list_recent(self, limit: int = 100) -> tuple[dict[str, Any], ...]:
        limit = max(1, min(int(limit), 1000))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload,digest FROM voice_lab_evidence ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._decode_rows(rows)

    @staticmethod
    def _decode_rows(rows) -> tuple[dict[str, Any], ...]:
        result = []
        for payload, digest in rows:
            item = json.loads(payload)
            item["digest"] = digest
            result.append(item)
        return tuple(result)

    def accept_baseline(self, baseline_id: str, evidence_id: str) -> None:
        if not baseline_id.strip():
            raise ValueError("baseline_id is required")
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM voice_lab_evidence WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
            if not exists:
                raise KeyError(evidence_id)
            existing = conn.execute(
                "SELECT evidence_id FROM voice_lab_baselines WHERE baseline_id=?",
                (baseline_id,),
            ).fetchone()
            if existing and existing[0] != evidence_id:
                raise ValueError("accepted baselines are immutable; create a new baseline family/version")
            conn.execute(
                "INSERT OR IGNORE INTO voice_lab_baselines VALUES(?,?,?)",
                (baseline_id, evidence_id, _utc_now()),
            )

    def baseline(self, baseline_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT evidence_id FROM voice_lab_baselines WHERE baseline_id=?",
                (baseline_id,),
            ).fetchone()
        return self.get(row[0]) if row else None
