from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .bootstrap import build_intelligence_lab
from .config import LabSettings
from .runtime import IntelligenceLabRuntime


class ThinkRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)


class AffectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    signals: dict[str, Any] = Field(default_factory=dict)


class ProposalRequest(BaseModel):
    action: str = Field(min_length=1, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=8000)
    risk: str = Field(default="unknown", max_length=100)


class ResearchCycleRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    proposed_action: str | None = Field(default=None, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=8000)
    risk: str = Field(default="unknown", max_length=100)


class EvaluationRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=500)
    scores: dict[str, float]
    evidence: list[str] = Field(default_factory=list, max_length=100)


def create_app(runtime: IntelligenceLabRuntime | None = None) -> FastAPI:
    lab = runtime or build_intelligence_lab()
    app = FastAPI(
        title="Vishnu Intelligence Lab",
        version="1.0",
        description=(
            "Opt-in experimental cognition backend. It has no standalone execution endpoint; "
            "real actions require an in-process bridge back through Vishnu Core governance."
        ),
    )
    app.state.lab = lab

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "enabled": lab.settings.enabled,
            "level": lab.settings.level.name,
            "core_attached": lab.bridge.attached,
            "execution_surface_exposed": False,
        }

    @app.get("/status")
    def status():
        return lab.status()

    @app.post("/think")
    def think(request: ThinkRequest):
        return _guard(lambda: lab.think(request.goal, context=request.context).public_dict())

    @app.post("/deliberate")
    def deliberate(request: ThinkRequest):
        return _guard(lambda: lab.deliberate(request.goal, context=request.context))

    @app.post("/affect")
    def affect(request: AffectRequest):
        return _guard(lambda: lab.estimate_affect(request.text, signals=request.signals).public_dict())

    @app.post("/propose")
    def propose(request: ProposalRequest):
        return _guard(
            lambda: lab.propose(
                request.action,
                request.parameters,
                request.rationale,
                risk=request.risk,
            ).public_dict()
        )

    @app.post("/research-cycle")
    def research_cycle(request: ResearchCycleRequest):
        return _guard(
            lambda: lab.research_cycle(
                request.goal,
                proposed_action=request.proposed_action,
                parameters=request.parameters,
                rationale=request.rationale,
                risk=request.risk,
            )
        )

    @app.post("/evaluate")
    def evaluate(request: EvaluationRequest):
        return _guard(
            lambda: lab.evaluate_candidate(
                request.subject_id,
                request.scores,
                evidence=request.evidence,
            ).public_dict()
        )

    @app.get("/memory/audit")
    def audit(limit: int = 100):
        return _guard(lambda: {"items": lab.memory.audit_log(limit)})

    @app.get("/memory/skills")
    def skills():
        return _guard(lambda: {"items": lab.memory.skills()})

    # There is intentionally no /execute, /approval, /vault, /tool-dispatch,
    # /trusted-memory-write, or /security-policy-write route.
    return app


def _guard(callback):
    try:
        return callback()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> None:
    settings = LabSettings.from_environment()
    if not settings.enabled:
        raise SystemExit(
            "Vishnu Intelligence Lab is disabled. Set VISHNU_INTELLIGENCE_LAB_ENABLED=true explicitly."
        )
    import uvicorn

    host = os.getenv("VISHNU_INTELLIGENCE_LAB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in {"127.0.0.1", "localhost", "::1"} and os.getenv(
        "VISHNU_INTELLIGENCE_LAB_ALLOW_REMOTE", ""
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("remote Intelligence Lab binding requires VISHNU_INTELLIGENCE_LAB_ALLOW_REMOTE=true")
    port = int(os.getenv("VISHNU_INTELLIGENCE_LAB_PORT", "8776"))
    uvicorn.run(create_app(build_intelligence_lab(settings=settings)), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
