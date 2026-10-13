from __future__ import annotations

import json
from typing import Any

from future_intelligence.engineering.canary import CanaryMetrics, compare_canary
from integrations.discovery.generated_catalog import set_generated_capability_state
from integrations.discovery.generated_runtime_v2 import detach_generated_capability_v2

from .canary_rollout import CapabilityCanaryRollout, _now


class ProductionCapabilityCanaryRollout(CapabilityCanaryRollout):
    """V3 hardening for staged promotion and evidence-driven quarantine."""

    def _metrics_for_source(self, capability_id: str, version: str, source: str) -> CanaryMetrics:
        with self._con() as con:
            rows = con.execute(
                "SELECT ok,duration_ms FROM forge_canary_samples WHERE capability_id=? AND version=? AND source=? ORDER BY id",
                (str(capability_id), str(version), str(source)),
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

    def promote(self, capability_id: str, version: str, *, target_stage: str, ticket_id: str,
                owner_id: str = "owner", device_id: str | None = None,
                session_id: str | None = None) -> dict[str, Any]:
        record = self.approvals.record(str(ticket_id))
        if not record or record.get("status") != "approved":
            raise PermissionError("owner approval is required for Forge rollout promotion")
        ticket = record["ticket"]
        if str(ticket.destination or "") != str(capability_id):
            raise PermissionError("Forge rollout approval destination changed")
        if str(ticket.data_classification or "internal") != "internal":
            raise PermissionError("Forge rollout approval data classification changed")
        limited_baseline = None
        if target_stage == "broad_eligible":
            # Broad eligibility must be earned from observations made while the
            # capability was actually in the limited stage. Internal samples may
            # qualify internal -> limited, but cannot be reused to skip limited
            # exposure or manufacture a production-health baseline.
            rollout = self.get(capability_id, version)
            if rollout.get("stage") != "limited":
                raise PermissionError("Forge broad-eligible rollout requires the limited stage")
            limited_baseline = self._metrics_for_source(capability_id, version, "limited")
            if limited_baseline.sample_count < self.thresholds.min_sample_count:
                raise PermissionError("Forge broad-eligible rollout lacks sufficient limited-stage evidence")
        result = super().promote(
            capability_id,
            version,
            target_stage=target_stage,
            ticket_id=ticket_id,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
        )
        if target_stage == "broad_eligible":
            # Freeze limited-stage behavior as the immutable active-health
            # baseline. Operators cannot later provide a friendlier baseline to
            # suppress automatic regression detection.
            assert limited_baseline is not None
            with self._con() as con:
                con.execute(
                    "UPDATE forge_rollouts SET baseline_json=?,updated_at=? WHERE capability_id=? AND version=?",
                    (json.dumps(limited_baseline.__dict__, sort_keys=True), _now(), str(capability_id), str(version)),
                )
            result = self.get(capability_id, version)
        return result

    def active_health_from_rollout(self, capability_id: str, version: str) -> dict[str, Any]:
        rollout = self.get(capability_id, version)
        baseline_data = rollout.get("baseline")
        if rollout.get("stage") != "broad_eligible" or not isinstance(baseline_data, dict):
            raise PermissionError("Forge active health requires a frozen broad-eligible canary baseline")
        try:
            baseline = CanaryMetrics(
                int(baseline_data["sample_count"]),
                float(baseline_data["error_rate"]),
                float(baseline_data["p95_latency_ms"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PermissionError("Forge active health baseline is invalid") from exc
        return self.active_health(capability_id, version, baseline=baseline)

    def active_health(self, capability_id: str, version: str, *, baseline: CanaryMetrics) -> dict[str, Any]:
        with self.lifecycle._con() as con:
            rows = con.execute(
                "SELECT ok,duration_ms FROM forge_invocations WHERE capability_id=? AND version=? ORDER BY id DESC LIMIT 500",
                (str(capability_id), str(version)),
            ).fetchall()
        durations = sorted(float(row["duration_ms"]) for row in rows)
        count = len(rows)
        failures = sum(1 for row in rows if not int(row["ok"]))
        p95 = durations[max(0, min(len(durations) - 1, int((len(durations) - 1) * 0.95)))] if durations else 0.0
        candidate = CanaryMetrics(count, failures / count if count else 0.0, p95)
        recommendation = compare_canary(baseline, candidate, thresholds=self.thresholds)
        result = {**recommendation.to_dict(), "candidate": candidate.__dict__, "baseline": baseline.__dict__}
        if recommendation.recommended and recommendation.sufficient_evidence:
            # Automatic action only removes authority. The authoritative catalog
            # keeps its existing active/disabled state machine; quarantine detail
            # lives in the rollout record. Restoring/rolling back still requires
            # the normal exact owner approval path.
            set_generated_capability_state(self.catalog, str(capability_id), "disabled")
            detach_generated_capability_v2(self.tools, str(capability_id))
            self.lifecycle.disable_active(str(capability_id))
            with self._con() as con:
                con.execute(
                    "UPDATE forge_rollouts SET status='quarantined',recommendation_json=?,updated_at=? WHERE capability_id=? AND version=?",
                    (json.dumps(result, sort_keys=True), _now(), str(capability_id), str(version)),
                )
            if self.events is not None:
                self.events.emit(
                    "capability_forge.quarantined",
                    capability_id=str(capability_id),
                    version=str(version),
                    reasons=result.get("reasons", []),
                )
        return result
