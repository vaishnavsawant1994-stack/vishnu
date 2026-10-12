"""Capability Forge intelligence.

The F1 package detects and specifies reusable capability gaps and selects the
narrowest governed implementation route. It does not execute or activate code.
"""

from .event_bridge import FORGE_OBSERVED_EVENTS, attach_capability_forge_observers
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
from .runtime import build_capability_forge
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
    "FORGE_OBSERVED_EVENTS",
    "GapSource",
    "GapStatus",
    "RiskAssessment",
    "attach_capability_forge_observers",
    "build_capability_forge",
]
