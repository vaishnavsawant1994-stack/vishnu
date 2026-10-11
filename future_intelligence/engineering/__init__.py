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
from .owner_policy import EngineeringOwnerPolicy, EngineeringOwnerPolicyStore
from .portability import EngineeringArtifactClass, EngineeringArtifactPolicy, classify_engineering_artifact, portability_manifest
from .production_feedback import ProductionFeedbackWork, ProductionRegressionWorkBridge
from .traceability import EngineeringTraceability, RequirementTrace, UserFlowExpectation, UserFlowObservation

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
    "EngineeringArtifactClass",
    "EngineeringArtifactPolicy",
    "EngineeringAutonomyMode",
    "EngineeringBudget",
    "EngineeringFailureStore",
    "EngineeringOwnerPolicy",
    "EngineeringOwnerPolicyStore",
    "EngineeringSpec",
    "EngineeringTraceability",
    "FailureFingerprint",
    "FlakyAssessment",
    "HttpQualificationProbe",
    "ProductionFeedbackWork",
    "ProductionRegressionWorkBridge",
    "QualificationGateResult",
    "QualificationGateStatus",
    "QualificationReport",
    "ReadOnlyHttpQualificationProvider",
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
]
