from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import sqlite3
from threading import RLock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized(value: str | None, fallback: str) -> str:
    return str(value or '').strip().lower() or fallback


@dataclass(frozen=True)
class PerformanceObservation:
    task_domain: str
    provider_id: str
    model_id: str
    success: bool
    task_complexity: str = 'medium'
    specialist_role: str = 'general'
    verifier_score: float | None = None
    tool_agreement: float | None = None
    explicit_feedback: float | None = None
    latency_ms: float | None = None
    estimated_cost: float = 0.0
    accepted: bool | None = None
    corrected: bool = False
    regenerated: bool = False
    fallback: bool = False
    observed_at: str | None = None

    def __post_init__(self) -> None:
        for field, value in (
            ('verifier_score', self.verifier_score),
            ('tool_agreement', self.tool_agreement),
            ('explicit_feedback', self.explicit_feedback),
        ):
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError(f'{field} must be between 0 and 1')
        if self.latency_ms is not None and float(self.latency_ms) < 0:
            raise ValueError('latency_ms cannot be negative')
        if float(self.estimated_cost) < 0:
            raise ValueError('estimated_cost cannot be negative')


@dataclass(frozen=True)
class PerformanceProfile:
    task_domain: str
    task_complexity: str
    specialist_role: str
    provider_id: str
    model_id: str
    samples: int
    success_rate: float
    quality_score: float
    acceptance_rate: float | None
    tool_agreement: float | None
    feedback_score: float | None
    fallback_rate: float
    latency_ms: float | None
    estimated_cost: float
    sample_confidence: float
    recency_weight: float
    learning_influence: float
    last_observed_at: str | None

    def public(self) -> dict:
        return {
            'task_domain': self.task_domain,
            'task_complexity': self.task_complexity,
            'specialist_role': self.specialist_role,
            'provider_id': self.provider_id,
            'model_id': self.model_id,
            'samples': self.samples,
            'success_rate': self.success_rate,
            'quality_score': self.quality_score,
            'acceptance_rate': self.acceptance_rate,
            'tool_agreement': self.tool_agreement,
            'feedback_score': self.feedback_score,
            'fallback_rate': self.fallback_rate,
            'latency_ms': self.latency_ms,
            'estimated_cost': self.estimated_cost,
            'sample_confidence': self.sample_confidence,
            'recency_weight': self.recency_weight,
            'learning_influence': self.learning_influence,
            'last_observed_at': self.last_observed_at,
            'routing_authority': False,
        }


@dataclass
class _Aggregate:
    samples: int = 0
    successes: int = 0
    quality_ema: float = 0.5
    acceptance_samples: int = 0
    acceptances: int = 0
    tool_agreement_ema: float | None = None
    feedback_ema: float | None = None
    feedback_samples: int = 0
    fallback_count: int = 0
    latency_ema: float | None = None
    cost_ema: float = 0.0
    last_observed_at: str | None = None


class ModelPerformanceTracker:
    """Bounded task-specific model learning with no security authority.

    Observations are segmented by task domain, complexity and specialist role.
    Confidence grows gradually with sample count and decays with age. Learned
    scores can advise routing only; this tracker has no provider eligibility,
    credential, privacy, permission, approval or policy mutation capability.
    """

    def __init__(
        self,
        *,
        alpha: float = 0.3,
        max_influence: float = 0.5,
        full_weight_samples: int = 20,
        recency_half_life_days: float = 30.0,
        path: str | Path | None = None,
    ):
        if not 0.0 < float(alpha) <= 1.0:
            raise ValueError('alpha must be between 0 and 1')
        if not 0.0 <= float(max_influence) <= 1.0:
            raise ValueError('max_influence must be between 0 and 1')
        if int(full_weight_samples) < 1:
            raise ValueError('full_weight_samples must be positive')
        if float(recency_half_life_days) <= 0:
            raise ValueError('recency_half_life_days must be positive')
        self.alpha = float(alpha)
        self.max_influence = float(max_influence)
        self.full_weight_samples = int(full_weight_samples)
        self.recency_half_life_days = float(recency_half_life_days)
        self._aggregates: dict[tuple[str, str, str, str, str], _Aggregate] = {}
        self._lock = RLock()
        self.path = Path(path) if path is not None else None
        self.connection: sqlite3.Connection | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            self._ensure_schema()
            self._load()

    def _ensure_schema(self) -> None:
        if self.connection is None:
            return
        self.connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS model_performance_v2 (
                task_domain TEXT NOT NULL,
                task_complexity TEXT NOT NULL,
                specialist_role TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                samples INTEGER NOT NULL,
                successes INTEGER NOT NULL,
                quality_ema REAL NOT NULL,
                acceptance_samples INTEGER NOT NULL,
                acceptances INTEGER NOT NULL,
                tool_agreement_ema REAL,
                feedback_ema REAL,
                feedback_samples INTEGER NOT NULL,
                fallback_count INTEGER NOT NULL,
                latency_ema REAL,
                cost_ema REAL NOT NULL,
                last_observed_at TEXT,
                PRIMARY KEY(task_domain, task_complexity, specialist_role, provider_id, model_id)
            )
            '''
        )
        # Preserve older persisted observations as weak generic history. The old
        # table remains untouched for rollback compatibility.
        old = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='model_performance'"
        ).fetchone()
        current = self.connection.execute('SELECT COUNT(*) FROM model_performance_v2').fetchone()[0]
        if old is not None and int(current) == 0:
            try:
                rows = self.connection.execute('SELECT * FROM model_performance').fetchall()
                stamp = _now()
                for row in rows:
                    self.connection.execute(
                        '''INSERT OR IGNORE INTO model_performance_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (
                            str(row['task_domain']), 'medium', 'general', str(row['provider_id']), str(row['model_id']),
                            int(row['samples']), int(row['successes']), float(row['quality_ema']),
                            int(row['acceptance_samples']), int(row['acceptances']), None, None, 0, 0,
                            None if row['latency_ema'] is None else float(row['latency_ema']), float(row['cost_ema']), stamp,
                        ),
                    )
            except Exception:
                pass
        self.connection.commit()

    def _load(self) -> None:
        if self.connection is None:
            return
        rows = self.connection.execute('SELECT * FROM model_performance_v2').fetchall()
        for row in rows:
            key = (
                str(row['task_domain']), str(row['task_complexity']), str(row['specialist_role']),
                str(row['provider_id']), str(row['model_id']),
            )
            self._aggregates[key] = _Aggregate(
                samples=int(row['samples']),
                successes=int(row['successes']),
                quality_ema=float(row['quality_ema']),
                acceptance_samples=int(row['acceptance_samples']),
                acceptances=int(row['acceptances']),
                tool_agreement_ema=None if row['tool_agreement_ema'] is None else float(row['tool_agreement_ema']),
                feedback_ema=None if row['feedback_ema'] is None else float(row['feedback_ema']),
                feedback_samples=int(row['feedback_samples']),
                fallback_count=int(row['fallback_count']),
                latency_ema=None if row['latency_ema'] is None else float(row['latency_ema']),
                cost_ema=float(row['cost_ema']),
                last_observed_at=row['last_observed_at'],
            )

    def _persist(self, key: tuple[str, str, str, str, str], aggregate: _Aggregate) -> None:
        if self.connection is None:
            return
        self.connection.execute(
            '''
            INSERT INTO model_performance_v2 (
                task_domain, task_complexity, specialist_role, provider_id, model_id,
                samples, successes, quality_ema, acceptance_samples, acceptances,
                tool_agreement_ema, feedback_ema, feedback_samples, fallback_count,
                latency_ema, cost_ema, last_observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_domain,task_complexity,specialist_role,provider_id,model_id) DO UPDATE SET
                samples=excluded.samples, successes=excluded.successes,
                quality_ema=excluded.quality_ema, acceptance_samples=excluded.acceptance_samples,
                acceptances=excluded.acceptances, tool_agreement_ema=excluded.tool_agreement_ema,
                feedback_ema=excluded.feedback_ema, feedback_samples=excluded.feedback_samples,
                fallback_count=excluded.fallback_count, latency_ema=excluded.latency_ema,
                cost_ema=excluded.cost_ema, last_observed_at=excluded.last_observed_at
            ''',
            (*key, aggregate.samples, aggregate.successes, aggregate.quality_ema,
             aggregate.acceptance_samples, aggregate.acceptances, aggregate.tool_agreement_ema,
             aggregate.feedback_ema, aggregate.feedback_samples, aggregate.fallback_count,
             aggregate.latency_ema, aggregate.cost_ema, aggregate.last_observed_at),
        )
        self.connection.commit()

    @staticmethod
    def _key(observation: PerformanceObservation) -> tuple[str, str, str, str, str]:
        return (
            _normalized(observation.task_domain, 'general'),
            _normalized(observation.task_complexity, 'medium'),
            _normalized(observation.specialist_role, 'general'),
            observation.provider_id.strip(),
            observation.model_id.strip(),
        )

    @staticmethod
    def _blend(current: float | None, value: float, alpha: float) -> float:
        return float(value) if current is None else (alpha * float(value)) + ((1.0 - alpha) * current)

    @staticmethod
    def _quality_signal(observation: PerformanceObservation) -> float:
        if not observation.success:
            return 0.0
        score = 0.80 if observation.verifier_score is None else float(observation.verifier_score)
        if observation.tool_agreement is not None:
            score = (score * .75) + (float(observation.tool_agreement) * .25)
        if observation.explicit_feedback is not None:
            score = (score * .80) + (float(observation.explicit_feedback) * .20)
        if observation.corrected:
            score *= 0.80
        if observation.regenerated:
            score *= 0.85
        if observation.fallback:
            score *= 0.90
        if observation.accepted is False:
            score *= 0.65
        elif observation.accepted is True:
            score = min(1.0, score * 1.03)
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
            if observation.tool_agreement is not None:
                aggregate.tool_agreement_ema = self._blend(aggregate.tool_agreement_ema, float(observation.tool_agreement), self.alpha)
            if observation.explicit_feedback is not None:
                aggregate.feedback_samples += 1
                aggregate.feedback_ema = self._blend(aggregate.feedback_ema, float(observation.explicit_feedback), self.alpha)
            if observation.fallback:
                aggregate.fallback_count += 1
            if observation.latency_ms is not None:
                aggregate.latency_ema = self._blend(aggregate.latency_ema, float(observation.latency_ms), self.alpha)
            aggregate.last_observed_at = str(observation.observed_at or _now())

            self._persist(key, aggregate)
            return self._profile(key, aggregate)

    def profile(
        self,
        task_domain: str,
        provider_id: str,
        model_id: str,
        *,
        task_complexity: str = 'medium',
        specialist_role: str = 'general',
    ) -> PerformanceProfile | None:
        key = (
            _normalized(task_domain, 'general'), _normalized(task_complexity, 'medium'),
            _normalized(specialist_role, 'general'), provider_id.strip(), model_id.strip(),
        )
        with self._lock:
            aggregate = self._aggregates.get(key)
            if aggregate is None and key[2] != 'general':
                fallback_key = (key[0], key[1], 'general', key[3], key[4])
                aggregate = self._aggregates.get(fallback_key)
                key = fallback_key if aggregate is not None else key
            return None if aggregate is None else self._profile(key, aggregate)

    def profiles(self) -> tuple[PerformanceProfile, ...]:
        with self._lock:
            return tuple(self._profile(key, aggregate) for key, aggregate in sorted(self._aggregates.items()))

    def task_summary(self, task_domain: str, *, task_complexity: str = 'medium', specialist_role: str = 'general') -> dict:
        domain = _normalized(task_domain, 'general')
        complexity = _normalized(task_complexity, 'medium')
        role = _normalized(specialist_role, 'general')
        rows = [
            row for row in self.profiles()
            if row.task_domain == domain and row.task_complexity == complexity and row.specialist_role in {role, 'general'}
        ]
        if not rows:
            return {'samples': 0, 'quality_score': None, 'confidence': 0.0, 'fallback_rate': None}
        weights = [max(.001, row.learning_influence) for row in rows]
        total = sum(weights)
        return {
            'samples': sum(row.samples for row in rows),
            'quality_score': sum(row.quality_score * weight for row, weight in zip(rows, weights)) / total,
            'confidence': min(1.0, sum(row.sample_confidence * weight for row, weight in zip(rows, weights)) / total),
            'fallback_rate': sum(row.fallback_rate * weight for row, weight in zip(rows, weights)) / total,
        }

    def _recency_weight(self, stamp: str | None) -> float:
        if not stamp:
            return 0.5
        try:
            then = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (datetime.now(timezone.utc) - then.astimezone(timezone.utc)).total_seconds() / 86400.0)
            return max(0.05, min(1.0, math.pow(0.5, age_days / self.recency_half_life_days)))
        except Exception:
            return 0.5

    def _profile(self, key: tuple[str, str, str, str, str], aggregate: _Aggregate) -> PerformanceProfile:
        task_domain, task_complexity, specialist_role, provider_id, model_id = key
        acceptance_rate = None
        if aggregate.acceptance_samples:
            acceptance_rate = aggregate.acceptances / aggregate.acceptance_samples
        sample_confidence = min(1.0, aggregate.samples / self.full_weight_samples)
        recency = self._recency_weight(aggregate.last_observed_at)
        influence = self.max_influence * sample_confidence * recency
        return PerformanceProfile(
            task_domain=task_domain,
            task_complexity=task_complexity,
            specialist_role=specialist_role,
            provider_id=provider_id,
            model_id=model_id,
            samples=aggregate.samples,
            success_rate=aggregate.successes / max(1, aggregate.samples),
            quality_score=max(0.0, min(1.0, aggregate.quality_ema)),
            acceptance_rate=acceptance_rate,
            tool_agreement=aggregate.tool_agreement_ema,
            feedback_score=aggregate.feedback_ema,
            fallback_rate=aggregate.fallback_count / max(1, aggregate.samples),
            latency_ms=aggregate.latency_ema,
            estimated_cost=max(0.0, aggregate.cost_ema),
            sample_confidence=sample_confidence,
            recency_weight=recency,
            learning_influence=influence,
            last_observed_at=aggregate.last_observed_at,
        )

    def close(self) -> None:
        with self._lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
