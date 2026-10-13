"""Typed contracts for the Capability Forge intelligence layer.

F1 is intentionally non-executing: these models describe gaps, frozen capability
specifications, planning decisions, and risk observations. They grant no runtime,
installation, merge, deployment, or activation authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class GapSource(str, Enum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    WORKFLOW = "workflow"
    EXECUTION = "execution"
    PROACTIVE = "proactive"
    ENGINEERING = "engineering"
    SYSTEM = "system"


class GapStatus(str, Enum):
    OPEN = "open"
    SPECIFIED = "specified"
    DISMISSED = "dismissed"
    REJECTED = "rejected"
    ACTIVE = "active"


class CapabilityRoute(str, Enum):
    EXISTING = "existing"
    WORKFLOW_COMPOSITION = "workflow_composition"
    OPENAPI_DISCOVERY = "openapi_discovery"
    MCP_DISCOVERY = "mcp_discovery"
    GENERATED = "generated"
    CORE_ENGINEERING = "core_engineering"


class CapabilityRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class CapabilityGap:
    id: str
    fingerprint: str
    summary: str
    requested_outcome: str
    source: GapSource
    evidence: tuple[str, ...] = ()
    hints: Mapping[str, Any] = field(default_factory=dict)
    occurrences: int = 1
    status: GapStatus = GapStatus.OPEN
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source"] = self.source.value
        value["status"] = self.status.value
        value["evidence"] = list(self.evidence)
        value["hints"] = dict(self.hints)
        return value


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    gap_id: str
    name: str
    purpose: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    required_operations: tuple[str, ...] = ()
    network_hosts: tuple[str, ...] = ()
    filesystem_read: tuple[str, ...] = ()
    filesystem_write: tuple[str, ...] = ()
    secret_names: tuple[str, ...] = ()
    connector_ids: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    ui_required: bool = False
    background_allowed: bool = False
    acceptance_criteria: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "required_operations",
            "network_hosts",
            "filesystem_read",
            "filesystem_write",
            "secret_names",
            "connector_ids",
            "side_effects",
            "acceptance_criteria",
        ):
            value[key] = list(value[key])
        value["inputs"] = dict(self.inputs)
        value["outputs"] = dict(self.outputs)
        value["metadata"] = dict(self.metadata)
        return value


@dataclass(frozen=True)
class RiskAssessment:
    risk: CapabilityRisk
    reasons: tuple[str, ...]
    owner_review_required: bool
    authority_expansion: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk.value,
            "reasons": list(self.reasons),
            "owner_review_required": self.owner_review_required,
            "authority_expansion": self.authority_expansion,
        }


@dataclass(frozen=True)
class CapabilityPlan:
    id: str
    spec_id: str
    route: CapabilityRoute
    rationale: str
    candidate_capability_ids: tuple[str, ...] = ()
    risk: RiskAssessment | None = None
    owner_review_required: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "spec_id": self.spec_id,
            "route": self.route.value,
            "rationale": self.rationale,
            "candidate_capability_ids": list(self.candidate_capability_ids),
            "risk": self.risk.to_dict() if self.risk else None,
            "owner_review_required": self.owner_review_required,
            "created_at": self.created_at,
        }
