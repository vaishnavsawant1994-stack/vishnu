"""Vishnu production readiness, owner trust and universal continuity layer.

This package coordinates existing Vishnu authorities. It does not grant device,
computer, sensor, IoT, credential or execution authority by itself.
"""

from .adapters import KeychainSecretStore
from .future_extensions import (
    FUTURE_CAPABILITY_KINDS,
    CapabilityProposal,
    GovernedFutureCapabilities,
)
from .identity_continuity import (
    DATA_POLICIES,
    MultiDeviceContinuity,
    RecoveryResult,
    UniversalOwnerRecovery,
)
from .memory_intelligence import MemoryIntelligence
from .operations import OperationalHealthMonitor, ProbeResult
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
from .runtime import TrustContinuityRuntime, build_trust_continuity_runtime
from .services import (
    EvaluationLab,
    OAuthLifecycleManager,
    OfflineIntelligence,
    SecretStore,
    TrustCenter,
)
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
    "KeychainSecretStore",
    "MemoryIntelligence",
    "MultiDeviceContinuity",
    "NON_PHYSICAL_PROVIDERS",
    "OAuthLifecycleManager",
    "OfflineIntelligence",
    "OperationalHealthMonitor",
    "PHYSICAL_PLATFORMS",
    "PRODUCTION_REQUIREMENTS",
    "PhysicalL4Qualification",
    "ProbeResult",
    "ProductionReadinessManager",
    "ReadinessResult",
    "RecoveryResult",
    "SecretStore",
    "TrustCenter",
    "TrustContinuityRuntime",
    "TrustContinuityStore",
    "UniversalOwnerRecovery",
    "WorkEngineV2",
    "bounded_json",
    "build_trust_continuity_runtime",
    "utcnow",
]
