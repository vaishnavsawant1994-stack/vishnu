from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .contracts import ReleaseEnvironment, ReleasePlan, ReleaseRiskClass


class ReleaseAutonomyMode(StrEnum):
    OFF = "off"
    PREVIEW_ONLY = "preview_only"
    APPROVAL_REQUIRED = "approval_required"
    AUTO_LOW_RISK = "auto_low_risk"


_SENSITIVE_SURFACE_MARKERS = (
    "auth",
    "authentication",
    "authorization",
    "security",
    "billing",
    "payment",
    "database",
    "migration",
    "credential",
    "secret",
    "provider",
    "owner",
    "permission",
    "release",
    "deploy",
    "runtime",
    "body",
    "evolution",
)


@dataclass(frozen=True)
class ReleaseOwnerPolicy:
    mode: ReleaseAutonomyMode = ReleaseAutonomyMode.APPROVAL_REQUIRED
    allow_production: bool = True
    require_preview: bool = True
    require_exact_revision_evidence: bool = True
    require_production_smoke: bool = True
    require_canary: bool = True
    automatic_risk_ceiling: ReleaseRiskClass = ReleaseRiskClass.LOW
    canary_min_requests: int = 20
    canary_max_error_rate_regression: float = 0.05
    canary_max_latency_ratio: float = 1.35
    allow_automatic_rollback: bool = False
    owner_approval_for_sensitive_surfaces: bool = True
    max_monitoring_observations: int = 1000

    def __post_init__(self) -> None:
        if self.automatic_risk_ceiling is not ReleaseRiskClass.LOW:
            raise ValueError("automatic production is permanently limited to low-risk releases")
        if not self.owner_approval_for_sensitive_surfaces:
            raise ValueError("sensitive release surfaces always require owner approval")
        if self.canary_min_requests < 1:
            raise ValueError("canary_min_requests must be positive")
        if not 0.0 <= self.canary_max_error_rate_regression <= 1.0:
            raise ValueError("canary_max_error_rate_regression must be between 0 and 1")
        if self.canary_max_latency_ratio < 1.0:
            raise ValueError("canary_max_latency_ratio must be at least 1.0")
        if not 1 <= self.max_monitoring_observations <= 100_000:
            raise ValueError("max_monitoring_observations is outside the supported range")

    @staticmethod
    def has_sensitive_surface(plan: ReleasePlan) -> bool:
        values = tuple(item.lower() for item in plan.affected_surfaces)
        return any(marker in value for value in values for marker in _SENSITIVE_SURFACE_MARKERS)

    def can_create_preview(self) -> bool:
        return self.mode is not ReleaseAutonomyMode.OFF

    def requires_owner_approval(self, plan: ReleasePlan) -> bool:
        if plan.requested_environment is not ReleaseEnvironment.PRODUCTION:
            return False
        if self.mode in {ReleaseAutonomyMode.OFF, ReleaseAutonomyMode.PREVIEW_ONLY, ReleaseAutonomyMode.APPROVAL_REQUIRED}:
            return True
        # AUTO_LOW_RISK is a hard product boundary, not a soft owner preference.
        # Medium/high/critical releases and all sensitive surfaces always remain
        # owner-approved even if a persisted policy file is manually edited.
        if plan.risk_class is not ReleaseRiskClass.LOW:
            return True
        if self.has_sensitive_surface(plan):
            return True
        return False

    def allows_automatic_production(self, plan: ReleasePlan) -> bool:
        return (
            self.mode is ReleaseAutonomyMode.AUTO_LOW_RISK
            and self.allow_production
            and plan.risk_class is ReleaseRiskClass.LOW
            and not self.has_sensitive_surface(plan)
            and not self.requires_owner_approval(plan)
        )

    def can_promote(self, plan: ReleasePlan) -> bool:
        if self.mode in {ReleaseAutonomyMode.OFF, ReleaseAutonomyMode.PREVIEW_ONLY}:
            return False
        if not self.allow_production:
            return False
        if self.requires_owner_approval(plan):
            return bool(plan.approved_by and plan.approved_at)
        return True

    def can_execute_rollback(self, *, explicitly_approved: bool) -> bool:
        # Rollback is a separate irreversible authority. It is never implied by
        # canary analysis or by automatic production promotion.
        return self.allow_automatic_rollback and explicitly_approved

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "allow_production": self.allow_production,
            "require_preview": self.require_preview,
            "require_exact_revision_evidence": self.require_exact_revision_evidence,
            "require_production_smoke": self.require_production_smoke,
            "require_canary": self.require_canary,
            "automatic_risk_ceiling": self.automatic_risk_ceiling.label,
            "canary_min_requests": self.canary_min_requests,
            "canary_max_error_rate_regression": self.canary_max_error_rate_regression,
            "canary_max_latency_ratio": self.canary_max_latency_ratio,
            "allow_automatic_rollback": self.allow_automatic_rollback,
            "owner_approval_for_sensitive_surfaces": self.owner_approval_for_sensitive_surfaces,
            "max_monitoring_observations": self.max_monitoring_observations,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ReleaseOwnerPolicy":
        data = data or {}
        return cls(
            mode=ReleaseAutonomyMode(str(data.get("mode", ReleaseAutonomyMode.APPROVAL_REQUIRED.value))),
            allow_production=bool(data.get("allow_production", True)),
            require_preview=bool(data.get("require_preview", True)),
            require_exact_revision_evidence=bool(data.get("require_exact_revision_evidence", True)),
            require_production_smoke=bool(data.get("require_production_smoke", True)),
            require_canary=bool(data.get("require_canary", True)),
            automatic_risk_ceiling=ReleaseRiskClass.parse(data.get("automatic_risk_ceiling", "low")),
            canary_min_requests=int(data.get("canary_min_requests", 20)),
            canary_max_error_rate_regression=float(data.get("canary_max_error_rate_regression", 0.05)),
            canary_max_latency_ratio=float(data.get("canary_max_latency_ratio", 1.35)),
            allow_automatic_rollback=bool(data.get("allow_automatic_rollback", False)),
            owner_approval_for_sensitive_surfaces=bool(data.get("owner_approval_for_sensitive_surfaces", True)),
            max_monitoring_observations=int(data.get("max_monitoring_observations", 1000)),
        )
