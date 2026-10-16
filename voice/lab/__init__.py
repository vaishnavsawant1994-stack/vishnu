"""Isolated Vishnu Voice Lab qualification framework.

The package is intentionally inert on import. It provides inventory, experiment,
evidence and promotion-policy primitives without starting providers or touching
production voice configuration.
"""

from .catalog import CapabilityState, VoiceCapability, all_capabilities, find_capability, gaps
from .evaluation import (
    BASELINE_REQUIRED_GATES,
    GateStatus,
    QualificationGate,
    ReportStatus,
    VoiceLabReport,
    passed_gate,
)
from .experiments import VoiceExperimentSpec
from .promotion import PromotionDecision, PromotionRequest, evaluate_promotion

__all__ = [
    "BASELINE_REQUIRED_GATES",
    "CapabilityState",
    "GateStatus",
    "PromotionDecision",
    "PromotionRequest",
    "QualificationGate",
    "ReportStatus",
    "VoiceCapability",
    "VoiceExperimentSpec",
    "VoiceLabReport",
    "all_capabilities",
    "evaluate_promotion",
    "find_capability",
    "gaps",
    "passed_gate",
]
