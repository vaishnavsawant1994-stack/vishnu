from __future__ import annotations

from types import MethodType
from typing import Callable

from models.contracts import RoutingCandidate


MAX_SCORE_ADJUSTMENT = 0.05


def _task_domain(request) -> str:
    metadata = request.metadata if isinstance(getattr(request, 'metadata', None), dict) else {}
    return str(metadata.get('task_domain') or getattr(request, 'routing_policy', None) or 'general').strip().lower() or 'general'


def performance_adjustment(profile) -> float:
    """Return a confidence-bounded routing adjustment in [-.05, .05].

    Learned routing is intentionally advisory. The performance tracker caps its
    own influence and this function applies a second hard cap, so learned data
    can re-rank close eligible candidates but cannot overwhelm canonical model
    policy scores.
    """

    if profile is None:
        return 0.0
    quality = max(0.0, min(1.0, float(profile.quality_score)))
    success = max(0.0, min(1.0, float(profile.success_rate)))
    acceptance = profile.acceptance_rate
    acceptance = quality if acceptance is None else max(0.0, min(1.0, float(acceptance)))
    signal = ((quality * .5) + (success * .3) + (acceptance * .2) - .5) * 2.0
    confidence = max(0.0, min(.5, float(profile.learning_influence)))
    return max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, signal * confidence * .1))


def attach_performance_routing(router, tracker, *, enabled: Callable[[], bool] | None = None) -> None:
    """Attach bounded learned ranking to the canonical governed router.

    This wraps only ``_rank_request`` after the canonical router has already
    applied capabilities, owner provider allow/deny policy and health gates.
    Therefore observations can never make an ineligible provider eligible.
    Calling this function more than once is idempotent.
    """

    if getattr(router, '_performance_routing_attached', False):
        router._performance_tracker = tracker
        router._performance_learning_enabled = enabled
        return

    original = router._rank_request
    router._performance_tracker = tracker
    router._performance_learning_enabled = enabled

    def ranked_with_learning(self, request):
        policy, ranked = original(request)
        predicate = getattr(self, '_performance_learning_enabled', None)
        if callable(predicate):
            try:
                if not bool(predicate()):
                    return policy, ranked
            except Exception:
                return policy, ranked
        tracker_value = getattr(self, '_performance_tracker', None)
        if tracker_value is None or not ranked:
            return policy, ranked
        domain = _task_domain(request)
        adjusted: list[RoutingCandidate] = []
        for row in ranked:
            try:
                profile = tracker_value.profile(domain, row.provider_id, row.model_id)
                delta = performance_adjustment(profile)
            except Exception:
                delta = 0.0
            reasons = row.reasons
            if delta:
                reasons = tuple((*reasons, 'bounded_performance_learning'))
            adjusted.append(RoutingCandidate(
                row.provider_id,
                row.model_id,
                round(float(row.score) + delta, 6),
                reasons,
            ))
        adjusted.sort(key=lambda item: (-item.score, item.provider_id, item.model_id))
        return policy, tuple(adjusted)

    router._rank_request = MethodType(ranked_with_learning, router)
    router._performance_routing_attached = True
