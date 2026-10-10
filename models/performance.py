from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class PerformanceObservation:
    task_domain: str
    provider_id: str
    model_id: str
    success: bool
    verifier_score: float | None = None
    latency_ms: float | None = None
    estimated_cost: float = 0.0
    accepted: bool | None = None
    corrected: bool = False
    regenerated: bool = False
    fallback: bool = False

    def __post_init__(self) -> None:
        if self.verifier_score is not None and not 0.0 <= float(self.verifier_score) <= 1.0:
            raise ValueError('verifier_score must be between 0 and 1')
        if self.latency_ms is not None and float(self.latency_ms) < 0:
            raise ValueError('latency_ms cannot be negative')
        if float(self.estimated_cost) < 0:
            raise ValueError('estimated_cost cannot be negative')


@dataclass(frozen=True)
class PerformanceProfile:
    task_domain: str
    provider_id: str
    model_id: str
    samples: int
    success_rate: float
    quality_score: float
    acceptance_rate: float | None
    latency_ms: float | None
    estimated_cost: float
    learning_influence: float


@dataclass
class _Aggregate:
    samples: int = 0
    successes: int = 0
    quality_ema: float = 0.5
    acceptance_samples: int = 0
    acceptances: int = 0
    latency_ema: float | None = None
    cost_ema: float = 0.0


class ModelPerformanceTracker:
    """Bounded task-specific model learning with no security authority.

    The tracker intentionally stores only operational outcome measurements. It
    cannot mutate provider credentials, privacy rules, permissions, approvals,
    or execution policy. Low-sample observations have limited routing influence.
    """

    def __init__(self, *, alpha: float = 0.3, max_influence: float = 0.5, full_weight_samples: int = 20):
        if not 0.0 < float(alpha) <= 1.0:
            raise ValueError('alpha must be between 0 and 1')
        if not 0.0 <= float(max_influence) <= 1.0:
            raise ValueError('max_influence must be between 0 and 1')
        if int(full_weight_samples) < 1:
            raise ValueError('full_weight_samples must be positive')
        self.alpha = float(alpha)
        self.max_influence = float(max_influence)
        self.full_weight_samples = int(full_weight_samples)
        self._aggregates: dict[tuple[str, str, str], _Aggregate] = {}
        self._lock = RLock()

    @staticmethod
    def _key(observation: PerformanceObservation) -> tuple[str, str, str]:
        return (
            observation.task_domain.strip().lower() or 'general',
            observation.provider_id.strip(),
            observation.model_id.strip(),
        )

    @staticmethod
    def _quality_signal(observation: PerformanceObservation) -> float:
        if not observation.success:
            return 0.0
        score = 1.0 if observation.verifier_score is None else float(observation.verifier_score)
        if observation.corrected:
            score *= 0.8
        if observation.regenerated:
            score *= 0.85
        if observation.fallback:
            score *= 0.95
        if observation.accepted is False:
            score *= 0.7
        return max(0.0, min(1.0, score))

    def record(self, observation: PerformanceObservation) -> PerformanceProfile:
        key = self._key(observation)
        with self._lock:
            aggregate = self._aggregates.setdefault(key, _Aggregate())
            aggregate.samples += 1
            aggregate.successes += int(bool(observation.success))

            quality = self._quality_signal(observation)
            if aggregate.samples == 1:
                aggregate.quality_ema = quality
                aggregate.cost_ema = float(observation.estimated_cost)
            else:
                aggregate.quality_ema = (self.alpha * quality) + ((1.0 - self.alpha) * aggregate.quality_ema)
                aggregate.cost_ema = (self.alpha * float(observation.estimated_cost)) + ((1.0 - self.alpha) * aggregate.cost_ema)

            if observation.accepted is not None:
                aggregate.acceptance_samples += 1
                aggregate.acceptances += int(bool(observation.accepted))

            if observation.latency_ms is not None:
                latency = float(observation.latency_ms)
                if aggregate.latency_ema is None:
                    aggregate.latency_ema = latency
                else:
                    aggregate.latency_ema = (self.alpha * latency) + ((1.0 - self.alpha) * aggregate.latency_ema)

            return self._profile(key, aggregate)

    def profile(self, task_domain: str, provider_id: str, model_id: str) -> PerformanceProfile | None:
        key = (task_domain.strip().lower() or 'general', provider_id.strip(), model_id.strip())
        with self._lock:
            aggregate = self._aggregates.get(key)
            return None if aggregate is None else self._profile(key, aggregate)

    def profiles(self) -> tuple[PerformanceProfile, ...]:
        with self._lock:
            return tuple(self._profile(key, aggregate) for key, aggregate in sorted(self._aggregates.items()))

    def _profile(self, key: tuple[str, str, str], aggregate: _Aggregate) -> PerformanceProfile:
        task_domain, provider_id, model_id = key
        acceptance_rate = None
        if aggregate.acceptance_samples:
            acceptance_rate = aggregate.acceptances / aggregate.acceptance_samples
        influence = self.max_influence * min(1.0, aggregate.samples / self.full_weight_samples)
        return PerformanceProfile(
            task_domain=task_domain,
            provider_id=provider_id,
            model_id=model_id,
            samples=aggregate.samples,
            success_rate=aggregate.successes / aggregate.samples,
            quality_score=max(0.0, min(1.0, aggregate.quality_ema)),
            acceptance_rate=acceptance_rate,
            latency_ms=aggregate.latency_ema,
            estimated_cost=max(0.0, aggregate.cost_ema),
            learning_influence=influence,
        )
