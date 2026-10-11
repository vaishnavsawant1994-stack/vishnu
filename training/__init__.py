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
from training.contribution_settings import ContributionSettingsService, ContributionSettingsSnapshot
from training.contributions import (
    ContributionDecision,
    ContributionKind,
    ContributionMode,
    ContributionPreferences,
    ContributorPseudonymizer,
    StrategySignalAggregator,
    evaluate_contribution,
)
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
    GovernedModelDeploymentController as _GovernedModelDeploymentController,
    GovernedTrainingDatasetSnapshotBuilder as TrainingDatasetSnapshotBuilder,
    GovernedTrainingRegistry as TrainingRegistry,
    GovernedTrainingSettingsService as TrainingSettingsService,
    ShadowQualificationRuntime,
    ShadowResult,
    TrainingGovernanceLedger,
)
from training.remote_gpu import (
    RemoteGpuProvider,
    RemoteGpuProviderCapabilities,
    RemoteGpuTrainerBackend,
    RemoteGpuTrainingPolicy,
    RemoteTrainingJob,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTrainingState,
)
from training.runtime_controls import BoundedLocalPeftTrainerBackend as LocalPeftTrainerBackend
from training.store import TrainingCandidateStore


class ModelDeploymentController(_GovernedModelDeploymentController):
    """Release-controller deployment/rollback boundary.

    Automatic rollback is not model authority. A trusted release/health monitor
    may report a verified production regression to this controller; rollback is
    executed only when the owner setting is enabled and a configured deployment
    backend can prove the previous known-good checkpoint is running. The model,
    evaluator and consensus layers cannot call themselves approved or activate a
    checkpoint through this surface.
    """

    def __init__(self, registry, *, backends=None, events=None, settings=None) -> None:
        super().__init__(registry, backends=backends, events=events)
        self.settings = settings

    def handle_verified_regression(
        self,
        active_model_id: str,
        *,
        backend_id: str,
        actor: str = 'release_health_monitor',
    ):
        if self.settings is None:
            return {
                'rolled_back': False,
                'reason': 'automatic_rollback_settings_unavailable',
            }
        config = self.settings.snapshot()
        if not bool(getattr(config, 'automatic_rollback', False)):
            return {
                'rolled_back': False,
                'reason': 'automatic_rollback_disabled',
            }
        model, result = self.rollback(
            active_model_id,
            backend_id=backend_id,
            actor=str(actor or 'release_health_monitor'),
        )
        return {
            'rolled_back': True,
            'model_id': model.model_id,
            'checkpoint_ref': result.checkpoint_ref,
            'deployment_ref': result.deployment_ref,
            'actor': str(actor or 'release_health_monitor'),
        }

    def status(self):
        value = super().status()
        enabled = False
        if self.settings is not None:
            try:
                enabled = bool(self.settings.snapshot().automatic_rollback)
            except Exception:
                enabled = False
        value['automatic_rollback_enabled'] = enabled
        value['automatic_rollback_trigger_authority'] = 'release_health_monitor'
        value['model_can_trigger_rollback'] = False
        return value


__all__ = [
    'CandidateStatus',
    'PrivacyLevel',
    'TrainingCandidate',
    'TrainingCandidateFactory',
    'TrainingCandidateStore',
    'TrainingCollector',
    'TrainingDatasetExporter',
    'TrainingExport',
    'ContributionDecision',
    'ContributionKind',
    'ContributionMode',
    'ContributionPreferences',
    'ContributionSettingsService',
    'ContributionSettingsSnapshot',
    'ContributorPseudonymizer',
    'StrategySignalAggregator',
    'evaluate_contribution',
    'AutoTrainingCoordinator',
    'AutoTrainingRuntime',
    'AutoTrainingSettings',
    'EvaluationResult',
    'FailClosedEvaluator',
    'LocalCheckpointEvaluator',
    'LocalPeftTrainerBackend',
    'RemoteGpuProvider',
    'RemoteGpuProviderCapabilities',
    'RemoteGpuTrainerBackend',
    'RemoteGpuTrainingPolicy',
    'RemoteTrainingJob',
    'RemoteTrainingRequest',
    'RemoteTrainingResult',
    'RemoteTrainingState',
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
