"""Capability Forge intelligence.

The F1 package detects and specifies reusable capability gaps and selects the
narrowest governed implementation route. It does not execute or activate code.
"""

from .gap_detector import CapabilityGapDetector
from .models import (
    CapabilityGap,
    CapabilityPlan,
    CapabilityRisk,
    CapabilityRoute,
    CapabilitySpec,
    GapSource,
    GapStatus,
    RiskAssessment,
)
from .planner import CapabilityPlanner
from .risk_mapper import CapabilityRiskMapper
from .service import CapabilityForgeService
from .spec_builder import CapabilitySpecBuilder
from .store import CapabilityForgeStore

__all__ = [
    "CapabilityForgeService",
    "CapabilityForgeStore",
    "CapabilityGap",
    "CapabilityGapDetector",
    "CapabilityPlan",
    "CapabilityPlanner",
    "CapabilityRisk",
    "CapabilityRiskMapper",
    "CapabilityRoute",
    "CapabilitySpec",
    "CapabilitySpecBuilder",
    "GapSource",
    "GapStatus",
    "RiskAssessment",
]
