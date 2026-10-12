from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    CapabilityGap,
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    GapSource,
    GapStatus,
    RiskAssessment,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityForgeStore:
    """Durable F1 lifecycle state, separate from the authoritative capability catalog."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS forge_gaps(
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    requested_outcome TEXT NOT NULL,
                    source TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    hints_json TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_gaps_status ON forge_gaps(status, updated_at);

                CREATE TABLE IF NOT EXISTS forge_specs(
                    id TEXT PRIMARY KEY,
                    gap_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(gap_id) REFERENCES forge_gaps(id)
                );
                CREATE INDEX IF NOT EXISTS idx_forge_specs_gap ON forge_specs(gap_id, created_at);

                CREATE TABLE IF NOT EXISTS forge_plans(
                    id TEXT PRIMARY KEY,
                    spec_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(spec_id) REFERENCES forge_specs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_forge_plans_spec ON forge_plans(spec_id, created_at);
                """
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @staticmethod
    def _load_json(raw: str) -> Any:
        return json.loads(raw) if raw else None

    def record_gap(self, gap: CapabilityGap) -> CapabilityGap:
        """Insert a gap or increment the existing fingerprint occurrence atomically."""
        now = gap.updated_at or utc_now()
        created = gap.created_at or now
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM forge_gaps WHERE fingerprint=?", (gap.fingerprint,)).fetchone()
            if row is None:
                con.execute(
                    """INSERT INTO forge_gaps(
                        id,fingerprint,summary,requested_outcome,source,evidence_json,hints_json,
                        occurrences,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        gap.id,
                        gap.fingerprint,
                        gap.summary,
                        gap.requested_outcome,
                        gap.source.value,
                        json.dumps(list(gap.evidence), sort_keys=True),
                        json.dumps(dict(gap.hints), sort_keys=True, default=str),
                        max(1, int(gap.occurrences)),
                        gap.status.value,
                        created,
                        now,
                    ),
                )
                return replace(gap, occurrences=max(1, gap.occurrences), created_at=created, updated_at=now)
            evidence = list(self._load_json(row["evidence_json"]) or [])
            for item in gap.evidence:
                if item and item not in evidence:
                    evidence.append(item)
            hints = dict(self._load_json(row["hints_json"]) or {})
            hints.update(dict(gap.hints))
            occurrences = int(row["occurrences"]) + 1
            con.execute(
                "UPDATE forge_gaps SET evidence_json=?,hints_json=?,occurrences=?,updated_at=? WHERE id=?",
                (json.dumps(evidence, sort_keys=True), json.dumps(hints, sort_keys=True, default=str), occurrences, now, row["id"]),
            )
            return CapabilityGap(
                id=str(row["id"]),
                fingerprint=str(row["fingerprint"]),
                summary=str(row["summary"]),
                requested_outcome=str(row["requested_outcome"]),
                source=GapSource(str(row["source"])),
                evidence=tuple(evidence),
                hints=hints,
                occurrences=occurrences,
                status=GapStatus(str(row["status"])),
                created_at=str(row["created_at"]),
                updated_at=now,
            )

    def set_gap_status(self, gap_id: str, status: GapStatus) -> CapabilityGap:
        with self._con() as con:
            cur = con.execute("UPDATE forge_gaps SET status=?,updated_at=? WHERE id=?", (status.value, utc_now(), gap_id))
            if cur.rowcount != 1:
                raise KeyError(gap_id)
        gap = self.get_gap(gap_id)
        if gap is None:
            raise KeyError(gap_id)
        return gap

    def get_gap(self, gap_id: str) -> CapabilityGap | None:
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_gaps WHERE id=?", (gap_id,)).fetchone()
        if row is None:
            return None
        return CapabilityGap(
            id=str(row["id"]),
            fingerprint=str(row["fingerprint"]),
            summary=str(row["summary"]),
            requested_outcome=str(row["requested_outcome"]),
            source=GapSource(str(row["source"])),
            evidence=tuple(self._load_json(row["evidence_json"]) or []),
            hints=dict(self._load_json(row["hints_json"]) or {}),
            occurrences=int(row["occurrences"]),
            status=GapStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def list_gaps(self, *, status: GapStatus | None = None, limit: int = 100) -> list[CapabilityGap]:
        limit = max(1, min(int(limit), 500))
        with self._con() as con:
            if status is None:
                rows = con.execute("SELECT id FROM forge_gaps ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = con.execute(
                    "SELECT id FROM forge_gaps WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status.value, limit)
                ).fetchall()
        return [gap for row in rows if (gap := self.get_gap(str(row["id"]))) is not None]

    def save_spec(self, spec: CapabilitySpec) -> CapabilitySpec:
        payload = spec.to_dict()
        with self._con() as con:
            con.execute(
                "INSERT OR IGNORE INTO forge_specs(id,gap_id,payload_json,created_at) VALUES(?,?,?,?)",
                (spec.id, spec.gap_id, json.dumps(payload, sort_keys=True, default=str), spec.created_at),
            )
        self.set_gap_status(spec.gap_id, GapStatus.SPECIFIED)
        return spec

    def get_spec(self, spec_id: str) -> CapabilitySpec | None:
        with self._con() as con:
            row = con.execute("SELECT payload_json FROM forge_specs WHERE id=?", (spec_id,)).fetchone()
        if row is None:
            return None
        p = dict(self._load_json(row["payload_json"]) or {})
        return CapabilitySpec(
            id=p["id"], gap_id=p["gap_id"], name=p["name"], purpose=p["purpose"],
            inputs=p.get("inputs") or {}, outputs=p.get("outputs") or {},
            required_operations=tuple(p.get("required_operations") or ()),
            network_hosts=tuple(p.get("network_hosts") or ()),
            filesystem_read=tuple(p.get("filesystem_read") or ()),
            filesystem_write=tuple(p.get("filesystem_write") or ()),
            secret_names=tuple(p.get("secret_names") or ()), connector_ids=tuple(p.get("connector_ids") or ()),
            side_effects=tuple(p.get("side_effects") or ()), ui_required=bool(p.get("ui_required", False)),
            background_allowed=bool(p.get("background_allowed", False)),
            acceptance_criteria=tuple(p.get("acceptance_criteria") or ()), metadata=p.get("metadata") or {},
            created_at=p.get("created_at") or "",
        )

    def save_plan(self, plan: CapabilityPlan) -> CapabilityPlan:
        with self._con() as con:
            con.execute(
                "INSERT OR REPLACE INTO forge_plans(id,spec_id,payload_json,created_at) VALUES(?,?,?,?)",
                (plan.id, plan.spec_id, json.dumps(plan.to_dict(), sort_keys=True, default=str), plan.created_at),
            )
        return plan

    def get_plan(self, plan_id: str) -> CapabilityPlan | None:
        with self._con() as con:
            row = con.execute("SELECT payload_json FROM forge_plans WHERE id=?", (plan_id,)).fetchone()
        if row is None:
            return None
        p = dict(self._load_json(row["payload_json"]) or {})
        risk_data = p.get("risk")
        risk = None
        if risk_data:
            risk = RiskAssessment(
                risk=CapabilityRisk(risk_data["risk"]), reasons=tuple(risk_data.get("reasons") or ()),
                owner_review_required=bool(risk_data.get("owner_review_required", True)),
                authority_expansion=bool(risk_data.get("authority_expansion", False)),
            )
        return CapabilityPlan(
            id=p["id"], spec_id=p["spec_id"], route=CapabilityRoute(p["route"]), rationale=p["rationale"],
            candidate_capability_ids=tuple(p.get("candidate_capability_ids") or ()), risk=risk,
            owner_review_required=bool(p.get("owner_review_required", True)), created_at=p.get("created_at") or "",
        )
