from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from .bootstrap import build_intelligence_lab
from .config import LabSettings
from .runtime import IntelligenceLabRuntime
from .service import create_app


class AdaptiveThinkRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)
    domain: str = Field(default="general", max_length=200)


class ModelTeamRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="synthesize", max_length=40)
    sensitivity: str = Field(default="internal", max_length=40)
    max_tokens: int | None = Field(default=None, ge=1, le=200000)
    max_cost: float | None = Field(default=None, ge=0)


class HumanContextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    derived_signals: dict[str, Any] = Field(default_factory=dict)
    consent: dict[str, bool] = Field(default_factory=dict)


class WorldFactRequest(BaseModel):
    key: str = Field(min_length=1, max_length=500)
    value: Any
    confidence: float = Field(ge=0, le=1)
    source: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=100)


class WorldRelationRequest(BaseModel):
    cause: str = Field(min_length=1, max_length=500)
    effect: str = Field(min_length=1, max_length=500)
    strength: float = Field(ge=0, le=1)
    evidence: list[str] = Field(min_length=1, max_length=100)
    relation: str = Field(default="influences", max_length=120)


class LongPlanRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    success_criteria: list[str] = Field(default_factory=list, max_length=100)


class BenchmarkRequest(BaseModel):
    variants: int | None = Field(default=None, ge=1, le=20)
    seed: int = 7


class ReflectionRequest(BaseModel):
    domain: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=500)


class SkillRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    allowed_actions: list[str] = Field(min_length=1, max_length=100)
    examples: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


def create_phase2_app(runtime: IntelligenceLabRuntime | None = None):
    app = create_app(runtime)
    lab: IntelligenceLabRuntime = app.state.lab
    app.title = "Vishnu Intelligence Lab Phase 2"
    app.version = "2.0"

    @app.post("/phase2/think/adaptive")
    def adaptive_think(request: AdaptiveThinkRequest):
        return lab.adaptive_think(request.goal, context=request.context, domain=request.domain).public_dict()

    @app.post("/phase2/model-team")
    def model_team(request: ModelTeamRequest):
        return lab.deliberate_models(
            request.goal,
            context=request.context,
            mode=request.mode,
            sensitivity=request.sensitivity,
            max_tokens=request.max_tokens,
            max_cost=request.max_cost,
        ).public_dict()

    @app.post("/phase2/human-context")
    def human_context(request: HumanContextRequest):
        return lab.estimate_human_context(
            request.text,
            derived_signals=request.derived_signals,
            consent=request.consent,
        ).public_dict()

    @app.post("/phase2/world/fact")
    def world_fact(request: WorldFactRequest):
        return lab.assert_world_fact(
            request.key,
            request.value,
            confidence=request.confidence,
            source=request.source,
            evidence=request.evidence,
        ).public_dict()

    @app.post("/phase2/world/relation")
    def world_relation(request: WorldRelationRequest):
        return lab.relate_world_facts(
            request.cause,
            request.effect,
            strength=request.strength,
            evidence=request.evidence,
            relation=request.relation,
        ).public_dict()

    @app.get("/phase2/world")
    def world_snapshot():
        return {
            "facts": lab.temporal_world.snapshot(),
            "contradictions": lab.temporal_world.contradictions(),
        }

    @app.post("/phase2/planning/start")
    def planning_start(request: LongPlanRequest):
        return lab.start_long_horizon_plan(
            request.goal,
            success_criteria=request.success_criteria,
        ).public_dict()

    @app.post("/phase2/benchmarks/run")
    def benchmark(request: BenchmarkRequest):
        return lab.run_agi_research_benchmark(variants=request.variants, seed=request.seed)

    @app.post("/phase2/learning/reflect")
    def reflection(request: ReflectionRequest):
        return lab.reflect_learning(domain=request.domain, limit=request.limit)

    @app.post("/phase2/skills/synthesize")
    def skill(request: SkillRequest):
        return lab.synthesize_skill(
            request.goal,
            allowed_actions=request.allowed_actions,
            examples=request.examples,
        ).public_dict()

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
    port = int(os.getenv("VISHNU_INTELLIGENCE_LAB_PORT", "8776"))
    uvicorn.run(create_phase2_app(build_intelligence_lab(settings=settings)), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
