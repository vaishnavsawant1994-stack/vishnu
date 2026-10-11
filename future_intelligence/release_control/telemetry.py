from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .providers import ReleaseDeployment


class ProductionTelemetryError(RuntimeError):
    """Read-only provider telemetry could not be collected or trusted."""


@dataclass(frozen=True)
class ProductionTelemetryObservation:
    """Sanitized aggregate production telemetry for one exact deployment.

    Raw provider logs, request paths, messages, headers and credentials are
    intentionally excluded. Evidence persisted by release monitoring contains
    only deployment-bound aggregates and non-secret provider references.
    """

    provider: str
    deployment_id: str
    request_count: int
    server_error_count: int
    window_seconds: int
    p95_latency_ms: float | None = None
    references: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.provider).strip() or not str(self.deployment_id).strip():
            raise ValueError("telemetry provider and deployment id are required")
        if self.request_count < 0 or self.server_error_count < 0:
            raise ValueError("telemetry counts cannot be negative")
        if self.server_error_count > self.request_count:
            raise ValueError("server error count cannot exceed request count")
        if self.window_seconds < 30 or self.window_seconds > 3_600:
            raise ValueError("telemetry window must be between 30 and 3600 seconds")
        if self.p95_latency_ms is not None and self.p95_latency_ms < 0:
            raise ValueError("p95 latency cannot be negative")

    @property
    def error_rate(self) -> float:
        if self.request_count <= 0:
            return 0.0
        return self.server_error_count / self.request_count

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "deployment_id": self.deployment_id,
            "request_count": self.request_count,
            "server_error_count": self.server_error_count,
            "error_rate": self.error_rate,
            "window_seconds": self.window_seconds,
            "p95_latency_ms": self.p95_latency_ms,
            "references": list(self.references),
            "metadata": dict(self.metadata),
            "raw_logs_persisted": False,
        }


class ProductionTelemetryProvider(Protocol):
    """Read-only telemetry authority scoped to an already-recorded deployment."""

    name: str

    def collect_production_telemetry(
        self,
        deployment: ReleaseDeployment,
        *,
        window_seconds: int = 300,
    ) -> ProductionTelemetryObservation: ...
