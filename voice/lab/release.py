"""Immutable release-candidate manifests; never mutates production or Git refs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from .catalog import CapabilityState, find_capability
from .evaluation import BASELINE_REQUIRED_GATES
from .evidence import EvidenceStore


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


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
        self.evidence = evidence

    def prepare(self, capability_ids: tuple[str, ...], evidence_ids: tuple[str, ...]) -> ReleaseCandidate:
        reasons = []
        if not capability_ids or not evidence_ids:
            reasons.append("capabilities and evidence are required")
        for capability_id in capability_ids:
            capability = find_capability(capability_id)
            if capability is None:
                reasons.append(f"unknown capability: {capability_id}")
            elif capability.state is CapabilityState.GAP:
                reasons.append(f"capability is a known gap: {capability_id}")
        evidence_digests = []
        for evidence_id in evidence_ids:
            row = self.evidence.get(evidence_id)
            if row is None:
                reasons.append(f"missing evidence: {evidence_id}")
                continue
            gates = row.get("gates", [])
            for gate_id in BASELINE_REQUIRED_GATES:
                matches = [gate for gate in gates if gate.get("gate_id") == gate_id]
                if len(matches) != 1:
                    reasons.append(f"evidence does not contain exactly one {gate_id} gate: {evidence_id}")
                elif matches[0].get("status") != "pass":
                    reasons.append(f"evidence baseline gate did not pass: {gate_id}: {evidence_id}")
            if any(gate.get("status") != "pass" for gate in gates):
                reasons.append(f"evidence contains non-passing scenario/regression gates: {evidence_id}")
            evidence_digests.append(row.get("digest"))
        if reasons:
            raise ValueError("; ".join(reasons))
        created = datetime.now(timezone.utc).isoformat()
        body = {
            "capability_ids": capability_ids,
            "evidence_ids": evidence_ids,
            "evidence_digests": evidence_digests,
            "created_at": created,
        }
        manifest = _digest(body)
        return ReleaseCandidate("vlrc-" + manifest[:20], capability_ids, evidence_ids, created, manifest)

    def approve(self, candidate: ReleaseCandidate, *, owner_id: str, attestation: str) -> ReleaseApproval:
        if not owner_id.strip() or not attestation.strip():
            raise ValueError("explicit owner identity and attestation are required")
        return ReleaseApproval(
            candidate.candidate_id,
            candidate.manifest_digest,
            owner_id,
            datetime.now(timezone.utc).isoformat(),
            attestation,
        )

    def evaluate(self, candidate: ReleaseCandidate, approval: ReleaseApproval | None) -> ReleaseDecision:
        reasons = []
        if approval is None:
            reasons.append("explicit owner approval is required")
        elif approval.candidate_id != candidate.candidate_id or approval.manifest_digest != candidate.manifest_digest:
            reasons.append("approval does not bind the exact immutable candidate manifest")
        return ReleaseDecision(not reasons, tuple(reasons))
