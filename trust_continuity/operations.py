from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .store import TrustContinuityStore, utcnow


@dataclass(frozen=True)
class ProbeResult:
    name: str
    healthy: bool
    latency_ms: float | None
    detail: str


class OperationalHealthMonitor:
    """Bounded health/metrics/crash markers for production readiness.

    It observes existing services and records metadata only. It does not restart,
    deploy, or mutate a protected authority on its own.
    """

    def __init__(self, store: TrustContinuityStore):
        self.store = store
        self._probes: dict[str, Callable[[], Any]] = {}

    def register_probe(self, name: str, probe: Callable[[], Any]) -> None:
        if not name or len(name) > 120:
            raise ValueError("probe name is invalid")
        self._probes[name] = probe

    def run_probe(self, name: str) -> ProbeResult:
        import time

        probe = self._probes.get(name)
        if probe is None:
            raise KeyError(name)
        started = time.perf_counter()
        detail = "ok"
        healthy = True
        try:
            result = probe()
            if isinstance(result, dict):
                healthy = bool(result.get("healthy", result.get("ok", True)))
                detail = str(result.get("detail") or result.get("status") or "ok")[:1000]
            elif isinstance(result, bool):
                healthy = result
                detail = "ok" if result else "failed"
            elif result is not None:
                detail = str(result)[:1000]
        except Exception as exc:
            healthy = False
            detail = type(exc).__name__
        latency = round((time.perf_counter() - started) * 1000, 3)
        payload = {
            "name": name,
            "healthy": healthy,
            "latency_ms": latency,
            "detail": detail,
            "checked_at": utcnow(),
        }
        self.store.put(
            "health_probe",
            name,
            payload,
            status="healthy" if healthy else "unhealthy",
        )
        self.store.audit(
            "operations",
            "health_probe",
            subject=name,
            payload={"healthy": healthy, "latency_ms": latency},
        )
        return ProbeResult(name, healthy, latency, detail)

    def run_all(self) -> dict[str, Any]:
        results = [self.run_probe(name) for name in sorted(self._probes)]
        healthy = bool(results) and all(result.healthy for result in results)
        return {
            "healthy": healthy,
            "probes": [result.__dict__ for result in results],
            "checked_at": utcnow(),
        }

    def record_metric(
        self,
        name: str,
        value: float,
        *,
        unit: str,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        safe_labels = {
            str(key)[:80]: str(label)[:160]
            for key, label in (labels or {}).items()
        }
        payload = {
            "name": name[:120],
            "value": float(value),
            "unit": unit[:40],
            "labels": safe_labels,
            "recorded_at": utcnow(),
        }
        return self.store.put("ops_metric", name[:120], payload)

    def mark_process_start(self, process_id: str, *, clean_previous_shutdown: bool) -> None:
        self.store.put(
            "process_state",
            process_id,
            {
                "process_id": process_id,
                "started_at": utcnow(),
                "clean_previous_shutdown": bool(clean_previous_shutdown),
                "running": True,
            },
            status="running",
        )
        if not clean_previous_shutdown:
            self.store.audit(
                "operations",
                "crash_detected",
                subject=process_id,
                payload={"recovery_required": True},
            )

    def mark_checkpoint(
        self,
        process_id: str,
        *,
        checkpoint: dict[str, Any],
    ) -> None:
        row = self.store.get("process_state", process_id)
        if row is None:
            raise KeyError(process_id)
        payload = dict(row["payload"])
        payload["checkpoint"] = dict(checkpoint)
        payload["checkpointed_at"] = utcnow()
        self.store.put("process_state", process_id, payload, status=row["status"])

    def mark_shutdown(self, process_id: str) -> None:
        row = self.store.get("process_state", process_id)
        if row is None:
            raise KeyError(process_id)
        payload = dict(row["payload"])
        payload.update({"running": False, "clean_shutdown_at": utcnow()})
        self.store.put("process_state", process_id, payload, status="stopped")
        self.store.audit("operations", "clean_shutdown", subject=process_id)

    def recovery_state(self, process_id: str) -> dict[str, Any]:
        row = self.store.get("process_state", process_id)
        if row is None:
            raise KeyError(process_id)
        payload = row["payload"]
        return {
            "process_id": process_id,
            "requires_recovery": not bool(payload.get("clean_previous_shutdown", True)),
            "checkpoint": payload.get("checkpoint"),
            "running": bool(payload.get("running")),
        }
