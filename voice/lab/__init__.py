"""Isolated Vishnu Voice Lab execution and qualification framework.

Importing this package is inert: it does not start audio devices/providers, download models,
read credentials, create an evidence database, or change production voice configuration.
"""

from .benchmarks import BenchmarkEngine, character_error_rate, retention_score, word_error_rate
from .catalog import CapabilityState, VoiceCapability, all_capabilities, find_capability, gaps, qualification_required
from .comparison import ComparisonCandidate, ProviderComparison
from .dashboard import VOICE_LAB_SECTIONS, VoiceLabDashboardSnapshot, snapshot
from .devices import (
    DeviceClass,
    DeviceQualificationEvidence,
    NativeDeviceSoftwareEvidence,
    native_software_evidence,
    native_software_gate,
    physical_acoustics_gate,
)
from .evaluation import BASELINE_REQUIRED_GATES, GateStatus, QualificationGate, ReportStatus, VoiceLabReport, passed_gate
from .evidence import EvidenceRecord, EvidenceStore
from .experiments import VoiceExperimentSpec
from .fixtures import FixtureKind, FixtureRegistry, VoiceFixture, builtin_fixture_ids
from .promotion import PromotionDecision, PromotionRequest, evaluate_promotion
from .regression import DEFAULT_REGRESSION_RULES, MetricDirection, RegressionEngine, RegressionRule
from .release import ReleaseApproval, ReleaseCandidate, ReleaseDecision, ReleaseManager
from .runner import AdapterResult, ExperimentRun, LabAdapter, LabRunControl, VoiceExperimentRunner

__all__ = [
    "AdapterResult",
    "BASELINE_REQUIRED_GATES",
    "BenchmarkEngine",
    "CapabilityState",
    "ComparisonCandidate",
    "DEFAULT_REGRESSION_RULES",
    "DeviceClass",
    "DeviceQualificationEvidence",
    "EvidenceRecord",
    "EvidenceStore",
    "ExperimentRun",
    "FixtureKind",
    "FixtureRegistry",
    "GateStatus",
    "LabAdapter",
    "LabRunControl",
    "MetricDirection",
    "NativeDeviceSoftwareEvidence",
    "PromotionDecision",
    "PromotionRequest",
    "ProviderComparison",
    "QualificationGate",
    "RegressionEngine",
    "RegressionRule",
    "ReleaseApproval",
    "ReleaseCandidate",
    "ReleaseDecision",
    "ReleaseManager",
    "ReportStatus",
    "VOICE_LAB_SECTIONS",
    "VoiceCapability",
    "VoiceExperimentRunner",
    "VoiceExperimentSpec",
    "VoiceFixture",
    "VoiceLabDashboardSnapshot",
    "VoiceLabReport",
    "all_capabilities",
    "builtin_fixture_ids",
    "character_error_rate",
    "evaluate_promotion",
    "find_capability",
    "gaps",
    "native_software_evidence",
    "native_software_gate",
    "passed_gate",
    "physical_acoustics_gate",
    "qualification_required",
    "retention_score",
    "snapshot",
    "word_error_rate",
]
