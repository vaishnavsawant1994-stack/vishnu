from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import math
import statistics
import threading
import time
from typing import Any, Iterator, Mapping

from .memory import LabMemory
from .models import new_id


@dataclass(frozen=True)
class PerformanceBudget:
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    minimum_success_rate: float = 0.98
    minimum_quality: float | None = None
    maximum_mean_cost: float | None = None
    minimum_cache_hit_rate: float | None = None


@dataclass(frozen=True)
class PerformanceSample:
    operation: str
    latency_ms: float
    success: bool = True
    quality: float | None = None
    cost: float = 0.0
    tokens: int = 0
    cache_hit: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: new_id("perf"))


class PerformanceTelemetry:
    """Bounded Lab-local performance telemetry with regression gates.

    Prompts, credentials and raw tool payloads are intentionally not accepted.
    Callers should attach only bounded operational labels in metadata.
    """

    def __init__(self, memory: LabMemory, *, window: int = 1000):
        self.memory = memory
        self.window = max(50, min(int(window), 10000))
        self._samples: dict[str, deque[PerformanceSample]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )
        self._lock = threading.RLock()

    @staticmethod
    def _finite(value: float, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    def record(
        self,
        operation: str,
        latency_ms: float,
        *,
        success: bool = True,
        quality: float | None = None,
        cost: float = 0.0,
        tokens: int = 0,
        cache_hit: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PerformanceSample:
        op = str(operation).strip()[:200]
        if not op:
            raise ValueError("operation is required")
        safe_metadata = {
            str(key)[:100]: (
                value
                if isinstance(value, (bool, int, float)) or value is None
                else str(value)[:300]
            )
            for key, value in dict(metadata or {}).items()
        }
        sample = PerformanceSample(
            operation=op,
            latency_ms=max(0.0, self._finite(latency_ms)),
            success=bool(success),
            quality=(
                max(0.0, min(self._finite(quality), 1.0))
                if quality is not None
                else None
            ),
            cost=max(0.0, self._finite(cost)),
            tokens=max(0, int(tokens or 0)),
            cache_hit=cache_hit if cache_hit is None else bool(cache_hit),
            metadata=safe_metadata,
        )
        with self._lock:
            self._samples[op].append(sample)
        return sample

    @contextmanager
    def measure(
        self,
        operation: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        outcome: dict[str, Any] = {
            "success": True,
            "quality": None,
            "cost": 0.0,
            "tokens": 0,
            "cache_hit": None,
        }
        try:
            yield outcome
        except Exception:
            outcome["success"] = False
            raise
        finally:
            self.record(
                operation,
                (time.perf_counter() - started) * 1000.0,
                success=bool(outcome.get("success", True)),
                quality=outcome.get("quality"),
                cost=float(outcome.get("cost", 0.0) or 0.0),
                tokens=int(outcome.get("tokens", 0) or 0),
                cache_hit=outcome.get("cache_hit"),
                metadata=metadata,
            )

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction

    def summary(self, operation: str) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples.get(str(operation), ()))
        latencies = [item.latency_ms for item in samples]
        qualities = [item.quality for item in samples if item.quality is not None]
        cache = [item.cache_hit for item in samples if item.cache_hit is not None]
        elapsed = 0.0
        if len(samples) >= 2:
            elapsed = max(0.0, samples[-1].created_at - samples[0].created_at)
        result = {
            "operation": str(operation),
            "samples": len(samples),
            "p50_latency_ms": self._percentile(latencies, 0.50),
            "p95_latency_ms": self._percentile(latencies, 0.95),
            "p99_latency_ms": self._percentile(latencies, 0.99),
            "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "success_rate": (
                sum(1 for item in samples if item.success) / len(samples)
                if samples
                else 0.0
            ),
            "mean_quality": statistics.fmean(qualities) if qualities else None,
            "mean_cost": (
                statistics.fmean(item.cost for item in samples) if samples else 0.0
            ),
            "mean_tokens": (
                statistics.fmean(item.tokens for item in samples) if samples else 0.0
            ),
            "cache_hit_rate": (
                sum(1 for value in cache if value) / len(cache) if cache else None
            ),
            "throughput_per_second": (
                len(samples) / elapsed if elapsed > 0 else 0.0
            ),
            "raw_prompt_stored": False,
            "credential_stored": False,
        }
        return result

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            operations = tuple(self._samples)
        return {operation: self.summary(operation) for operation in operations}

    def persist_summary(self, operation: str) -> dict[str, Any]:
        result = self.summary(operation)
        record_id = new_id("perfsummary")
        self.memory.put(record_id, "performance_summary", {"id": record_id, **result})
        return {"id": record_id, **result}

    def gate(self, operation: str, budget: PerformanceBudget) -> dict[str, Any]:
        result = self.summary(operation)
        failures: list[str] = []
        if result["samples"] == 0:
            failures.append("no_samples")
        if budget.p95_latency_ms is not None and result["p95_latency_ms"] > budget.p95_latency_ms:
            failures.append("p95_latency")
        if budget.p99_latency_ms is not None and result["p99_latency_ms"] > budget.p99_latency_ms:
            failures.append("p99_latency")
        if result["success_rate"] < budget.minimum_success_rate:
            failures.append("success_rate")
        if (
            budget.minimum_quality is not None
            and (result["mean_quality"] is None or result["mean_quality"] < budget.minimum_quality)
        ):
            failures.append("quality")
        if (
            budget.maximum_mean_cost is not None
            and result["mean_cost"] > budget.maximum_mean_cost
        ):
            failures.append("cost")
        if (
            budget.minimum_cache_hit_rate is not None
            and (
                result["cache_hit_rate"] is None
                or result["cache_hit_rate"] < budget.minimum_cache_hit_rate
            )
        ):
            failures.append("cache_hit_rate")
        outcome = {
            "operation": str(operation),
            "passed": not failures,
            "failures": failures,
            "summary": result,
            "budget": asdict(budget),
        }
        self.memory.audit(
            "performance",
            "regression_gate",
            {"operation": operation, "passed": not failures, "failures": failures},
        )
        return outcome
