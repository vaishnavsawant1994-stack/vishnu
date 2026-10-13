from __future__ import annotations

from .models import CapabilityRisk, CapabilitySpec, RiskAssessment


class CapabilityRiskMapper:
    """Translate a frozen spec into a conservative Forge risk observation.

    This is advisory only. Existing Vishnu policy/approval systems remain the
    execution authority.
    """

    DESTRUCTIVE_WORDS = frozenset({"delete", "destroy", "terminate", "revoke", "erase", "drop", "remove"})
    WRITE_WORDS = frozenset({"write", "send", "create", "update", "modify", "post", "publish", "purchase", "transfer"})

    def assess(self, spec: CapabilitySpec) -> RiskAssessment:
        reasons: list[str] = []
        operations = {str(item).strip().lower() for item in spec.required_operations}
        effects = {str(item).strip().lower() for item in spec.side_effects}
        tokens = operations | effects
        destructive = any(any(word in token for word in self.DESTRUCTIVE_WORDS) for token in tokens)
        writes = bool(spec.filesystem_write) or any(any(word in token for word in self.WRITE_WORDS) for token in tokens)
        authority_expansion = bool(spec.network_hosts or spec.filesystem_read or spec.filesystem_write or spec.secret_names or spec.connector_ids)

        if destructive:
            risk = CapabilityRisk.DESTRUCTIVE
            reasons.append("declared operation may irreversibly remove or revoke state")
        elif writes:
            risk = CapabilityRisk.WRITE
            reasons.append("declared operation can change external or filesystem state")
        else:
            risk = CapabilityRisk.READ
            reasons.append("declared operations are read-oriented")

        if spec.network_hosts:
            reasons.append("requests network authority")
        if spec.secret_names:
            reasons.append("requests secret access")
        if spec.filesystem_write:
            reasons.append("requests filesystem write authority")
        elif spec.filesystem_read:
            reasons.append("requests filesystem read authority")
        if spec.connector_ids:
            reasons.append("requests connector authority")
        if spec.background_allowed:
            reasons.append("may run in background")

        owner_review = risk is not CapabilityRisk.READ or authority_expansion
        return RiskAssessment(
            risk=risk,
            reasons=tuple(reasons),
            owner_review_required=owner_review,
            authority_expansion=authority_expansion,
        )
