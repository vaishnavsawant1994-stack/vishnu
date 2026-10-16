"""Immutable release-candidate manifests; never mutates production or Git refs."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json

from .catalog import CapabilityState, find_capability
from .evidence import EvidenceStore


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseCandidate:
    candidate_id: str
    capability_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    created_at: str
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class ReleaseApproval:
    candidate_id: str
    manifest_digest: str
    owner_id: str
    approved_at: str
    attestation: str


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    allowed: bool
    reasons: tuple[str, ...]


class ReleaseManager:
    def __init__(self, evidence: EvidenceStore):
        self.evidence=evidence

    def prepare(self, capability_ids: tuple[str, ...], evidence_ids: tuple[str, ...]) -> ReleaseCandidate:
        reasons=[]
        if not capability_ids or not evidence_ids: reasons.append("capabilities and evidence are required")
        for cid in capability_ids:
            cap=find_capability(cid)
            if cap is None: reasons.append(f"unknown capability: {cid}")
            elif cap.state is CapabilityState.GAP: reasons.append(f"capability is a known gap: {cid}")
        rows=[]
        for eid in evidence_ids:
            row=self.evidence.get(eid)
            if row is None: reasons.append(f"missing evidence: {eid}"); continue
            if any(g.get("status") != "pass" for g in row.get("gates",[])): reasons.append(f"evidence is not fully passing: {eid}")
            rows.append(row.get("digest"))
        if reasons: raise ValueError("; ".join(reasons))
        created=datetime.now(timezone.utc).isoformat()
        body={"capability_ids":capability_ids,"evidence_ids":evidence_ids,"evidence_digests":rows,"created_at":created}
        manifest=_digest(body)
        return ReleaseCandidate("vlrc-"+manifest[:20],capability_ids,evidence_ids,created,manifest)

    def approve(self, candidate: ReleaseCandidate, *, owner_id: str, attestation: str) -> ReleaseApproval:
        if not owner_id.strip() or not attestation.strip(): raise ValueError("explicit owner identity and attestation are required")
        return ReleaseApproval(candidate.candidate_id,candidate.manifest_digest,owner_id,datetime.now(timezone.utc).isoformat(),attestation)

    def evaluate(self, candidate: ReleaseCandidate, approval: ReleaseApproval | None) -> ReleaseDecision:
        reasons=[]
        if approval is None: reasons.append("explicit owner approval is required")
        elif approval.candidate_id != candidate.candidate_id or approval.manifest_digest != candidate.manifest_digest:
            reasons.append("approval does not bind the exact immutable candidate manifest")
        return ReleaseDecision(not reasons,tuple(reasons))
