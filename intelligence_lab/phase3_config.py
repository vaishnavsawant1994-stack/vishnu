from __future__ import annotations

from dataclasses import dataclass
import math
import os


class Phase3ConfigurationError(ValueError):
    pass


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise Phase3ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise Phase3ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _number(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise Phase3ConfigurationError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise Phase3ConfigurationError(
            f"{name} must be finite and between {minimum} and {maximum}"
        )
    return value


@dataclass(frozen=True)
class Phase3Settings:
    telemetry_window: int = 1000
    cache_entries: int = 512
    cache_ttl_seconds: float = 900.0
    semantic_cache_threshold: float = 0.92
    retrieval_index_limit: int = 5000
    retrieval_hot_limit: int = 256
    context_max_chars: int = 16000
    context_max_chunks: int = 32
    dag_max_workers: int = 4
    fast_confidence: float = 0.72
    smart_confidence: float = 0.82
    optimization_window: int = 500

    @classmethod
    def from_environment(cls) -> "Phase3Settings":
        prefix = "VISHNU_INTELLIGENCE_LAB_PHASE3_"
        return cls(
            telemetry_window=_integer(prefix + "TELEMETRY_WINDOW", 1000, 50, 10000),
            cache_entries=_integer(prefix + "CACHE_ENTRIES", 512, 16, 10000),
            cache_ttl_seconds=_number(prefix + "CACHE_TTL_SECONDS", 900.0, 1.0, 86400.0),
            semantic_cache_threshold=_number(
                prefix + "SEMANTIC_CACHE_THRESHOLD", 0.92, 0.5, 1.0
            ),
            retrieval_index_limit=_integer(
                prefix + "RETRIEVAL_INDEX_LIMIT", 5000, 100, 50000
            ),
            retrieval_hot_limit=_integer(
                prefix + "RETRIEVAL_HOT_LIMIT", 256, 32, 4096
            ),
            context_max_chars=_integer(
                prefix + "CONTEXT_MAX_CHARS", 16000, 1000, 200000
            ),
            context_max_chunks=_integer(
                prefix + "CONTEXT_MAX_CHUNKS", 32, 1, 256
            ),
            dag_max_workers=_integer(prefix + "DAG_MAX_WORKERS", 4, 1, 32),
            fast_confidence=_number(prefix + "FAST_CONFIDENCE", 0.72, 0.5, 0.95),
            smart_confidence=_number(prefix + "SMART_CONFIDENCE", 0.82, 0.5, 0.98),
            optimization_window=_integer(
                prefix + "OPTIMIZATION_WINDOW", 500, 50, 5000
            ),
        )

    def public_snapshot(self) -> dict[str, object]:
        return {
            "telemetry_window": self.telemetry_window,
            "cache_entries": self.cache_entries,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "semantic_cache_threshold": self.semantic_cache_threshold,
            "retrieval_index_limit": self.retrieval_index_limit,
            "retrieval_hot_limit": self.retrieval_hot_limit,
            "context_max_chars": self.context_max_chars,
            "context_max_chunks": self.context_max_chunks,
            "dag_max_workers": self.dag_max_workers,
            "fast_confidence": self.fast_confidence,
            "smart_confidence": self.smart_confidence,
            "optimization_window": self.optimization_window,
        }
