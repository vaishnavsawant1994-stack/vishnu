from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from urllib.parse import urlsplit

from .models import CapabilityGap, CapabilitySpec
from .store import utc_now


class CapabilitySpecBuilder:
    """Build a frozen capability contract from a recorded gap and reviewed requirements."""

    PLANNING_HINTS = (
        "preferred_route",
        "protocol",
        "external_api",
        "mcp",
        "requires_core_change",
    )

    @staticmethod
    def _bounded_strings(values, *, limit: int = 100, item_limit: int = 500) -> tuple[str, ...]:
        out: list[str] = []
        for raw in list(values or [])[:limit]:
            value = " ".join(str(raw or "").split())[:item_limit]
            if value and value not in out:
                out.append(value)
        return tuple(out)

    @staticmethod
    def _host(value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or "").strip(".")
        if not host or any(ch.isspace() for ch in host):
            raise ValueError(f"invalid network host: {value}")
        return host

    def build(self, gap: CapabilityGap, requirements: Mapping[str, Any] | None = None) -> CapabilitySpec:
        req = dict(requirements or {})
        hints = dict(gap.hints or {})
        merged = {**hints, **req}
        name = " ".join(str(merged.get("name") or gap.summary).split())[:160]
        purpose = " ".join(str(merged.get("purpose") or gap.requested_outcome).split())[:2000]
        if not name or not purpose:
            raise ValueError("capability name and purpose are required")
        hosts = tuple(host for host in (self._host(v) for v in merged.get("network_hosts") or []) if host)
        criteria = self._bounded_strings(merged.get("acceptance_criteria"), limit=50, item_limit=1000)
        if not criteria:
            criteria = (
                "Produces outputs matching the declared output contract.",
                "Does not exercise authority outside the declared permission scope.",
                "Fails closed when required inputs or permissions are unavailable.",
            )
        metadata = dict(merged.get("metadata") or {})
        for key in self.PLANNING_HINTS:
            if key in merged and key not in metadata:
                metadata[key] = merged[key]
        canonical = {
            "gap_id": gap.id,
            "name": name,
            "purpose": purpose,
            "inputs": dict(merged.get("inputs") or {}),
            "outputs": dict(merged.get("outputs") or {}),
            "required_operations": list(self._bounded_strings(merged.get("required_operations"), limit=100, item_limit=200)),
            "network_hosts": list(hosts),
            "filesystem_read": list(self._bounded_strings(merged.get("filesystem_read"), item_limit=1000)),
            "filesystem_write": list(self._bounded_strings(merged.get("filesystem_write"), item_limit=1000)),
            "secret_names": list(self._bounded_strings(merged.get("secret_names"), item_limit=200)),
            "connector_ids": list(self._bounded_strings(merged.get("connector_ids") or ([merged["connector_id"]] if merged.get("connector_id") else []), item_limit=200)),
            "side_effects": list(self._bounded_strings(merged.get("side_effects"), item_limit=500)),
            "ui_required": bool(merged.get("ui_required", False)),
            "background_allowed": bool(merged.get("background_allowed", False)),
            "acceptance_criteria": list(criteria),
            "metadata": metadata,
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]
        return CapabilitySpec(
            id=f"spec-{digest}",
            gap_id=gap.id,
            name=name,
            purpose=purpose,
            inputs=canonical["inputs"],
            outputs=canonical["outputs"],
            required_operations=tuple(canonical["required_operations"]),
            network_hosts=tuple(canonical["network_hosts"]),
            filesystem_read=tuple(canonical["filesystem_read"]),
            filesystem_write=tuple(canonical["filesystem_write"]),
            secret_names=tuple(canonical["secret_names"]),
            connector_ids=tuple(canonical["connector_ids"]),
            side_effects=tuple(canonical["side_effects"]),
            ui_required=canonical["ui_required"],
            background_allowed=canonical["background_allowed"],
            acceptance_criteria=tuple(canonical["acceptance_criteria"]),
            metadata=canonical["metadata"],
            created_at=utc_now(),
        )
