from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from .bootstrap import build_intelligence_lab
from .config import LabSettings
from .phase2_service import create_phase2_app
from .runtime import IntelligenceLabRuntime


class Phase3ReasonRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=12000)
    context: dict[str, Any] = Field(default_factory=dict)
    domain: str = Field(default="general", max_length=200)
    sensitivity: str = Field(default="internal", max_length=40)
    scope: str = Field(default="shared", max_length=200)
    requested_depth: str | None = Field(default=None, max_length=20)


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    kind: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=200)


class CompressionRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    chunks: list[Any] = Field(default_factory=list, max_length=256)


class ComputePlacementRequest(BaseModel):
    sensitivity: str = Field(default="internal", max_length=40)
    local_device: dict[str, Any] | None = None


class AccelerationRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PerformanceGateRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=200)
    p95_latency_ms: float | None = Field(default=None, ge=0)
    p99_latency_ms: float | None = Field(default=None, ge=0)
    minimum_success_rate: float = Field(default=0.98, ge=0, le=1)
    minimum_quality: float | None = Field(default=None, ge=0, le=1)
    maximum_mean_cost: float | None = Field(default=None, ge=0)
    minimum_cache_hit_rate: float | None = Field(default=None, ge=0, le=1)


class WorldReliabilityRequest(BaseModel):
    source: str = Field(min_length=1, max_length=500)
    reliability: float = Field(ge=0, le=1)


class OptimizationRequest(BaseModel):
    task_class: str = Field(default="general", max_length=200)
    minimum_quality: float = Field(default=0.8, ge=0, le=1)
    maximum_cost: float | None = Field(default=None, ge=0)


def create_phase3_app(runtime: IntelligenceLabRuntime | None = None):
    app = create_phase2_app(runtime)
    lab: IntelligenceLabRuntime = app.state.lab
    phase3 = lab.phase3
    app.title = "Vishnu Intelligence Lab Phase 3"
    app.version = "3.0"

    @app.get("/phase3/status")
    def phase3_status():
        return phase3.status()

    @app.post("/phase3/reason")
    def phase3_reason(request: Phase3ReasonRequest):
        return phase3.reason(
            request.goal,
            context=request.context,
            domain=request.domain,
            sensitivity=request.sensitivity,
            scope=request.scope,
            requested_depth=request.requested_depth,
        ).public_dict()

    @app.post("/phase3/retrieval/search")
    def phase3_retrieval(request: RetrievalRequest):
        return [
            item.__dict__
            for item in phase3.retrieve(
                request.query,
                kind=request.kind,
                limit=request.limit,
            )
        ]

    @app.post("/phase3/context/compress")
    def phase3_compress(request: CompressionRequest):
        return phase3.compress_context(request.query, request.chunks)

    @app.post("/phase3/compute/place")
    def phase3_compute_place(request: ComputePlacementRequest):
        return phase3.compute_placement(
            sensitivity=request.sensitivity,
            local_device=request.local_device,
        )

    @app.post("/phase3/compute/acceleration")
    def phase3_acceleration(request: AccelerationRequest):
        return phase3.inference_acceleration_plan(
            platform=request.platform,
            metadata=request.metadata,
        )

    @app.get("/phase3/performance")
    def phase3_performance():
        return phase3.performance_summary()

    @app.post("/phase3/performance/gate")
    def phase3_performance_gate(request: PerformanceGateRequest):
        return phase3.performance_gate(
            request.operation,
            p95_latency_ms=request.p95_latency_ms,
            p99_latency_ms=request.p99_latency_ms,
            minimum_success_rate=request.minimum_success_rate,
            minimum_quality=request.minimum_quality,
            maximum_mean_cost=request.maximum_mean_cost,
            minimum_cache_hit_rate=request.minimum_cache_hit_rate,
        )

    @app.post("/phase3/world/source-reliability")
    def phase3_world_source_reliability(request: WorldReliabilityRequest):
        phase3.set_world_source_reliability(request.source, request.reliability)
        return {"updated": True, "source": request.source}

    @app.get("/phase3/world/predict/{effect}")
    def phase3_world_predict(effect: str):
        return phase3.indexed_world_prediction(effect)

    @app.post("/phase3/optimizer/recommend")
    def phase3_optimizer(request: OptimizationRequest):
        return phase3.recommend_optimization(
            task_class=request.task_class,
            minimum_quality=request.minimum_quality,
            maximum_cost=request.maximum_cost,
        )

    return app


def main() -> None:
    settings = LabSettings.from_environment()
    if not settings.enabled:
        raise SystemExit("Vishnu Intelligence Lab is disabled")
    import uvicorn

    host = os.getenv("VISHNU_INTELLIGENCE_LAB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in {"127.0.0.1", "localhost", "::1"} and os.getenv(
        "VISHNU_INTELLIGENCE_LAB_ALLOW_REMOTE", ""
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("remote Intelligence Lab binding requires explicit opt-in")
    port = int(os.getenv("VISHNU_INTELLIGENCE_LAB_PORT", "8777"))
    uvicorn.run(
        create_phase3_app(build_intelligence_lab(settings=settings)),
        host=host,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
