from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .config import CapabilityLevel, LabSettings
from .models import ActionProposal, SimulationResult


@dataclass(frozen=True)
class SafetyVerdict:
    allowed: bool
    reasons: tuple[str, ...]
    requires_core_governance: bool = True

    def public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "requires_core_governance": self.requires_core_governance,
        }


class LabSafetyPolicy:
    """Lab-side defense in depth; Vishnu Core remains the execution authority."""

    _FORBIDDEN_DIRECT = {
        "disable_emergency_stop",
        "bypass_approval",
        "read_secret_vault",
        "export_credentials",
        "rewrite_security_policy",
        "mutate_trusted_memory",
        "self_promote",
    }

    def __init__(self, settings: LabSettings):
        self.settings = settings

    def evaluate_proposal(self, proposal: ActionProposal) -> SafetyVerdict:
        action = proposal.action.strip().lower()
        reasons: list[str] = []
        if action in self._FORBIDDEN_DIRECT:
            reasons.append("action is forbidden to the Intelligence Lab")
        if any(token in action for token in ("bypass", "disable_security", "steal_secret")):
            reasons.append("action appears to request a security-boundary bypass")
        if not action:
            reasons.append("action is empty")
        return SafetyVerdict(not reasons, tuple(reasons))

    def assert_autonomous(self, proposal: ActionProposal, *, preauthorized: bool) -> None:
        self.settings.require(CapabilityLevel.LIMITED_AUTONOMY)
        if not preauthorized:
            raise PermissionError("limited autonomy requires explicit preauthorization")
        if proposal.action not in set(self.settings.autonomous_allowlist):
            raise PermissionError("proposal action is not in the Intelligence Lab autonomy allowlist")
        verdict = self.evaluate_proposal(proposal)
        if not verdict.allowed:
            raise PermissionError("; ".join(verdict.reasons))


class SimulationEngine:
    """Predicts effects without any callable path to Vishnu Core execution."""

    def simulate(
        self,
        proposal: ActionProposal,
        *,
        world: Mapping[str, Any] | None = None,
    ) -> SimulationResult:
        world = dict(world or {})
        action = proposal.action.lower()
        effects = [f"Would request Vishnu Core to evaluate action '{proposal.action}'."]
        risks: list[str] = []
        if proposal.parameters:
            effects.append(f"Would provide {len(proposal.parameters)} structured parameter fields to Core governance.")
        if any(word in action for word in ("delete", "remove", "destroy", "revoke")):
            risks.append("potentially destructive or availability-reducing effect")
        if any(word in action for word in ("send", "publish", "deploy", "purchase", "pay", "execute")):
            risks.append("potential external side effect")
        if any(word in action for word in ("security", "credential", "permission", "password", "passkey")):
            risks.append("security-sensitive effect")
        if proposal.risk.lower() not in {"low", "read_only", "readonly"}:
            risks.append(f"proposal-declared risk: {proposal.risk}")
        assumptions = [
            "Simulation has no execution authority.",
            "Vishnu Core may reject, alter, or require approval for the proposal.",
            "Predicted effects are not proof of real-world outcomes.",
        ]
        if not world:
            assumptions.append("No current world-state evidence was supplied.")
        confidence = 0.65 if world else 0.45
        return SimulationResult(
            proposal_id=proposal.id,
            predicted_effects=tuple(effects),
            risks=tuple(dict.fromkeys(risks)),
            assumptions=tuple(assumptions),
            confidence=confidence,
            executed=False,
        )
