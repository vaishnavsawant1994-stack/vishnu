"""Governed release and production autonomy.

This package is a separate authority domain from engineering. Engineering may
produce and qualify a candidate; release control decides whether that exact
candidate may enter preview or production under owner policy.
"""

from .automation import ReleaseAutomationService, ReleaseHandoffResult
from .contracts import (
    ReleaseEnvironment,
    ReleaseEvidence,
    ReleasePlan,
    ReleaseRiskClass,
    ReleaseStatus,
)
from .controller import GovernedReleaseController, ReleaseControlError
from .feedback import RegressionAwareProductionSmokeProvider
from .monitoring import ProductionReleaseMonitor, ReleaseMonitorResult
from .policy import ReleaseAutonomyMode, ReleaseOwnerPolicy
from .policy_store import ReleasePolicyStore
from .providers import ReleaseDeployment, ReleaseProvider
from .recovery import ReleaseRecoveryResult, ReleaseRecoveryService
from .render_provider import RenderReleaseConfig, RenderReleaseProvider
from .runtime import ReleaseControlRuntime, build_release_control_runtime
from .store import JsonReleaseStore, ReleaseStore
from .vercel_provider import VercelReleaseConfig, VercelReleaseProvider

__all__ = [
    "GovernedReleaseController",
    "JsonReleaseStore",
    "ProductionReleaseMonitor",
    "RegressionAwareProductionSmokeProvider",
    "ReleaseAutonomyMode",
    "ReleaseAutomationService",
    "ReleaseControlError",
    "ReleaseControlRuntime",
    "ReleaseDeployment",
    "ReleaseEnvironment",
    "ReleaseEvidence",
    "ReleaseHandoffResult",
    "ReleaseMonitorResult",
    "ReleaseOwnerPolicy",
    "ReleasePlan",
    "ReleasePolicyStore",
    "ReleaseProvider",
    "ReleaseRecoveryResult",
    "ReleaseRecoveryService",
    "ReleaseRiskClass",
    "ReleaseStatus",
    "ReleaseStore",
    "RenderReleaseConfig",
    "RenderReleaseProvider",
    "VercelReleaseConfig",
    "VercelReleaseProvider",
    "build_release_control_runtime",
]
