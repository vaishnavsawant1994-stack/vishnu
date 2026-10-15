from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping

from .memory import LabMemory
from .models import new_id


@dataclass(frozen=True)
class OptimizationEpisode:
    task_class: str
    depth: str
    model_count: int
    cache_enabled: bool
    parallelism: int
    latency_ms: float
    cost: float
    quality: float
    successful: bool
    id: str = field(default_factory=lambda: new_id("opt"))


class AdaptivePerformanceOptimizer:
    """Learns configuration preferences without mutating Core or security."""

    def __init__(self, memory: LabMemory, *, window: int = 500):
        self.memory = memory
        self.window = max(50, min(int(window), 5000))

    def record(
        self,
        *,
        task_class: str,
        depth: str,
        model_count: int,
        cache_enabled: bool,
        parallelism: int,
        latency_ms: float,
        cost: float,
        quality: float,
        successful: bool,
    ) -> OptimizationEpisode:
        episode = OptimizationEpisode(
            task_class=str(task_class or "general")[:200],
            depth=str(depth or "smart")[:40],
            model_count=max(1, min(int(model_count), 16)),
            cache_enabled=bool(cache_enabled),
            parallelism=max(1, min(int(parallelism), 32)),
            latency_ms=max(0.0, float(latency_ms)),
            cost=max(0.0, float(cost)),
            quality=max(0.0, min(float(quality), 1.0)),
            successful=bool(successful),
        )
        self.memory.put(episode.id, "optimization_episode", episode.__dict__)
        return episode

    @staticmethod
    def _configuration(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            str(item.get("depth") or "smart"),
            int(item.get("model_count") or 1),
            bool(item.get("cache_enabled", True)),
            int(item.get("parallelism") or 1),
        )

    def recommend(
        self,
        *,
        task_class: str = "general",
        minimum_quality: float = 0.8,
        maximum_cost: float | None = None,
    ) -> dict[str, Any]:
        rows = self.memory.recent("optimization_episode", self.window)
        grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
        for row in rows:
            item = row.get("payload", {})
            if str(item.get("task_class")) != str(task_class):
                continue
            grouped.setdefault(self._configuration(item), []).append(item)
        ranked = []
        for config, episodes in grouped.items():
            successes = [item for item in episodes if item.get("successful")]
            if not successes:
                continue
            quality = sum(float(item.get("quality", 0.0)) for item in successes) / len(successes)
            latency = sum(float(item.get("latency_ms", 0.0)) for item in successes) / len(successes)
            cost = sum(float(item.get("cost", 0.0)) for item in successes) / len(successes)
            success_rate = len(successes) / len(episodes)
            if quality < minimum_quality:
                continue
            if maximum_cost is not None and cost > maximum_cost:
                continue
            utility = (
                quality * 0.55
                + success_rate * 0.25
                - min(0.15, latency / 60000.0)
                - min(0.15, cost)
            )
            exploration = math.sqrt(1.0 / (len(episodes) + 1.0)) * 0.03
            ranked.append((utility + exploration, config, quality, latency, cost, success_rate, len(episodes)))
        ranked.sort(key=lambda item: -item[0])
        if not ranked:
            return {
                "task_class": task_class,
                "configuration": {
                    "depth": "smart",
                    "model_count": 2,
                    "cache_enabled": True,
                    "parallelism": 4,
                },
                "evidence_count": 0,
                "adaptive": False,
                "core_configuration_mutated": False,
            }
        best = ranked[0]
        depth, model_count, cache_enabled, parallelism = best[1]
        return {
            "task_class": task_class,
            "configuration": {
                "depth": depth,
                "model_count": model_count,
                "cache_enabled": cache_enabled,
                "parallelism": parallelism,
            },
            "mean_quality": best[2],
            "mean_latency_ms": best[3],
            "mean_cost": best[4],
            "success_rate": best[5],
            "evidence_count": best[6],
            "adaptive": True,
            "core_configuration_mutated": False,
        }
