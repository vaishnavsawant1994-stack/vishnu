from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium.action_feedback import ActionObservationLoop
from sensorium.active_perception import ActivePerceptionPlanner
from sensorium.benchmark import SensoriumBenchmark
from sensorium.causal_world import CausalWorldModel
from sensorium.context_service import SENSOR_SCOPES, SENSITIVE_SENSORS
from sensorium.outcome_simulator import OutcomeSimulator
from sensorium.physical_safety import PhysicalSafetyEngine
from sensorium.procedural_memory import ProceduralMemory
from sensorium.scene_graph import SemanticSceneGraph
from sensorium.task_state import TaskStateTracker
from sensorium.unified_reality import UnifiedRealityModel
from sensorium.world_model import TemporalWorldModel


class ActivePerceptionBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    candidates: list[dict[str, Any]] = Field(min_length=1, max_length=64)
    uncertainty: float = Field(default=0.5, ge=0, le=1)
    urgency: float = Field(default=0.5, ge=0, le=1)
    max_observations: int = Field(default=3, ge=1, le=8)


class SceneEntityBody(BaseModel):
    observed_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="object", max_length=80)
    label: str | None = Field(default=None, max_length=240)
    stable_key: str | None = Field(default=None, max_length=240)


class SceneRelationBody(BaseModel):
    subject_id: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=120)
    object_id: str = Field(min_length=1, max_length=200)
    source_modality: str = Field(min_length=1, max_length=80)
    confidence: float = Field(default=0.7, ge=0, le=1)
    freshness_seconds: float = Field(default=60, gt=0, le=86400)


class CausalHypothesisBody(BaseModel):
    cause: dict[str, Any]
    effect: dict[str, Any]
    description: str = Field(min_length=1, max_length=2000)
    prior: float = Field(default=0.5, gt=0, lt=1)


class CausalEvidenceBody(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=80)
    supports: bool = True
    confidence: float = Field(default=0.7, ge=0, le=1)
    source: str = Field(min_length=1, max_length=200)
    details: dict[str, Any] = Field(default_factory=dict)


class CounterfactualBody(BaseModel):
    intervention: dict[str, Any]
    assume_no_unmodeled_causes: bool = False


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    purpose: str = Field(min_length=1, max_length=2000)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=256)


class TaskStepBody(BaseModel):
    state: str = Field(min_length=1, max_length=40)
    uncertainty: float | None = Field(default=None, ge=0, le=1)
    observed_state: dict[str, Any] | None = None


class TaskHypothesisBody(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    probability: float = Field(ge=0, le=1)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=128)
    status: str = Field(default="open", max_length=40)


class ProcedureLearnBody(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    demonstrations: list[dict[str, Any]] = Field(min_length=1, max_length=32)
    description: str = Field(default="", max_length=4000)
    prerequisites: list[str] = Field(default_factory=list, max_length=128)
    safety_conditions: list[str] = Field(default_factory=list, max_length=128)
    checkpoints: list[str] = Field(default_factory=list, max_length=128)
    source_devices: list[str] = Field(default_factory=list, max_length=64)
    explicit_owner_save: bool = False


class OutcomeModelBody(BaseModel):
    action_type: str = Field(min_length=1, max_length=200)
    preconditions: list[dict[str, Any]] = Field(default_factory=list, max_length=128)
    effects: list[dict[str, Any]] = Field(min_length=1, max_length=128)
    reversible: bool
    hazards: list[str] = Field(default_factory=list, max_length=128)
    confidence: float = Field(default=0.7, ge=0, le=1)


class SimulateBody(BaseModel):
    action_type: str = Field(min_length=1, max_length=200)
    current_state: dict[str, Any]
    parameters: dict[str, Any] = Field(default_factory=dict)


class VerificationStartBody(BaseModel):
    proposed_action_id: str = Field(min_length=1, max_length=240)
    approval_reference: str = Field(min_length=1, max_length=240)
    expected_effects: list[dict[str, Any]] = Field(min_length=1, max_length=128)
    verification_sensors: list[str] = Field(min_length=1, max_length=32)


class VerificationObserveBody(BaseModel):
    sensor: str = Field(min_length=1, max_length=80)
    observed_state: dict[str, Any]
    captured_at: float | None = None


class VerificationCompleteBody(BaseModel):
    final_observed_state: dict[str, Any]


class SafetyBody(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    observed_conditions: dict[str, bool] = Field(default_factory=dict)
    reversible: bool | None = None
    requested_ppe: list[str] = Field(default_factory=list, max_length=32)


class RealityIngestBody(BaseModel):
    modality: str = Field(min_length=1, max_length=80)
    observed_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="object", max_length=80)
    label: str | None = Field(default=None, max_length=240)
    stable_key: str | None = Field(default=None, max_length=240)
    attributes: dict[str, Any] = Field(default_factory=dict)
    relations: list[dict[str, Any]] = Field(default_factory=list, max_length=128)
    confidence: float = Field(default=0.7, ge=0, le=1)
    freshness_seconds: float = Field(default=30, gt=0, le=86400)


class BenchmarkBody(BaseModel):
    suite: dict[str, Any]


def sensorium_v3_router(runtime) -> APIRouter:
    """Sensorium 3 intelligence surfaces; no route receives action authority."""

    router = APIRouter(
        prefix="/sensorium/v3",
        tags=["sensorium", "causal-world-intelligence", "active-perception"],
    )
    registry = runtime.get("device_registry") if runtime else None
    settings = runtime.get("settings") if runtime else None
    events = runtime.get("events") if runtime else None
    if registry is None:
        raise RuntimeError("Sensorium 3 requires device registry")
    data_dir_value = getattr(settings, "data_dir", None)
    if data_dir_value is None:
        raise RuntimeError("Sensorium 3 requires a durable data directory")
    data_dir = Path(data_dir_value)
    db = data_dir / "sensorium-v3.sqlite3"

    world = runtime.get("sensorium_world")
    if world is None:
        world = TemporalWorldModel(data_dir / "sensorium-world.sqlite3", events=events)
        runtime["sensorium_world"] = world

    def component(key: str, factory):
        value = runtime.get(key)
        if value is None:
            value = factory()
            runtime[key] = value
        return value

    active = component("sensorium_v3_active", lambda: ActivePerceptionPlanner(events=events))
    scene = component("sensorium_v3_scene", lambda: SemanticSceneGraph(db, events=events))
    causal = component("sensorium_v3_causal", lambda: CausalWorldModel(db, world=world, events=events))
    tasks = component("sensorium_v3_tasks", lambda: TaskStateTracker(db, events=events))
    procedures = component("sensorium_v3_procedures", lambda: ProceduralMemory(db, events=events))
    simulator = component("sensorium_v3_simulator", lambda: OutcomeSimulator(db, events=events))
    feedback = component(
        "sensorium_v3_feedback",
        lambda: ActionObservationLoop(db, world=world, events=events),
    )
    safety = component("sensorium_v3_safety", lambda: PhysicalSafetyEngine(events=events))
    reality = component(
        "sensorium_v3_reality",
        lambda: UnifiedRealityModel(world=world, scene=scene, events=events),
    )
    benchmark = component("sensorium_v3_benchmark", SensoriumBenchmark)

    def auth(authorization: str | None, device_id: str | None, *scopes: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in scopes:
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def translate(exc: Exception) -> HTTPException:
        if isinstance(exc, PermissionError):
            return HTTPException(403, str(exc)[:300] or "Sensorium 3 operation is not permitted")
        if isinstance(exc, KeyError):
            return HTTPException(404, str(exc)[:300] or "Sensorium 3 resource not found")
        if isinstance(exc, ValueError):
            return HTTPException(422, str(exc)[:300])
        return HTTPException(409, str(exc)[:300] or "Sensorium 3 operation is unavailable")

    @router.get("/status")
    def status(
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return {
            "version": "3.0",
            "primary": [
                "active_perception",
                "causal_world_model",
                "semantic_scene_graph",
                "task_state",
                "learning_from_demonstration",
                "outcome_simulation",
                "action_observation_verification",
                "physical_safety",
                "unified_reality",
                "intelligence_benchmarking",
            ],
            "secondary_foundations": [
                "environment_prediction",
                "anomaly_detection",
                "local_multimodal_routing",
                "indoor_positioning",
                "matter_homekit_boundary",
                "robotics_boundary",
                "room_reconstruction",
                "collaborative_perception",
            ],
            "execution_authority": False,
        }

    @router.post("/perception/plan")
    def plan_perception(
        body: ActivePerceptionBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        governed_candidates = []
        for candidate in body.candidates:
            governed = dict(candidate)
            sensor = str(governed.get("sensor") or "").strip().lower()
            scope = SENSOR_SCOPES.get(sensor)
            governed["permitted"] = bool(scope and registry.authorize(device_id, scope))
            governed["active_session"] = False
            governed_candidates.append(governed)
        try:
            return active.plan(
                body.question,
                candidates=governed_candidates,
                uncertainty=body.uncertainty,
                urgency=body.urgency,
                max_observations=body.max_observations,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/scene/entities/resolve")
    def resolve_entity(
        body: SceneEntityBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        try:
            return scene.resolve_or_create(
                body.observed_id,
                kind=body.kind,
                label=body.label,
                stable_key=body.stable_key,
                source_device_id=device_id,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/scene/relations")
    def relate(
        body: SceneRelationBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        try:
            return scene.relate(
                body.subject_id,
                body.predicate,
                body.object_id,
                source_device_id=device_id,
                source_modality=body.source_modality,
                confidence=body.confidence,
                freshness_seconds=body.freshness_seconds,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/scene")
    def scene_snapshot(
        limit: int = Query(default=500, ge=1, le=2000),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return scene.snapshot(limit=limit)

    @router.post("/causal/hypotheses")
    def causal_hypothesis(
        body: CausalHypothesisBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return causal.propose(body.cause, body.effect, description=body.description, prior=body.prior)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/causal/hypotheses/{hypothesis_id}/evidence")
    def causal_evidence(
        hypothesis_id: str,
        body: CausalEvidenceBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return causal.add_evidence(
                hypothesis_id,
                evidence_type=body.evidence_type,
                supports=body.supports,
                confidence=body.confidence,
                source=body.source,
                details=body.details,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/causal/hypotheses/{hypothesis_id}/counterfactual")
    def counterfactual(
        hypothesis_id: str,
        body: CounterfactualBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return causal.counterfactual(
                hypothesis_id,
                intervention=body.intervention,
                assume_no_unmodeled_causes=body.assume_no_unmodeled_causes,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/causal/hypotheses")
    def causal_list(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return {"hypotheses": causal.list_hypotheses(limit=limit), "execution_authority": False}

    @router.post("/tasks")
    def create_task(
        body: TaskCreateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return tasks.create(body.title, purpose=body.purpose, steps=body.steps)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/tasks/{task_id}/steps/{step_index}")
    def update_task_step(
        task_id: str,
        step_index: int,
        body: TaskStepBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return tasks.update_step(
                task_id,
                step_index,
                state=body.state,
                uncertainty=body.uncertainty,
                observed_state=body.observed_state,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/tasks/{task_id}/hypotheses")
    def task_hypothesis(
        task_id: str,
        body: TaskHypothesisBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return tasks.record_hypothesis(
                task_id,
                description=body.description,
                probability=body.probability,
                evidence=body.evidence,
                status=body.status,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/tasks/{task_id}")
    def task_state(
        task_id: str,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return tasks.state(task_id)
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/procedures/learn")
    def learn_procedure(
        body: ProcedureLearnBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin", "memory:sensitive")
        try:
            return procedures.learn(
                body.name,
                demonstrations=body.demonstrations,
                description=body.description,
                prerequisites=body.prerequisites,
                safety_conditions=body.safety_conditions,
                checkpoints=body.checkpoints,
                source_devices=body.source_devices,
                explicit_owner_save=body.explicit_owner_save,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/procedures")
    def list_procedures(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        return {"procedures": procedures.list(limit=limit), "execution_authority": False}

    @router.post("/simulator/models")
    def register_outcome_model(
        body: OutcomeModelBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin")
        try:
            return simulator.register_model(
                body.action_type,
                preconditions=body.preconditions,
                effects=body.effects,
                reversible=body.reversible,
                hazards=body.hazards,
                confidence=body.confidence,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/simulator/simulate")
    def simulate(
        body: SimulateBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return simulator.simulate(
                body.action_type,
                current_state=body.current_state,
                parameters=body.parameters,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/feedback")
    def begin_feedback(
        body: VerificationStartBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return feedback.begin(
                body.proposed_action_id,
                approval_reference=body.approval_reference,
                expected_effects=body.expected_effects,
                verification_sensors=body.verification_sensors,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/feedback/{verification_id}/observe")
    def observe_feedback(
        verification_id: str,
        body: VerificationObserveBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        sensor = body.sensor.strip().lower()
        scope = SENSOR_SCOPES.get(sensor)
        if scope is None:
            raise HTTPException(422, "Unsupported Sensorium verification sensor")
        auth(authorization, x_device_id, scope)
        if sensor in SENSITIVE_SENSORS:
            auth(authorization, x_device_id, "memory:sensitive")
        try:
            return feedback.observe(
                verification_id,
                sensor=sensor,
                observed_state=body.observed_state,
                source_device_id=device_id,
                captured_at=body.captured_at,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/feedback/{verification_id}/complete")
    def complete_feedback(
        verification_id: str,
        body: VerificationCompleteBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return feedback.complete(
                verification_id,
                final_observed_state=body.final_observed_state,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/safety/evaluate")
    def evaluate_safety(
        body: SafetyBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        try:
            return safety.evaluate(
                body.description,
                observed_conditions=body.observed_conditions,
                reversible=body.reversible,
                requested_ppe=body.requested_ppe,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.post("/reality/ingest")
    def ingest_reality(
        body: RealityIngestBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        device_id = auth(authorization, x_device_id, "device:read")
        modality = body.modality.strip().lower()
        scope = SENSOR_SCOPES.get(modality)
        if scope is None:
            raise HTTPException(422, "Unified reality ingestion requires a governed Sensorium modality")
        auth(authorization, x_device_id, scope)
        if modality in SENSITIVE_SENSORS:
            auth(authorization, x_device_id, "memory:sensitive")
        try:
            return reality.ingest(
                source_device_id=device_id,
                trusted_device=True,
                permission_valid=True,
                modality=modality,
                observed_id=body.observed_id,
                kind=body.kind,
                label=body.label,
                stable_key=body.stable_key,
                attributes=body.attributes,
                relations=body.relations,
                confidence=body.confidence,
                freshness_seconds=body.freshness_seconds,
            )
        except Exception as exc:
            raise translate(exc) from exc

    @router.get("/reality")
    def get_reality(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:read")
        return reality.snapshot(limit=limit)

    @router.post("/benchmarks/evaluate")
    def evaluate_benchmark(
        body: BenchmarkBody,
        authorization: str | None = Header(default=None),
        x_device_id: str | None = Header(default=None),
    ):
        auth(authorization, x_device_id, "device:admin")
        try:
            return benchmark.report(body.suite)
        except Exception as exc:
            raise translate(exc) from exc

    return router
