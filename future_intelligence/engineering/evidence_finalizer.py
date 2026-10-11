from __future__ import annotations

from .final_qualification import EngineeringCandidateFinalizer


class EvidenceAwareEngineeringFinalizer(EngineeringCandidateFinalizer):
    """Compatibility name for the canonical evidence-aware finalizer.

    Trusted physical-device evidence and reserved-gate enforcement now live in
    EngineeringCandidateFinalizer itself so desktop, cloud and release-aware
    finalization all share the same fail-closed behavior.
    """

    pass
