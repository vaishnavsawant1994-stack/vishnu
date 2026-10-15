"""Vishnu production readiness, owner trust and universal continuity layer.

This package coordinates existing Vishnu authorities. It does not grant device,
computer, sensor, IoT, credential or execution authority by itself.
"""

from .future_extensions import CapabilityProposal, FUTURE_CAPABILITY_KINDS, GovernedFutureCapabilities
from .identity_continuity import DATA_POLICIES, MultiDeviceContinuity, RecoveryResult, UniversalOwnerRecovery
from .memory_intelligence import MemoryIntelligence
from .production import (
    NON_PHYSICAL_PROVIDERS,
    PHYSICAL_PLATFORMS,
    PRODUCTION_REQUIREMENTS,
    BackupRestoreVerifier,
    DeploymentTransaction,
    PhysicalL4Qualification,
    ProductionReadinessManager,
    ReadinessResult,
)
from .services import EvaluationLab, OAuthLifecycleManager, OfflineIntelligence, SecretStore, TrustCenter
from .store import TrustContinuityStore, bounded_json, utcnow
from .work_engine import WorkEngineV2

__all__ = [
    "BackupRestoreVerifier",
    "CapabilityProposal",
    "DATA_POLICIES",
    "DeploymentTransaction",
    "EvaluationLab",
    "FUTURE_CAPABILITY_KINDS",
    "GovernedFutureCapabilities",
    "MemoryIntelligence",
    "MultiDeviceContinuity",
    "NON_PHYSICAL_PROVIDERS",
    "OAuthLifecycleManager",
    "OfflineIntelligence",
    "PHYSICAL_PLATFORMS",
    "PRODUCTION_REQUIREMENTS",
    "PhysicalL4Qualification",
    "ProductionReadinessManager",
    "ReadinessResult",
    "RecoveryResult",
    "SecretStore",
    "TrustCenter",
    "TrustContinuityStore",
    "UniversalOwnerRecovery",
    "WorkEngineV2",
    "bounded_json",
    "utcnow",
]
