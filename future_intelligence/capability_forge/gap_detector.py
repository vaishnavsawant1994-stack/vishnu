from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .models import CapabilityGap, GapSource
from .store import CapabilityForgeStore, utc_now


class CapabilityGapDetector:
    """Conservative gap detector.

    It only records an explicit or strongly typed unsupported-capability signal.
    Free-form user text alone never starts a Forge build in F1.
    """

    GAP_ERROR_CODES = frozenset({
        "capability_missing",
        "tool_unavailable",
        "unsupported_capability",
        "unsupported_operation",
        "connector_missing",
    })

    def __init__(self, store: CapabilityForgeStore):
        self.store = store

    @staticmethod
    def _source(value: str | GapSource) -> GapSource:
        try:
            return value if isinstance(value, GapSource) else GapSource(str(value))
        except ValueError:
            return GapSource.SYSTEM

    @staticmethod
    def _clean(value: Any, *, limit: int = 1000) -> str:
        return " ".join(str(value or "").split())[:limit]

    @classmethod
    def _is_gap_signal(cls, payload: Mapping[str, Any]) -> bool:
        code = str(payload.get("error_code") or "").strip().lower()
        if bool(payload.get("capability_gap")) or bool(payload.get("unsupported")):
            return True
        if code in cls.GAP_ERROR_CODES:
            return True
        # Repeated governed workarounds are eligible only when the producer
        # explicitly marks them as reusable capability candidates.
        return bool(payload.get("workaround_repeated") and payload.get("reusable_candidate"))

    @classmethod
    def _fingerprint(cls, summary: str, outcome: str, payload: Mapping[str, Any]) -> str:
        stable = {
            "summary": summary.lower(),
            "outcome": outcome.lower(),
            "required_operations": sorted(str(x).strip().lower() for x in payload.get("required_operations") or [] if str(x).strip()),
            "connector": cls._clean(payload.get("connector_id"), limit=200).lower(),
            "protocol": cls._clean(payload.get("protocol"), limit=80).lower(),
        }
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()
        return digest[:32]

    def observe(self, source: str | GapSource, payload: Mapping[str, Any]) -> CapabilityGap | None:
        data = dict(payload or {})
        if not self._is_gap_signal(data):
            return None
        summary = self._clean(data.get("capability_name") or data.get("summary") or data.get("title") or "Missing capability", limit=240)
        outcome = self._clean(data.get("requested_outcome") or data.get("desired_outcome") or data.get("message") or summary)
        if not outcome:
            return None
        fingerprint = self._fingerprint(summary, outcome, data)
        evidence = []
        for key in ("error_code", "request_id", "workflow_id", "project_id", "tool_id"):
            value = self._clean(data.get(key), limit=240)
            if value:
                evidence.append(f"{key}:{value}")
        hints = {
            key: data[key]
            for key in (
                "required_operations", "connector_id", "protocol", "external_api", "mcp", "requires_core_change",
                "network_hosts", "filesystem_read", "filesystem_write", "secret_names", "side_effects", "ui_required",
                "background_allowed", "preferred_route",
            )
            if key in data
        }
        now = utc_now()
        gap = CapabilityGap(
            id=f"gap-{fingerprint[:24]}",
            fingerprint=fingerprint,
            summary=summary,
            requested_outcome=outcome,
            source=self._source(source),
            evidence=tuple(evidence),
            hints=hints,
            created_at=now,
            updated_at=now,
        )
        return self.store.record_gap(gap)
