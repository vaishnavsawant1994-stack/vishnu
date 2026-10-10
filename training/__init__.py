"""Governed training-data foundations for Vishnu.

Training capture may be enabled by product policy, but captured interactions are
candidates only. Promotion into an approved dataset requires explicit governance
checks implemented by this package.
"""

from training.candidates import (
    CandidateStatus,
    PrivacyLevel,
    TrainingCandidate,
    TrainingCandidateFactory,
)

__all__ = [
    'CandidateStatus',
    'PrivacyLevel',
    'TrainingCandidate',
    'TrainingCandidateFactory',
]
