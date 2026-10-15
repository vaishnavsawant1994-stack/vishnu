from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


FUTURE_CAPABILITY_KINDS = {
    "agent_team",
    "learned_skill",
    "robotics",
    "home_automation",
    "third_party_skill",
    "emotional_social_intelligence",
    "teaching_coaching",
    "developer_sdk",
    "self_improvement_proposal",
}


@dataclass(frozen=True)
class CapabilityProposal:
    proposal_id: str
    kind: str
    description: str
    required_authorities: tuple[str, ...]
    execution_authority: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class GovernedFutureCapabilities:
    """Safe extension boundary for ambitious capabilities.

    A proposal can describe or learn a capability, but it cannot execute anything.
    Execution must be delegated to existing Vishnu policy/approval/tool authorities.
    """

    def __init__(self, store: TrustContinuityStore, *, approval_check: Callable[[str], bool] | None = None):
        self.store = store
        self.approval_check = approval_check or (lambda _proposal_id: False)

    def propose(
        self,
        *,
        owner_id: str,
        kind: str,
        description: str,
        required_authorities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityProposal:
        if kind not in FUTURE_CAPABILITY_KINDS:
            raise ValueError("unsupported future capability kind")
        proposal_id = uuid4().hex
        payload = {
            "kind": kind,
            "description": description[:4000],
            "required_authorities": sorted(set(item[:200] for item in required_authorities)),
            "execution_authority": False,
            "metadata": dict(metadata or {}),
            "phase": "proposed",
            "created_at": utcnow(),
        }
        self.store.put("future_capability", proposal_id, payload, status="proposed", owner_id=owner_id)
        self.store.audit("future_capability", "proposed", actor=owner_id, subject=proposal_id, payload={"kind": kind})
        return CapabilityProposal(
            proposal_id=proposal_id,
            kind=kind,
            description=payload["description"],
            required_authorities=tuple(payload["required_authorities"]),
            metadata=payload["metadata"],
        )

    def mark_tested(self, proposal_id: str, *, owner_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        row = self._owned(proposal_id, owner_id)
        payload = dict(row["payload"])
        payload.update({"phase": "tested", "evidence": dict(evidence), "tested_at": utcnow(), "execution_authority": False})
        return self.store.put("future_capability", proposal_id, payload, status="tested", owner_id=owner_id)

    def authorize_for_existing_runtime(self, proposal_id: str, *, owner_id: str) -> dict[str, Any]:
        row = self._owned(proposal_id, owner_id)
        if row["status"] != "tested":
            raise RuntimeError("capability must be tested before owner authorization")
        if not self.approval_check(proposal_id):
            raise PermissionError("existing approval authority did not authorize activation")
        payload = dict(row["payload"])
        payload.update({"phase": "approved_for_delegation", "approved_at": utcnow(), "execution_authority": False})
        self.store.audit("future_capability", "approved_for_delegation", actor=owner_id, subject=proposal_id)
        return self.store.put("future_capability", proposal_id, payload, status="approved", owner_id=owner_id)

    def _owned(self, proposal_id: str, owner_id: str) -> dict[str, Any]:
        row = self.store.get("future_capability", proposal_id)
        if row is None:
            raise KeyError(proposal_id)
        if row["owner_id"] != owner_id:
            raise PermissionError("proposal belongs to another owner")
        return row
