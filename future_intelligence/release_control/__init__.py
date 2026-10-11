"""Governed release and production autonomy.

This package is a separate authority domain from engineering. Engineering may
produce and qualify a candidate; release control decides whether that exact
candidate may enter preview or production under owner policy.
"""

from .contracts import (
    ReleaseEnvironment,
    ReleaseEvidence,
    ReleasePlan,
    ReleaseRiskClass,
    ReleaseStatus,
)
from .controller import GovernedReleaseController, ReleaseControlError
from .policy import ReleaseAutonomyMode, ReleaseOwnerPolicy
from .providers import ReleaseDeployment, ReleaseProvider
from .store import JsonReleaseStore, ReleaseStore

__all__ = [
    "GovernedReleaseController",
    "JsonReleaseStore",
    "ReleaseAutonomyMode",
    "ReleaseControlError",
    "ReleaseDeployment",
    "ReleaseEnvironment",
    "ReleaseEvidence",
    "ReleaseOwnerPolicy",
    "ReleasePlan",
    "ReleaseProvider",
    "ReleaseRiskClass",
    "ReleaseStatus",
    "ReleaseStore",
]
