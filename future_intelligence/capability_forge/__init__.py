"""Capability Forge intelligence and governed generated-capability lifecycle."""

from .action_runtime import GeneratedActionService
from .activation import CapabilityActivationService, ForgeActivationDecision
from .automation_bridge import CapabilityForgeAutomationBridge
from .build_service import CapabilityForgeBuildService
from .evaluator import GeneratedCapabilityEvaluator, GeneratedCapabilityHealth
from .event_bridge import FORGE_OBSERVED_EVENTS, attach_capability_forge_observers
from .execution_bridge import CapabilityForgeExecutionBridge, ForgeCandidateResult
from .gap_detector import CapabilityGapDetector
from .improvement import CapabilityImprovementService
from .lifecycle import CapabilityForgeLifecycle
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
from .package import CapabilityPackageBuilder, PackagedCapability
from .planner import CapabilityPlanner
from .risk_mapper import CapabilityRiskMapper
from .runtime import build_capability_forge
from .service import CapabilityForgeService
from .spec_builder import CapabilitySpecBuilder
from .store import CapabilityForgeStore
from .ui_contract import GeneratedUIContractError, validate_generated_ui_contract
from .work_bridge import CapabilityForgeWorkBridge, ForgeWorkProjection

__all__ = [
    "CapabilityActivationService",
    "CapabilityForgeAutomationBridge",
    "CapabilityForgeBuildService",
    "CapabilityForgeExecutionBridge",
    "CapabilityForgeLifecycle",
    "CapabilityForgeService",
    "CapabilityForgeStore",
    "CapabilityForgeWorkBridge",
    "CapabilityGap",
    "CapabilityGapDetector",
    "CapabilityImprovementService",
    "CapabilityPackageBuilder",
    "CapabilityPlan",
    "CapabilityPlanner",
    "CapabilityRisk",
    "CapabilityRiskMapper",
    "CapabilityRoute",
    "CapabilitySpec",
    "CapabilitySpecBuilder",
    "FORGE_OBSERVED_EVENTS",
    "ForgeActivationDecision",
    "ForgeCandidateResult",
    "ForgeWorkProjection",
    "GapSource",
    "GapStatus",
    "GeneratedActionService",
    "GeneratedCapabilityEvaluator",
    "GeneratedCapabilityHealth",
    "GeneratedUIContractError",
    "PackagedCapability",
    "RiskAssessment",
    "attach_capability_forge_observers",
    "build_capability_forge",
    "validate_generated_ui_contract",
]
