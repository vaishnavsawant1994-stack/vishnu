"""Governed software-engineering intelligence for Vishnu.

This package extends canonical Work and isolated repository workspaces. It is
not a self-evolution, approval, merge, deployment, or activation authority.
"""

from .contracts import (
    BrowserEngine,
    DeviceProfile,
    EngineeringAutonomyMode,
    EngineeringBudget,
    EngineeringSpec,
    QualificationGateResult,
    QualificationGateStatus,
    QualificationReport,
    SecurityClass,
    VisualDefect,
)
from .environment_qualification import HttpQualificationProbe, ReadOnlyHttpQualificationProvider
from .owner_policy import EngineeringOwnerPolicy, EngineeringOwnerPolicyStore
from .production_feedback import ProductionFeedbackWork, ProductionRegressionWorkBridge

__all__ = [
    "BrowserEngine",
    "DeviceProfile",
    "EngineeringAutonomyMode",
    "EngineeringBudget",
    "EngineeringSpec",
    "QualificationGateResult",
    "QualificationGateStatus",
    "QualificationReport",
    "SecurityClass",
    "VisualDefect",
    "HttpQualificationProbe",
    "ReadOnlyHttpQualificationProvider",
    "EngineeringOwnerPolicy",
    "EngineeringOwnerPolicyStore",
    "ProductionFeedbackWork",
    "ProductionRegressionWorkBridge",
]
