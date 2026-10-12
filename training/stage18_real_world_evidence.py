from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from training.multimodal_visual_reasoning import Stage18RealWorldQualificationReport


class Stage18RealWorldEvidenceStore:
    """Append-only authority for genuine Stage 18 real-world qualification.

    A report can be recorded whether it passes or fails for auditability, but
    only a persisted passing report is permitted to unlock a production
    real-world-qualified claim. Synthetic evidence remains permanently unable
    to qualify because the qualifier itself rejects it and this store refuses
    reports that claim otherwise.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS stage18_real_world_evidence(
                    evidence_sha256 TEXT PRIMARY KEY,
                    qualified INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    records INTEGER NOT NULL,
                    source_groups INTEGER NOT NULL,
                    report_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_stage18_real_world_passed
                    ON stage18_real_world_evidence(qualified,created_at);
                """
            )

    @staticmethod
    def _payload(report: Stage18RealWorldQualificationReport | dict[str, Any]) -> dict[str, Any]:
        value = report.public() if isinstance(report, Stage18RealWorldQualificationReport) else dict(report)
        if value.get("synthetic_evidence_can_qualify") is not False:
            raise ValueError("Stage 18 real-world evidence must explicitly forbid synthetic qualification")
        sha = str(value.get("evidence_sha256") or "").strip().lower()
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise ValueError("Stage 18 real-world evidence requires a SHA-256 evidence id")
        if bool(value.get("qualified")) != bool(value.get("real_world_corpus_qualified")):
            raise ValueError("Stage 18 qualification flags disagree")
        return value

    def record(self, report: Stage18RealWorldQualificationReport | dict[str, Any]) -> dict[str, Any]:
        value = self._payload(report)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        with self._con() as con:
            existing = con.execute(
                "SELECT report_json FROM stage18_real_world_evidence WHERE evidence_sha256=?",
                (value["evidence_sha256"],),
            ).fetchone()
            if existing:
                if str(existing["report_json"]) != encoded:
                    raise RuntimeError("immutable Stage 18 evidence digest collision")
            else:
                con.execute(
                    "INSERT INTO stage18_real_world_evidence VALUES(?,?,?,?,?,?)",
                    (
                        value["evidence_sha256"],
                        int(bool(value.get("qualified"))),
                        str(value.get("created_at") or ""),
                        int(value.get("records") or 0),
                        int(value.get("source_groups") or 0),
                        encoded,
                    ),
                )
        return {**value, "evidence_persisted": True}

    def get(self, evidence_sha256: str) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                "SELECT report_json FROM stage18_real_world_evidence WHERE evidence_sha256=?",
                (str(evidence_sha256).strip().lower(),),
            ).fetchone()
        if not row:
            return None
        return {**json.loads(row["report_json"]), "evidence_persisted": True}

    def latest_qualified(self) -> dict[str, Any] | None:
        with self._con() as con:
            row = con.execute(
                "SELECT report_json FROM stage18_real_world_evidence WHERE qualified=1 ORDER BY created_at DESC,evidence_sha256 DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {**json.loads(row["report_json"]), "evidence_persisted": True}
