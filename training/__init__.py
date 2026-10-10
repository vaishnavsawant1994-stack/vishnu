"""Governed training and self-improvement foundations for Vishnu.

Training Capture is enabled by default, but captured interactions are candidates
only. Secret/privacy/provenance/quality eligibility, dataset approval, weight
training, evaluation, live shadow qualification, promotion and activation are
separate governed stages. Model training can be automated; production
activation cannot self-authorize.
"""

from training.candidates import (
    CandidateStatus,
    PrivacyLevel,
    TrainingCandidate,
    TrainingCandidateFactory,
)
from training.collector import TrainingCollector
from training.comprehensive_evaluation import ComprehensiveCheckpointEvaluator as LocalCheckpointEvaluator
from training.deployment import (
    DeploymentResult,
    ModelDeploymentBackend,
    UnavailableDeploymentBackend,
)
from training.exporter import TrainingDatasetExporter, TrainingExport
from training.self_improvement import (
    AutoTrainingRuntime,
    EvaluationResult,
    FailClosedEvaluator,
    TrainedModel,
    TrainedModelStatus,
    TrainingArtifact,
    TrainingDatasetSnapshot,
    TrainingJob,
    TrainingJobStatus,
    TrainingMethod,
    UnavailableTrainerBackend,
)
from training.governance import (
    GovernedAutoTrainingCoordinator as AutoTrainingCoordinator,
    GovernedAutoTrainingSettings as AutoTrainingSettings,
    GovernedModelDeploymentController as ModelDeploymentController,
    GovernedTrainingDatasetSnapshotBuilder as TrainingDatasetSnapshotBuilder,
    GovernedTrainingRegistry as TrainingRegistry,
    GovernedTrainingSettingsService as TrainingSettingsService,
    ShadowQualificationRuntime,
    ShadowResult,
    TrainingGovernanceLedger,
)
from training.runtime_controls import BoundedLocalPeftTrainerBackend as LocalPeftTrainerBackend
from training.store import TrainingCandidateStore

__all__ = [
    'CandidateStatus',
    'PrivacyLevel',
    'TrainingCandidate',
    'TrainingCandidateFactory',
    'TrainingCandidateStore',
    'TrainingCollector',
    'TrainingDatasetExporter',
    'TrainingExport',
    'AutoTrainingCoordinator',
    'AutoTrainingRuntime',
    'AutoTrainingSettings',
    'EvaluationResult',
    'FailClosedEvaluator',
    'LocalCheckpointEvaluator',
    'LocalPeftTrainerBackend',
    'TrainedModel',
    'TrainedModelStatus',
    'TrainingArtifact',
    'TrainingDatasetSnapshot',
    'TrainingDatasetSnapshotBuilder',
    'TrainingJob',
    'TrainingJobStatus',
    'TrainingMethod',
    'TrainingRegistry',
    'TrainingSettingsService',
    'UnavailableTrainerBackend',
    'DeploymentResult',
    'ModelDeploymentBackend',
    'ModelDeploymentController',
    'UnavailableDeploymentBackend',
    'ShadowQualificationRuntime',
    'ShadowResult',
    'TrainingGovernanceLedger',
]
