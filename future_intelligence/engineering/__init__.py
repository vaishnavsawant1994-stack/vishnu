"""Governed software-engineering intelligence for Vishnu.

This package extends canonical Work and isolated repository workspaces. It is
not a self-evolution, approval, merge, deployment, rollback, or activation authority.
"""

from .api_contracts import ApiContractCase, ApiContractObservation, ApiContractQualifier
from .canary import CanaryMetrics, CanaryThresholds, RollbackRecommendation, compare_canary
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
from .database_qualification import DatabaseQualificationResult, SqliteMigrationSandbox
from .dependency_qualification import DependencyFinding, DependencyQualificationResult, DependencyQualifier
from .environment_qualification import HttpQualificationProbe, ReadOnlyHttpQualificationProvider
from .failure_intelligence import EngineeringFailureStore, FailureFingerprint, FlakyAssessment
from .final_qualification import EngineeringCandidateFinalizer, EngineeringFinalQualificationResult
from .owner_policy import EngineeringOwnerPolicy, EngineeringOwnerPolicyStore
from .portability import EngineeringArtifactClass, EngineeringArtifactPolicy, classify_engineering_artifact, portability_manifest
from .production_feedback import ProductionFeedbackWork, ProductionRegressionWorkBridge
from .release_qualification import PreviewQualificationRequest
from .specialists import (
    ENGINEERING_SPECIALISTS,
    EngineeringSpecialistAdvice,
    EngineeringSpecialistSelector,
    GovernedEngineeringSpecialistConsultations,
)
from .traceability import EngineeringTraceability, RequirementTrace, UserFlowExpectation, UserFlowObservation
from .trusted_qualification import (
    EngineeringTrustedQualificationIntake,
    PhysicalDeviceQualificationEvidence,
    RegressionTestEvidence,
    preview_observation,
)

__all__ = [
    "ApiContractCase",
    "ApiContractObservation",
    "ApiContractQualifier",
    "BrowserEngine",
    "CanaryMetrics",
    "CanaryThresholds",
    "DatabaseQualificationResult",
    "DependencyFinding",
    "DependencyQualificationResult",
    "DependencyQualifier",
    "DeviceProfile",
    "ENGINEERING_SPECIALISTS",
    "EngineeringArtifactClass",
    "EngineeringArtifactPolicy",
    "EngineeringAutonomyMode",
    "EngineeringBudget",
    "EngineeringCandidateFinalizer",
    "EngineeringFailureStore",
    "EngineeringFinalQualificationResult",
    "EngineeringOwnerPolicy",
    "EngineeringOwnerPolicyStore",
    "EngineeringSpec",
    "EngineeringSpecialistAdvice",
    "EngineeringSpecialistSelector",
    "EngineeringTraceability",
    "EngineeringTrustedQualificationIntake",
    "FailureFingerprint",
    "FlakyAssessment",
    "GovernedEngineeringSpecialistConsultations",
    "HttpQualificationProbe",
    "PhysicalDeviceQualificationEvidence",
    "PreviewQualificationRequest",
    "ProductionFeedbackWork",
    "ProductionRegressionWorkBridge",
    "QualificationGateResult",
    "QualificationGateStatus",
    "QualificationReport",
    "ReadOnlyHttpQualificationProvider",
    "RegressionTestEvidence",
    "RequirementTrace",
    "RollbackRecommendation",
    "SecurityClass",
    "SqliteMigrationSandbox",
    "UserFlowExpectation",
    "UserFlowObservation",
    "VisualDefect",
    "classify_engineering_artifact",
    "compare_canary",
    "portability_manifest",
    "preview_observation",
]
