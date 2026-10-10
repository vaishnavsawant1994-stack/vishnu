from __future__ import annotations

from types import MethodType
from typing import Callable

from models.contracts import RoutingCandidate


MAX_SCORE_ADJUSTMENT = 0.05


def _task_context(request) -> tuple[str, str, str]:
    metadata = request.metadata if isinstance(getattr(request, 'metadata', None), dict) else {}
    domain = str(metadata.get('task_domain') or getattr(request, 'routing_policy', None) or 'general').strip().lower() or 'general'
    complexity = str(metadata.get('task_complexity') or metadata.get('complexity') or 'medium').strip().lower() or 'medium'
    role = str(metadata.get('specialist_role') or metadata.get('role') or 'general').strip().lower() or 'general'
    return domain, complexity, role


def performance_adjustment(profile) -> float:
    """Return a confidence/recency-bounded routing adjustment in [-.05, .05].

    Learned routing is intentionally advisory. The performance tracker caps its
    own influence and this function applies a second hard cap, so learned data
    can re-rank close eligible candidates but cannot overwhelm canonical model
    policy, privacy, cost, health or permission gates.
    """

    if profile is None:
        return 0.0
    quality = max(0.0, min(1.0, float(profile.quality_score)))
    success = max(0.0, min(1.0, float(profile.success_rate)))
    acceptance = getattr(profile, 'acceptance_rate', None)
    acceptance = quality if acceptance is None else max(0.0, min(1.0, float(acceptance)))
    tool = getattr(profile, 'tool_agreement', None)
    tool = quality if tool is None else max(0.0, min(1.0, float(tool)))
    feedback = getattr(profile, 'feedback_score', None)
    feedback = quality if feedback is None else max(0.0, min(1.0, float(feedback)))
    fallback_rate = max(0.0, min(1.0, float(getattr(profile, 'fallback_rate', 0.0) or 0.0)))
    latency_ms = max(0.0, float(getattr(profile, 'latency_ms', 0.0) or 0.0))
    estimated_cost = max(0.0, float(getattr(profile, 'estimated_cost', 0.0) or 0.0))

    positive = (quality * .38) + (success * .22) + (acceptance * .14) + (tool * .14) + (feedback * .12)
    operational_penalty = (fallback_rate * .15) + min(.08, latency_ms / 120000.0) + min(.08, estimated_cost / 100.0)
    signal = max(-1.0, min(1.0, ((positive - .5) * 2.0) - operational_penalty))
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
        domain, complexity, role = _task_context(request)
        adjusted: list[RoutingCandidate] = []
        for row in ranked:
            try:
                try:
                    profile = tracker_value.profile(
                        domain,
                        row.provider_id,
                        row.model_id,
                        task_complexity=complexity,
                        specialist_role=role,
                    )
                except TypeError:
                    # Compatibility with minimal/legacy tracker implementations.
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
