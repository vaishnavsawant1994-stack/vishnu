from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .models import CapabilityPlan, CapabilityRoute, CapabilitySpec
from .risk_mapper import CapabilityRiskMapper
from .store import utc_now


class CapabilityPlanner:
    """Choose the narrowest implementation route for a frozen capability spec."""

    def __init__(self, *, catalog=None, risk_mapper: CapabilityRiskMapper | None = None):
        self.catalog = catalog
        self.risk_mapper = risk_mapper or CapabilityRiskMapper()

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    def _catalog_candidates(self, spec: CapabilitySpec) -> tuple[str, ...]:
        if self.catalog is None or not hasattr(self.catalog, "search"):
            return ()
        queries = [spec.name, *spec.required_operations[:3]]
        found: list[str] = []
        for query in queries:
            query = str(query or "").strip()
            if not query:
                continue
            try:
                rows = self.catalog.search(query, 20)
            except Exception:
                continue
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                capability_id = str(row.get("id") or "").strip()
                if capability_id and capability_id not in found:
                    found.append(capability_id)
        return tuple(found[:20])

    def _exact_existing(self, spec: CapabilitySpec, candidate_ids: Iterable[str]) -> tuple[str, ...]:
        if self.catalog is None or not hasattr(self.catalog, "get"):
            return ()
        matches: list[str] = []
        target_name = self._norm(spec.name)
        target_ops = {self._norm(item) for item in spec.required_operations if self._norm(item)}
        for capability_id in candidate_ids:
            try:
                row = self.catalog.get(capability_id)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            name = self._norm(row.get("name"))
            operation = self._norm(row.get("operation_id") or row.get("method") or row.get("tool_name"))
            if name == target_name or (operation and operation in target_ops):
                matches.append(capability_id)
        return tuple(matches)

    def plan(self, spec: CapabilitySpec) -> CapabilityPlan:
        metadata = dict(spec.metadata or {})
        candidate_ids = self._catalog_candidates(spec)
        exact = self._exact_existing(spec, candidate_ids)
        preferred = self._norm(metadata.get("preferred_route"))
        protocol = self._norm(metadata.get("protocol"))
        requires_core = bool(metadata.get("requires_core_change"))
        external_api = bool(metadata.get("external_api"))
        mcp = bool(metadata.get("mcp"))

        if requires_core or preferred in {"core", "core_engineering", "vishnu_core"}:
            route = CapabilityRoute.CORE_ENGINEERING
            rationale = "The requirement explicitly changes Vishnu core behavior and must use governed engineering work."
        elif exact:
            route = CapabilityRoute.EXISTING
            candidate_ids = exact
            rationale = "An existing catalog capability exactly matches the declared name or operation; reuse is preferred."
        elif preferred in {"workflow", "compose", "composition"}:
            route = CapabilityRoute.WORKFLOW_COMPOSITION
            rationale = "The reviewed requirement explicitly prefers composition of existing governed capabilities."
        elif mcp or protocol == "mcp" or preferred == "mcp":
            route = CapabilityRoute.MCP_DISCOVERY
            rationale = "The missing ability is described as MCP-backed; discover and review the MCP server instead of generating code."
        elif external_api or protocol in {"openapi", "http", "https", "rest"} or preferred == "openapi":
            route = CapabilityRoute.OPENAPI_DISCOVERY
            rationale = "The missing ability is API-backed; OpenAPI discovery is narrower than generating a new runtime capability."
        else:
            route = CapabilityRoute.GENERATED
            rationale = "No exact existing, workflow, OpenAPI, MCP, or core-engineering route was declared; propose an isolated generated capability."

        risk = self.risk_mapper.assess(spec)
        canonical = {
            "spec_id": spec.id,
            "route": route.value,
            "candidates": list(candidate_ids),
            "risk": risk.to_dict(),
            "rationale": rationale,
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return CapabilityPlan(
            id=f"plan-{digest}",
            spec_id=spec.id,
            route=route,
            rationale=rationale,
            candidate_capability_ids=tuple(candidate_ids),
            risk=risk,
            owner_review_required=True,
            created_at=utc_now(),
        )
