from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from future_intelligence.engineering.canary import CanaryMetrics, CanaryThresholds, compare_canary
from integrations.discovery.generated_catalog import set_generated_capability_state
from integrations.discovery.generated_runtime import detach_generated_capability
from security.approvals import parameter_hash


_STAGES = ("internal", "limited", "broad_eligible")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityCanaryRollout:
    """Staged rollout evidence using the existing Engineering canary evaluator.

    Internal/limited stages do not grant production activation authority.  The
    final stage only marks a package broad-eligible; activation still requires
    CapabilityActivationService's separate exact owner approval.  Active health
    regression may automatically *remove* authority by quarantining a capability,
    but restoration/rollback remains owner-approved through the existing service.
    """

    PROMOTE_TOOL = "capability_forge.rollout.promote"

    def __init__(self, *, path: str | Path, lifecycle, approvals, catalog, tools, events=None,
                 thresholds: CanaryThresholds = CanaryThresholds()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lifecycle = lifecycle
        self.approvals = approvals
        self.catalog = catalog
        self.tools = tools
        self.events = events
        self.thresholds = thresholds
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS forge_rollouts(
                    capability_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    baseline_json TEXT,
                    recommendation_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(capability_id,version)
                );
                CREATE TABLE IF NOT EXISTS forge_canary_samples(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forge_canary_samples
                    ON forge_canary_samples(capability_id,version,id);
                """
            )

    def _con(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _execution_id(capability_id: str, version: str, target_stage: str, digest: str) -> str:
        raw = f"{capability_id}|{version}|{target_stage}|{digest}".encode("utf-8")
        return f"forge-rollout:{hashlib.sha256(raw).hexdigest()[:24]}"

    def start(self, *, capability_id: str, version: str, manifest_digest: str,
              baseline: CanaryMetrics | None = None) -> dict[str, Any]:
        now = _now()
        baseline_json = json.dumps(baseline.__dict__, sort_keys=True) if baseline is not None else None
        with self._con() as con:
            con.execute(
                """INSERT INTO forge_rollouts(capability_id,version,manifest_digest,stage,status,baseline_json,recommendation_json,created_at,updated_at)
                   VALUES(?,?,?,'internal','running',?,NULL,?,?)
                   ON CONFLICT(capability_id,version) DO UPDATE SET
                     manifest_digest=excluded.manifest_digest,baseline_json=COALESCE(forge_rollouts.baseline_json,excluded.baseline_json),updated_at=excluded.updated_at""",
                (str(capability_id), str(version), str(manifest_digest), baseline_json, now, now),
            )
        return self.get(capability_id, version)

    def get(self, capability_id: str, version: str) -> dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM forge_rollouts WHERE capability_id=? AND version=?",
                              (str(capability_id), str(version))).fetchone()
        if row is None:
            raise KeyError(f"{capability_id}:{version}")
        result = dict(row)
        for key in ("baseline_json", "recommendation_json"):
            raw = result.pop(key)
            result[key.removesuffix("_json")] = json.loads(raw) if raw else None
        return result

    def record_sample(self, capability_id: str, version: str, *, ok: bool,
                      duration_ms: float, source: str = "internal") -> None:
        rollout = self.get(capability_id, version)
        if rollout["status"] != "running":
            raise PermissionError("Forge canary rollout is not accepting samples")
        if source not in {"internal", "limited", "provider_probe"}:
            raise ValueError("invalid Forge canary sample source")
        with self._con() as con:
            con.execute(
                "INSERT INTO forge_canary_samples(capability_id,version,ok,duration_ms,source,created_at) VALUES(?,?,?,?,?,?)",
                (str(capability_id), str(version), 1 if ok else 0, max(0.0, float(duration_ms)), source, _now()),
            )

    def _candidate_metrics(self, capability_id: str, version: str) -> CanaryMetrics:
        with self._con() as con:
            rows = con.execute(
                "SELECT ok,duration_ms FROM forge_canary_samples WHERE capability_id=? AND version=? ORDER BY id",
                (str(capability_id), str(version)),
            ).fetchall()
        durations = sorted(float(row["duration_ms"]) for row in rows)
        count = len(rows)
        failures = sum(1 for row in rows if not int(row["ok"]))
        if durations:
            index = max(0, min(len(durations) - 1, int((len(durations) - 1) * 0.95)))
            p95 = durations[index]
        else:
            p95 = 0.0
        return CanaryMetrics(count, failures / count if count else 0.0, p95)

    def evaluate(self, capability_id: str, version: str, *, additional_checks: dict[str, bool] | None = None) -> dict[str, Any]:
        rollout = self.get(capability_id, version)
        candidate = self._candidate_metrics(capability_id, version)
        baseline_data = rollout.get("baseline")
        baseline = CanaryMetrics(**baseline_data) if baseline_data else CanaryMetrics(
            sample_count=max(candidate.sample_count, self.thresholds.min_sample_count),
            error_rate=0.0,
            p95_latency_ms=max(candidate.p95_latency_ms, 1.0),
        )
        recommendation = compare_canary(baseline, candidate, thresholds=self.thresholds,
                                        additional_checks=additional_checks)
        payload = {**recommendation.to_dict(), "candidate": candidate.__dict__, "baseline": baseline.__dict__}
        status = "blocked" if recommendation.recommended and recommendation.sufficient_evidence else "running"
        with self._con() as con:
            con.execute("UPDATE forge_rollouts SET status=?,recommendation_json=?,updated_at=? WHERE capability_id=? AND version=?",
                        (status, json.dumps(payload, sort_keys=True), _now(), str(capability_id), str(version)))
        return payload

    def request_promotion(self, capability_id: str, version: str, *, target_stage: str,
                          owner_id: str = "owner", device_id: str | None = None,
                          session_id: str | None = None) -> str:
        rollout = self.get(capability_id, version)
        if target_stage not in _STAGES:
            raise ValueError("invalid Forge rollout stage")
        current_index = _STAGES.index(rollout["stage"])
        if _STAGES.index(target_stage) != current_index + 1:
            raise PermissionError("Forge rollout stages must advance one step at a time")
        recommendation = self.evaluate(capability_id, version)
        if not recommendation.get("sufficient_evidence") or recommendation.get("recommended"):
            raise PermissionError("Forge canary evidence does not permit rollout promotion")
        parameters = {
            "capability_id": str(capability_id),
            "version": str(version),
            "target_stage": target_stage,
            "manifest_digest": str(rollout["manifest_digest"]),
        }
        ticket = self.approvals.create(
            self._execution_id(capability_id, version, target_stage, rollout["manifest_digest"]),
            self.PROMOTE_TOOL,
            parameters,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
            destination=str(capability_id),
            data_classification="internal",
        )
        return ticket.id

    def promote(self, capability_id: str, version: str, *, target_stage: str, ticket_id: str,
                owner_id: str = "owner", device_id: str | None = None,
                session_id: str | None = None) -> dict[str, Any]:
        rollout = self.get(capability_id, version)
        parameters = {
            "capability_id": str(capability_id), "version": str(version),
            "target_stage": str(target_stage), "manifest_digest": str(rollout["manifest_digest"]),
        }
        record = self.approvals.record(str(ticket_id))
        if not record or record.get("status") != "approved":
            raise PermissionError("owner approval is required for Forge rollout promotion")
        ticket = record["ticket"]
        expected_execution = self._execution_id(capability_id, version, target_stage, rollout["manifest_digest"])
        if ticket.execution_id != expected_execution or ticket.tool_name != self.PROMOTE_TOOL:
            raise PermissionError("Forge rollout approval scope mismatch")
        if ticket.parameter_hash != parameter_hash(parameters):
            raise PermissionError("Forge rollout approval parameters changed")
        if ticket.owner_id and ticket.owner_id != owner_id:
            raise PermissionError("Forge rollout approval owner changed")
        if ticket.device_id is not None and ticket.device_id != device_id:
            raise PermissionError("Forge rollout approval device changed")
        if ticket.session_id is not None and ticket.session_id != session_id:
            raise PermissionError("Forge rollout approval session changed")
        if ticket.security_epoch != self.approvals.current_security_epoch():
            raise PermissionError("Forge rollout approval security epoch changed")
        dispatch = self.approvals.begin_dispatch(str(ticket_id), worker_id="capability-forge-rollout", lease_seconds=30)
        if not dispatch.get("dispatch"):
            raise PermissionError(f"Forge rollout approval dispatch is {dispatch.get('status')}")
        try:
            current_index = _STAGES.index(rollout["stage"])
            if target_stage not in _STAGES or _STAGES.index(target_stage) != current_index + 1:
                raise PermissionError("Forge rollout stage changed after approval")
            recommendation = self.evaluate(capability_id, version)
            if recommendation.get("recommended") or not recommendation.get("sufficient_evidence"):
                raise PermissionError("Forge canary health changed after approval")
            with self._con() as con:
                con.execute("UPDATE forge_rollouts SET stage=?,status='running',updated_at=? WHERE capability_id=? AND version=?",
                            (target_stage, _now(), str(capability_id), str(version)))
            self.approvals.complete_dispatch(str(ticket_id), {"stage": target_stage, "capability_id": str(capability_id), "version": str(version)})
        except Exception:
            self.approvals.mark_recovery_required(str(ticket_id), "capability_forge_rollout_failed")
            raise
        result = self.get(capability_id, version)
        if self.events is not None:
            self.events.emit("capability_forge.rollout_promoted", capability_id=str(capability_id), version=str(version), stage=target_stage)
        return result

    def active_health(self, capability_id: str, version: str, *, baseline: CanaryMetrics) -> dict[str, Any]:
        with self.lifecycle._con() as con:
            rows = con.execute(
                "SELECT ok,duration_ms FROM forge_invocations WHERE capability_id=? AND version=? ORDER BY id DESC LIMIT 500",
                (str(capability_id), str(version)),
            ).fetchall()
        durations = sorted(float(row["duration_ms"]) for row in rows)
        count = len(rows)
        failures = sum(1 for row in rows if not int(row["ok"]))
        p95 = durations[max(0, min(len(durations)-1, int((len(durations)-1)*0.95)))] if durations else 0.0
        candidate = CanaryMetrics(count, failures / count if count else 0.0, p95)
        recommendation = compare_canary(baseline, candidate, thresholds=self.thresholds)
        result = {**recommendation.to_dict(), "candidate": candidate.__dict__, "baseline": baseline.__dict__}
        if recommendation.recommended and recommendation.sufficient_evidence:
            # Fail safe: removing authority is automatic; restoring an older
            # package still requires the normal owner-approved rollback flow.
            set_generated_capability_state(self.catalog, str(capability_id), "quarantined")
            detach_generated_capability(self.tools, str(capability_id))
            self.lifecycle.disable_active(str(capability_id))
            with self._con() as con:
                con.execute("UPDATE forge_rollouts SET status='quarantined',recommendation_json=?,updated_at=? WHERE capability_id=? AND version=?",
                            (json.dumps(result, sort_keys=True), _now(), str(capability_id), str(version)))
            if self.events is not None:
                self.events.emit("capability_forge.quarantined", capability_id=str(capability_id), version=str(version), reasons=result.get("reasons", []))
        return result
