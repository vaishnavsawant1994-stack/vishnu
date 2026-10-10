"""Governed training and self-improvement foundations for Vishnu.

Training capture may be enabled by product policy, but captured interactions are
candidates only. Dataset creation, weight training, evaluation, promotion and
activation are separate governed stages. Model training can be automated;
production activation cannot self-authorize.
"""

from training.candidates import (
    CandidateStatus,
    PrivacyLevel,
    TrainingCandidate,
    TrainingCandidateFactory,
)
from training.collector import TrainingCollector
from training.exporter import TrainingDatasetExporter, TrainingExport
from training.self_improvement import (
    AutoTrainingCoordinator,
    AutoTrainingRuntime,
    AutoTrainingSettings,
    EvaluationResult,
    FailClosedEvaluator,
    LocalPeftTrainerBackend,
    TrainedModel,
    TrainedModelStatus,
    TrainingArtifact,
    TrainingDatasetSnapshot,
    TrainingDatasetSnapshotBuilder,
    TrainingJob,
    TrainingJobStatus,
    TrainingMethod,
    TrainingRegistry,
    TrainingSettingsService,
    UnavailableTrainerBackend,
)
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
]
