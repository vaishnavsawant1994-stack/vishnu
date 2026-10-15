from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from sensorium.intelligence import SensoriumIntelligence


class Payload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


def sensorium_intelligence_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/sensorium/v3", tags=["sensorium", "causal-world-intelligence"])
    registry = runtime.get("device_registry") if runtime else None
    settings = runtime.get("settings") if runtime else None
    events = runtime.get("events") if runtime else None
    attention = runtime.get("sensorium_attention") if runtime else None
    world = runtime.get("sensorium_world") if runtime else None
    if registry is None:
        raise RuntimeError("Sensorium 3 requires device registry")
    data_dir = getattr(settings, "data_dir", None)
    if data_dir is None:
        raise RuntimeError("Sensorium 3 requires a durable data directory")
    intelligence = runtime.get("sensorium_intelligence_v3")
    if intelligence is None:
        intelligence = SensoriumIntelligence(Path(data_dir) / "sensorium-intelligence-v3.sqlite3", events=events)
        runtime["sensorium_intelligence_v3"] = intelligence

    def auth(authorization: str | None, device_id: str | None, *scopes: str) -> str:
        resolved = str(device_id or "").strip()
        token = str(authorization or "").removeprefix("Bearer ").strip()
        if not resolved or not token or not registry.authenticate(resolved, token):
            raise HTTPException(401, "Device authentication required")
        for scope in scopes:
            if not registry.authorize(resolved, scope):
                raise HTTPException(403, f"Device is not permitted to use {scope}")
        return resolved

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)[:300]) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc)[:300]) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:300]) from exc
        except Exception as exc:
            raise HTTPException(409, str(exc)[:300]) from exc

    @router.get("/architecture")
    def architecture(authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return intelligence.architecture()

    @router.post("/perception/plan")
    def perception_plan(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        data = body.data
        candidates = list(data.get("candidates") or [])
        attention_plan = None
        if attention is not None:
            attention_plan = attention.plan(
                data.get("goal", ""),
                permitted=data.get("permitted", []),
                privacy_denied=data.get("privacy_denied", []),
                battery_percent=data.get("battery_percent"),
                max_active_sensors=data.get("limit", 2),
            ).public()
            allowed = {item["sensor"] for item in attention_plan["requested"]}
            candidates = [item for item in candidates if item.get("sensor") in allowed or item.get("sensor") == "memory"]
        result = call(
            intelligence.active_perception.plan,
            data.get("goal", ""),
            candidates,
            uncertainty=data.get("uncertainty", 0.5),
            limit=data.get("limit", 2),
        )
        result["attention_plan"] = attention_plan
        return result

    @router.post("/causal/hypotheses")
    def causal_create(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.causal.propose, d.get("cause", ""), d.get("effect", ""), statement=d.get("statement"), prior=d.get("prior", 0.5))

    @router.post("/causal/hypotheses/{hypothesis_id}/evidence")
    def causal_evidence(hypothesis_id: str, body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.causal.add_evidence, hypothesis_id, direction=d.get("direction", ""), weight=d.get("weight", 0), source=d.get("source", ""), summary=d.get("summary", ""))

    @router.post("/causal/hypotheses/{hypothesis_id}/counterfactual")
    def counterfactual(hypothesis_id: str, body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.causal.counterfactual, hypothesis_id, body.data.get("intervention", ""), assumed=bool(body.data.get("assumed", True)))

    @router.post("/scene/entities")
    def scene_entity(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        result = call(
            intelligence.scene.upsert_entity,
            kind=d.get("kind", "object"), label=d.get("label", ""), identity_signature=d.get("identity_signature"),
            aliases=d.get("aliases", []), attributes=d.get("attributes", {}), confidence=d.get("confidence", 0.7),
        )
        if world is not None:
            call(world.observe, result["entity_id"], attribute="scene_identity", value={"kind": result["kind"], "label": result["label"]}, source="sensorium-v3-scene", modality="semantic", confidence=result["confidence"], freshness_seconds=3600, kind=result["kind"], label=result["label"])
        return result

    @router.post("/scene/relations")
    def scene_relation(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        result = call(intelligence.scene.relate, d.get("subject_id", ""), d.get("predicate", ""), d.get("object_id", ""), source=d.get("source", "sensorium-v3"), confidence=d.get("confidence", 0.7))
        if world is not None:
            call(world.relate, result["subject_id"], result["predicate"], result["object_id"], source=d.get("source", "sensorium-v3"), confidence=d.get("confidence", 0.7))
        return result

    @router.get("/scene")
    def scene(authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return intelligence.scene.snapshot()

    @router.post("/tasks")
    def task_create(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.tasks.create, d.get("title", ""), d.get("goal", ""), d.get("steps", []))

    @router.post("/tasks/{task_id}/steps/{index}")
    def task_step(task_id: str, index: int, body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.tasks.update_step, task_id, index, state=d.get("state", ""), observed=d.get("observed", {}), confidence=d.get("confidence", 0.7))

    @router.post("/tasks/{task_id}/hypotheses")
    def task_hypothesis(task_id: str, body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.tasks.add_hypothesis, task_id, body.data.get("statement", ""), body.data.get("confidence", 0.5))

    @router.get("/tasks/{task_id}")
    def task_get(task_id: str, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.tasks.get, task_id)

    @router.post("/procedures/learn")
    def procedure_learn(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        d = body.data
        return call(intelligence.procedures.learn, d.get("name", ""), d.get("demonstrations", []), description=d.get("description", ""), prerequisites=d.get("prerequisites", []), safety_conditions=d.get("safety_conditions", []))

    @router.get("/procedures/{procedure_id}")
    def procedure_get(procedure_id: str, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read", "memory:sensitive")
        return call(intelligence.procedures.get, procedure_id)

    @router.post("/simulation/models")
    def simulation_model(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:admin")
        d = body.data
        return call(intelligence.simulator.register, d.get("action_type", ""), d.get("effects", []), reversible=bool(d.get("reversible", True)), hazards=d.get("hazards", []), required_scopes=d.get("required_scopes", []), confidence=d.get("confidence", 0.7))

    @router.post("/simulation")
    def simulate(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.simulator.simulate, d.get("action_type", ""), d.get("current_state", {}), d.get("parameters", {}))

    @router.post("/verification")
    def verify_begin(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.verifier.begin, d.get("action_receipt_id", ""), d.get("action_type", ""), d.get("expected", []))

    @router.post("/verification/{verification_id}/observations")
    def verify_observe(verification_id: str, body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.verifier.observe, verification_id, body.data)

    @router.post("/verification/{verification_id}/finalize")
    def verify_finalize(verification_id: str, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.verifier.finalize, verification_id)

    @router.post("/safety/evaluate")
    def safety(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        d = body.data
        return call(intelligence.safety.evaluate, d.get("hazard_tags", []), ppe_present=d.get("ppe_present", []), observed_conditions=d.get("observed_conditions", []), action_reversible=bool(d.get("action_reversible", True)))

    @router.post("/reality/observations")
    def reality_ingest(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        controller = auth(authorization, x_device_id, "device:read")
        d = body.data
        source = str(d.get("source_device_id", ""))
        if controller != source and not registry.authorize(controller, "device:admin"):
            raise HTTPException(403, "Cross-device reality ingestion requires device:admin")
        result = call(intelligence.reality.ingest, entity_id=d.get("entity_id", ""), attribute=d.get("attribute", ""), value=d.get("value"), source_device_id=source, modality=d.get("modality", ""), confidence=d.get("confidence", 0.7), permission_session_id=d.get("permission_session_id"), ttl_seconds=d.get("ttl_seconds"))
        if world is not None:
            call(world.observe, d.get("entity_id", ""), attribute=d.get("attribute", ""), value=d.get("value"), source=source, modality=d.get("modality", "semantic"), confidence=d.get("confidence", 0.7), freshness_seconds=d.get("ttl_seconds") or 300)
        return result

    @router.get("/reality/{entity_id}/{attribute}")
    def reality(entity_id: str, attribute: str, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.reality.fuse, entity_id, attribute)

    @router.post("/benchmarks")
    def benchmark(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:admin")
        d = body.data
        return call(intelligence.benchmark.record, d.get("suite", ""), d.get("metrics", {}), d.get("metadata", {}))

    @router.post("/prediction/samples")
    def prediction_sample(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        controller = auth(authorization, x_device_id, "device:read")
        d = body.data
        source = str(d.get("source_device_id", ""))
        if controller != source and not registry.authorize(controller, "device:admin"):
            raise HTTPException(403, "Cross-device prediction samples require device:admin")
        return call(intelligence.predictive.add_sample, d.get("series_id", ""), d.get("value", 0), source)

    @router.get("/prediction/{series_id}")
    def prediction(series_id: str, horizon_seconds: float = Query(default=300, ge=0, le=604800), authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.predictive.forecast, series_id, horizon_seconds)

    @router.post("/capabilities")
    def capability_register(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:admin")
        d = body.data
        return call(intelligence.capabilities.register, d.get("capability", ""), provider=d.get("provider", ""), device_id=d.get("device_id", ""), available=bool(d.get("available", False)), evidence_level=d.get("evidence_level", "declared"), metadata=d.get("metadata", {}))

    @router.get("/capabilities/{capability}")
    def capability(capability: str, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        auth(authorization, x_device_id, "device:read")
        return call(intelligence.capabilities.get, capability)

    @router.post("/collaboration/semantic")
    def collaboration(body: Payload, authorization: str | None = Header(default=None), x_device_id: str | None = Header(default=None)):
        controller = auth(authorization, x_device_id, "device:read")
        d = body.data
        source = str(d.get("source_device_id", ""))
        trusted = controller == source or registry.authorize(controller, "device:admin")
        return call(intelligence.collaboration.ingest, trusted=trusted, permission_session_id=d.get("permission_session_id", ""), source_device_id=source, entity_id=d.get("entity_id", ""), attribute=d.get("attribute", ""), value=d.get("value"), modality=d.get("modality", ""), confidence=d.get("confidence", 0.7))

    return router
