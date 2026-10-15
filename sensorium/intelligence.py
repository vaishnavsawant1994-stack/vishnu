from __future__ import annotations

import json
import math
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from core.sqlite import Migration, connect_sqlite, run_migrations


def _id(value: str | None = None) -> str:
    return str(value or uuid.uuid4())


def _clean(value: str, field: str, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"invalid {field}")
    return text


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > 128 * 1024:
        raise ValueError("value is too large")
    return encoded


class IntelligenceStore:
    COMPONENT = "sensorium_intelligence_v3"

    def __init__(self, path: Path, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events
        with self.con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "sensorium-v3-records", self._migration),),
            )

    def con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_v3_records(
                namespace TEXT NOT NULL,
                record_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(namespace,record_key)
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_v3_events(
                event_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                record_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sensorium_v3_events ON sensorium_v3_events(namespace,record_key,created_at)"
        )

    def put(self, namespace: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        data = {**payload, "updated_at": now}
        with self.con() as con:
            con.execute(
                """INSERT INTO sensorium_v3_records VALUES(?,?,?,?)
                   ON CONFLICT(namespace,record_key) DO UPDATE SET
                   payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (namespace, key, _json(data), now),
            )
        return data

    def get(self, namespace: str, key: str) -> dict[str, Any]:
        with self.con() as con:
            row = con.execute(
                "SELECT payload_json FROM sensorium_v3_records WHERE namespace=? AND record_key=?",
                (namespace, key),
            ).fetchone()
        if row is None:
            raise KeyError(f"{namespace} record not found")
        return json.loads(row["payload_json"])

    def list(self, namespace: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.con() as con:
            rows = con.execute(
                """SELECT payload_json FROM sensorium_v3_records
                   WHERE namespace=? ORDER BY updated_at DESC LIMIT ?""",
                (namespace, max(1, min(int(limit), 1000))),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def append(self, namespace: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {**payload, "event_id": _id(), "created_at": time.time()}
        with self.con() as con:
            con.execute(
                "INSERT INTO sensorium_v3_events VALUES(?,?,?,?,?)",
                (item["event_id"], namespace, key, _json(item), item["created_at"]),
            )
        return item

    def events_for(self, namespace: str, key: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.con() as con:
            rows = con.execute(
                """SELECT payload_json FROM sensorium_v3_events
                   WHERE namespace=? AND record_key=? ORDER BY created_at ASC LIMIT ?""",
                (namespace, key, max(1, min(int(limit), 2000))),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def emit(self, event: str, **payload: Any) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)


class ActivePerceptionPlanner:
    """Ranks the next useful observation; it never activates a sensor."""

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def plan(self, goal: str, candidates: Iterable[dict[str, Any]], *, uncertainty: float = 0.5, limit: int = 2) -> dict:
        goal = _clean(goal, "goal", 2000)
        ranked = []
        for raw in candidates:
            if not bool(raw.get("available", True)):
                continue
            sensor = _clean(raw.get("sensor", ""), "sensor", 80)
            observation = _clean(raw.get("observation", ""), "observation", 700)
            info = _clamp(raw.get("information_gain", 0))
            reduction = _clamp(raw.get("uncertainty_reduction", 0))
            privacy = _clamp(raw.get("privacy_cost", 0))
            battery = _clamp(raw.get("battery_cost", 0))
            latency = max(0.0, float(raw.get("latency_ms", 0)))
            score = 0.34 * info + 0.30 * reduction - 0.16 * privacy - 0.10 * battery - 0.10 * min(latency / 5000, 1)
            ranked.append(
                {
                    "sensor": sensor,
                    "observation": observation,
                    "information_gain": info,
                    "uncertainty_reduction": reduction,
                    "privacy_cost": privacy,
                    "battery_cost": battery,
                    "latency_ms": latency,
                    "permission_ready": bool(raw.get("permission_ready", False)),
                    "utility_score": round(score, 6),
                    "activation_authorized": False,
                }
            )
        ranked.sort(key=lambda item: item["utility_score"], reverse=True)
        selected = [item for item in ranked if item["utility_score"] > 0][: max(1, min(int(limit), 4))]
        plan = {
            "plan_id": _id(),
            "goal": goal,
            "uncertainty": _clamp(uncertainty),
            "ranked_candidates": ranked,
            "selected": selected,
            "activation_authorized": False,
            "requires_sensor_permission": True,
        }
        self.store.put("perception_plan", plan["plan_id"], plan)
        self.store.emit("sensorium.v3.active_perception.planned", plan_id=plan["plan_id"], activation_authorized=False)
        return plan


class CausalWorldModel:
    """Evidence-weighted causal hypotheses with explicit counterfactual uncertainty."""

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def propose(self, cause: str, effect: str, *, statement: str | None = None, prior: float = 0.5) -> dict:
        record = {
            "hypothesis_id": _id(),
            "cause": _clean(cause, "cause"),
            "effect": _clean(effect, "effect"),
            "statement": _clean(statement or f"{cause} may cause {effect}", "statement", 1200),
            "prior": _clamp(prior),
            "confidence": _clamp(prior),
            "status": "open",
            "causality_proven": False,
            "execution_authority": False,
        }
        return self.store.put("causal_hypothesis", record["hypothesis_id"], record)

    def add_evidence(self, hypothesis_id: str, *, direction: str, weight: float, source: str, summary: str) -> dict:
        if direction not in {"support", "contradict"}:
            raise ValueError("direction must be support or contradict")
        hypothesis = self.store.get("causal_hypothesis", hypothesis_id)
        self.store.append(
            "causal_evidence",
            hypothesis_id,
            {
                "direction": direction,
                "weight": _clamp(weight),
                "source": _clean(source, "source", 200),
                "summary": _clean(summary, "summary", 1200),
            },
        )
        return self.assess(hypothesis_id)

    def assess(self, hypothesis_id: str) -> dict:
        hypothesis = self.store.get("causal_hypothesis", hypothesis_id)
        evidence = self.store.events_for("causal_evidence", hypothesis_id)
        prior = _clamp(hypothesis["prior"])
        odds = math.log(max(prior, 1e-6) / max(1 - prior, 1e-6))
        for item in evidence:
            odds += (1 if item["direction"] == "support" else -1) * (0.25 + 2 * item["weight"])
        posterior = 1 / (1 + math.exp(-max(-20, min(20, odds))))
        hypothesis.update(
            confidence=posterior,
            status="supported" if posterior >= 0.8 else "unlikely" if posterior <= 0.2 else "open",
            evidence=evidence,
            causality_proven=False,
            execution_authority=False,
        )
        return self.store.put("causal_hypothesis", hypothesis_id, hypothesis)

    def counterfactual(self, hypothesis_id: str, intervention: str, *, assumed: bool) -> dict:
        hypothesis = self.assess(hypothesis_id)
        return {
            "hypothesis_id": hypothesis_id,
            "intervention": _clean(intervention, "intervention", 700),
            "assumed_present": bool(assumed),
            "predicted_effect": hypothesis["effect"],
            "predicted_effect_confidence": _clamp(hypothesis["confidence"] * (0.85 if assumed else 0.65)),
            "counterfactual_only": True,
            "requires_real_observation_to_verify": True,
            "execution_authority": False,
        }


class SemanticSceneGraph:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def upsert_entity(self, *, kind: str, label: str, identity_signature: str | None = None,
                      aliases: Iterable[str] = (), attributes: dict[str, Any] | None = None,
                      confidence: float = 0.7) -> dict:
        signature = str(identity_signature or "").strip()
        entity = None
        for current in self.store.list("scene_entity", 1000):
            if signature and current.get("identity_signature") == signature:
                entity = current
                break
            if set(aliases).intersection(current.get("aliases", [])):
                entity = current
                break
        now = time.time()
        if entity is None:
            entity = {"entity_id": _id(), "first_seen": now}
        entity.update(
            kind=_clean(kind, "kind", 80),
            label=_clean(label, "label", 240),
            identity_signature=signature or entity.get("identity_signature"),
            aliases=sorted(set([label, *aliases, *entity.get("aliases", [])])),
            attributes={**entity.get("attributes", {}), **(attributes or {})},
            last_seen=now,
            confidence=_clamp(confidence),
            execution_authority=False,
        )
        return self.store.put("scene_entity", entity["entity_id"], entity)

    def relate(self, subject_id: str, predicate: str, object_id: str, *, source: str, confidence: float = 0.7) -> dict:
        self.store.get("scene_entity", subject_id)
        self.store.get("scene_entity", object_id)
        relation = {
            "relation_id": _id(),
            "subject_id": subject_id,
            "predicate": _clean(predicate, "predicate", 120),
            "object_id": object_id,
            "source": _clean(source, "source", 200),
            "confidence": _clamp(confidence),
            "captured_at": time.time(),
            "active": True,
            "execution_authority": False,
        }
        for old in self.store.list("scene_relation", 1000):
            if old["subject_id"] == subject_id and old["predicate"] == relation["predicate"] and old.get("active"):
                old["active"] = False
                self.store.put("scene_relation", old["relation_id"], old)
        return self.store.put("scene_relation", relation["relation_id"], relation)

    def snapshot(self) -> dict:
        return {
            "entities": self.store.list("scene_entity", 500),
            "relations": [r for r in self.store.list("scene_relation", 1000) if r.get("active")],
            "execution_authority": False,
        }


class TaskStateTracker:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def create(self, title: str, goal: str, steps: list[dict[str, Any]]) -> dict:
        if not steps or len(steps) > 200:
            raise ValueError("task requires 1-200 steps")
        task = {
            "task_id": _id(),
            "title": _clean(title, "title", 240),
            "goal": _clean(goal, "goal", 1200),
            "status": "active",
            "current_step": 0,
            "steps": [
                {
                    "index": index,
                    "instruction": _clean(step.get("instruction", ""), "instruction", 1200),
                    "state": "pending",
                    "expected": step.get("expected", {}),
                    "observed": {},
                    "confidence": _clamp(step.get("confidence", 0.7)),
                }
                for index, step in enumerate(steps)
            ],
            "hypotheses": [],
            "execution_authority": False,
        }
        return self.store.put("task", task["task_id"], task)

    def update_step(self, task_id: str, index: int, *, state: str, observed: dict[str, Any], confidence: float) -> dict:
        if state not in {"pending", "active", "complete", "blocked", "skipped"}:
            raise ValueError("invalid step state")
        task = self.store.get("task", task_id)
        if not 0 <= index < len(task["steps"]):
            raise KeyError("task step not found")
        task["steps"][index].update(state=state, observed=observed, confidence=_clamp(confidence))
        pending = [s["index"] for s in task["steps"] if s["state"] not in {"complete", "skipped"}]
        task["current_step"] = min(pending) if pending else len(task["steps"])
        task["status"] = "complete" if not pending else "blocked" if state == "blocked" else "active"
        return self.store.put("task", task_id, task)

    def add_hypothesis(self, task_id: str, statement: str, confidence: float = 0.5) -> dict:
        task = self.store.get("task", task_id)
        item = {"hypothesis_id": _id(), "statement": _clean(statement, "statement", 1200), "confidence": _clamp(confidence), "status": "open"}
        task["hypotheses"].append(item)
        self.store.put("task", task_id, task)
        return item

    def get(self, task_id: str) -> dict:
        return self.store.get("task", task_id)


class ProceduralMemory:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def learn(self, name: str, demonstrations: list[dict[str, Any]], *, description: str = "",
              prerequisites: Iterable[str] = (), safety_conditions: Iterable[str] = ()) -> dict:
        if not demonstrations or len(demonstrations) > 50:
            raise ValueError("1-50 demonstrations required")
        sequences = [list(d.get("steps", [])) for d in demonstrations]
        if any(not steps or len(steps) > 200 for steps in sequences):
            raise ValueError("each demonstration requires 1-200 steps")
        canonical = max(sequences, key=len)
        steps = []
        for index, step in enumerate(canonical):
            action = _clean(step.get("action", ""), "action", 1000)
            agreement = sum(
                1 for seq in sequences
                if index < len(seq) and str(seq[index].get("action", "")).strip().lower() == action.lower()
            ) / len(sequences)
            steps.append(
                {
                    "index": index,
                    "action": action,
                    "objects": step.get("objects", []),
                    "expected": step.get("expected", {}),
                    "checkpoint": step.get("checkpoint", {}),
                    "confidence": max(0.3, min(0.99, agreement)),
                }
            )
        procedure = {
            "procedure_id": _id(),
            "name": _clean(name, "name", 240),
            "description": str(description or "")[:2000],
            "prerequisites": list(prerequisites),
            "safety_conditions": list(safety_conditions),
            "source_count": len(demonstrations),
            "steps": steps,
            "requires_action_approval": True,
            "execution_authority": False,
        }
        return self.store.put("procedure", procedure["procedure_id"], procedure)

    def get(self, procedure_id: str) -> dict:
        return self.store.get("procedure", procedure_id)


class OutcomeSimulator:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def register(self, action_type: str, effects: list[dict[str, Any]], *, reversible: bool,
                 hazards: Iterable[str] = (), required_scopes: Iterable[str] = (), confidence: float = 0.7) -> dict:
        if not effects or len(effects) > 100:
            raise ValueError("1-100 effects required")
        model = {
            "action_type": _clean(action_type, "action type", 160),
            "effects": effects,
            "reversible": bool(reversible),
            "hazards": list(hazards),
            "required_scopes": list(required_scopes),
            "confidence": _clamp(confidence),
        }
        return self.store.put("action_model", model["action_type"], model)

    def simulate(self, action_type: str, current_state: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict:
        model = self.store.get("action_model", action_type)
        predicted = json.loads(_json(current_state))
        for effect in model["effects"]:
            key, op, value = str(effect.get("key", "")), str(effect.get("op", "set")), effect.get("value")
            if not key:
                continue
            if op == "set":
                predicted[key] = value
            elif op == "delete":
                predicted.pop(key, None)
            elif op == "increment":
                predicted[key] = float(predicted.get(key, 0)) + float(value or 0)
            else:
                raise ValueError("unsupported effect operation")
        return {
            "action_type": action_type,
            "parameters": parameters or {},
            "before": current_state,
            "predicted_after": predicted,
            "reversible": model["reversible"],
            "hazards": model["hazards"],
            "required_scopes": model["required_scopes"],
            "confidence": model["confidence"],
            "simulation_only": True,
            "execution_authority": False,
        }


class ActionObservationVerifier:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def begin(self, action_receipt_id: str, action_type: str, expected: list[dict[str, Any]]) -> dict:
        if not expected:
            raise ValueError("verification expectations required")
        session = {
            "verification_id": _id(),
            "action_receipt_id": _clean(action_receipt_id, "approved action receipt", 200),
            "action_type": _clean(action_type, "action type", 160),
            "expected": expected,
            "observations": [],
            "status": "observing",
            "execution_authority": False,
        }
        return self.store.put("verification", session["verification_id"], session)

    def observe(self, verification_id: str, observation: dict[str, Any]) -> dict:
        session = self.store.get("verification", verification_id)
        if session["status"] != "observing":
            raise ValueError("verification already complete")
        session["observations"].append(observation)
        session["observations"] = session["observations"][-200:]
        return self.store.put("verification", verification_id, session)

    @staticmethod
    def _match(expectation: dict[str, Any], observation: dict[str, Any]) -> bool:
        if observation.get("key") != expectation.get("key"):
            return False
        value, target, op = observation.get("value"), expectation.get("value"), expectation.get("comparator", "equals")
        if op == "equals":
            return value == target
        if op == "not_equals":
            return value != target
        if op == "contains":
            return target in value
        if op == "gte":
            return float(value) >= float(target)
        if op == "lte":
            return float(value) <= float(target)
        raise ValueError("unsupported comparator")

    def finalize(self, verification_id: str) -> dict:
        session = self.store.get("verification", verification_id)
        checks = [
            {**expected, "passed": any(self._match(expected, obs) for obs in session["observations"])}
            for expected in session["expected"]
        ]
        session["checks"] = checks
        session["verified"] = all(check["passed"] for check in checks)
        session["status"] = "verified" if session["verified"] else "mismatch"
        self.store.emit("sensorium.v3.action.verified", verification_id=verification_id, status=session["status"], execution_authority=False)
        return self.store.put("verification", verification_id, session)


class PhysicalSafetyEngine:
    RULES = {
        "mains_voltage": {"ppe": {"insulated_protection"}, "stop": {"exposed_live_conductor", "wet_environment"}, "reversible": True, "severity": "critical"},
        "high_heat": {"ppe": {"heat_protection"}, "stop": {"uncontrolled_flame", "unknown_hot_surface"}, "reversible": False, "severity": "high"},
        "rotating_machinery": {"ppe": {"eye_protection"}, "stop": {"guard_removed", "loose_clothing_near_rotation"}, "reversible": True, "severity": "critical"},
        "pressurized_system": {"ppe": {"eye_protection"}, "stop": {"unknown_pressure", "damaged_vessel"}, "reversible": True, "severity": "high"},
        "chemical_exposure": {"ppe": {"eye_protection", "gloves"}, "stop": {"unknown_chemical", "poor_ventilation"}, "reversible": True, "severity": "high"},
    }

    def evaluate(self, hazard_tags: Iterable[str], *, ppe_present: Iterable[str] = (),
                 observed_conditions: Iterable[str] = (), action_reversible: bool = True) -> dict:
        ppe, conditions = set(ppe_present), set(observed_conditions)
        violations = []
        for hazard in set(hazard_tags):
            rule = self.RULES.get(hazard)
            if not rule:
                continue
            missing = sorted(rule["ppe"] - ppe)
            stops = sorted(rule["stop"] & conditions)
            reversibility = rule["reversible"] and not action_reversible
            if missing or stops or reversibility:
                violations.append({"hazard": hazard, "severity": rule["severity"], "missing_ppe": missing, "stop_conditions": stops, "reversibility_violation": reversibility})
        return {"safe_to_propose": not violations, "violations": violations, "safety_authority": True, "action_authorized": False}


class UnifiedRealityModel:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def ingest(self, *, entity_id: str, attribute: str, value: Any, source_device_id: str, modality: str,
               confidence: float, permission_session_id: str | None = None, ttl_seconds: float | None = None) -> dict:
        key = f"{_clean(entity_id, 'entity', 160)}:{_clean(attribute, 'attribute', 120)}"
        self.store.append(
            "reality",
            key,
            {
                "entity_id": entity_id,
                "attribute": attribute,
                "value": value,
                "source_device_id": _clean(source_device_id, "source device", 200),
                "modality": _clean(modality, "modality", 80),
                "permission_session_id": str(permission_session_id or "").strip() or None,
                "confidence": _clamp(confidence),
                "expires_at": time.time() + float(ttl_seconds) if ttl_seconds else None,
            },
        )
        return self.fuse(entity_id, attribute)

    def fuse(self, entity_id: str, attribute: str) -> dict:
        key = f"{entity_id}:{attribute}"
        now = time.time()
        observations = [x for x in self.store.events_for("reality", key) if not x.get("expires_at") or x["expires_at"] > now]
        if not observations:
            raise KeyError("no active reality observations")
        buckets: dict[str, dict[str, Any]] = {}
        for item in observations:
            token = _json(item["value"])
            bucket = buckets.setdefault(token, {"value": item["value"], "score": 0.0})
            age = max(0.0, now - item["created_at"])
            bucket["score"] += item["confidence"] * math.exp(-age / 300)
        ranked = sorted(buckets.values(), key=lambda x: x["score"], reverse=True)
        total = sum(x["score"] for x in ranked) or 1
        return {
            "entity_id": entity_id,
            "attribute": attribute,
            "value": ranked[0]["value"],
            "confidence": _clamp(ranked[0]["score"] / total),
            "conflict": len(ranked) > 1 and ranked[1]["score"] >= ranked[0]["score"] * 0.65,
            "alternatives": ranked[1:5],
            "provenance": [{k: x.get(k) for k in ("event_id", "source_device_id", "modality", "permission_session_id", "confidence", "created_at")} for x in observations],
            "execution_authority": False,
        }


class SensoriumBenchmark:
    TARGETS = {
        "object_persistence_accuracy": ("gte", 0.90),
        "location_accuracy_m": ("lte", 10.0),
        "gesture_accuracy": ("gte", 0.90),
        "ocr_accuracy": ("gte", 0.95),
        "sound_event_f1": ("gte", 0.85),
        "false_alarm_rate": ("lte", 0.05),
        "uncertainty_calibration_error": ("lte", 0.10),
        "causal_hypothesis_accuracy": ("gte", 0.80),
        "task_progress_accuracy": ("gte", 0.90),
        "battery_drain_percent_per_hour": ("lte", 8.0),
        "privacy_violations": ("lte", 0.0),
    }

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def record(self, suite: str, metrics: dict[str, float], metadata: dict[str, Any] | None = None) -> dict:
        unknown = set(metrics) - set(self.TARGETS)
        if unknown:
            raise ValueError(f"unknown benchmark metrics: {sorted(unknown)}")
        results = {}
        for name, value in metrics.items():
            op, target = self.TARGETS[name]
            passed = float(value) >= target if op == "gte" else float(value) <= target
            results[name] = {"value": float(value), "target": {"comparator": op, "value": target}, "passed": passed}
        run = {"run_id": _id(), "suite": _clean(suite, "suite", 160), "metrics": results, "metadata": metadata or {}, "passed": bool(results) and all(x["passed"] for x in results.values())}
        return self.store.put("benchmark", run["run_id"], run)


class PredictiveContextEngine:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def add_sample(self, series_id: str, value: float, source_device_id: str) -> dict:
        series = _clean(series_id, "series", 160)
        return self.store.append("prediction", series, {"value": float(value), "source_device_id": _clean(source_device_id, "device", 200)})

    def forecast(self, series_id: str, horizon_seconds: float) -> dict:
        points = self.store.events_for("prediction", series_id, 1000)
        if len(points) < 3:
            raise ValueError("at least three samples required")
        xs = [p["created_at"] - points[0]["created_at"] for p in points]
        ys = [p["value"] for p in points]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        slope = 0 if denom == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        intercept = my - slope * mx
        residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        sigma = statistics.pstdev(residuals) if len(residuals) > 1 else 0
        anomaly_score = 0 if sigma <= 1e-9 else abs(residuals[-1]) / sigma
        return {"series_id": series_id, "predicted_value": intercept + slope * (xs[-1] + max(0, horizon_seconds)), "slope_per_second": slope, "anomaly_score": anomaly_score, "anomaly": anomaly_score >= 3, "prediction_only": True, "execution_authority": False}


class AdvancedCapabilityRegistry:
    ALLOWED = {
        "uwb_indoor_positioning", "lidar_room_reconstruction", "matter_observation",
        "homekit_observation", "robotics_observation", "robotics_action_proposal",
        "local_multimodal_model", "collaborative_perception",
    }

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def register(self, capability: str, *, provider: str, device_id: str, available: bool, evidence_level: str, metadata: dict[str, Any] | None = None) -> dict:
        capability = _clean(capability, "capability", 120)
        if capability not in self.ALLOWED:
            raise ValueError("unsupported advanced capability")
        return self.store.put("capability", capability, {"capability": capability, "provider": _clean(provider, "provider", 160), "device_id": _clean(device_id, "device", 200), "available": bool(available), "evidence_level": _clean(evidence_level, "evidence level", 80), "metadata": metadata or {}, "execution_authority": False})

    def get(self, capability: str) -> dict:
        return self.store.get("capability", capability)


class CollaborativePerception:
    FORBIDDEN = {"raw_image", "image_bytes", "raw_video", "video_bytes", "raw_audio", "audio_bytes", "pcm", "base64", "clipboard_content"}

    def __init__(self, reality: UnifiedRealityModel) -> None:
        self.reality = reality

    def ingest(self, *, trusted: bool, permission_session_id: str, source_device_id: str, entity_id: str,
               attribute: str, value: Any, modality: str, confidence: float) -> dict:
        if not trusted:
            raise PermissionError("trusted device required")
        if isinstance(value, dict) and self.FORBIDDEN.intersection(value):
            raise ValueError("raw sensitive media is not accepted")
        result = self.reality.ingest(
            entity_id=entity_id,
            attribute=attribute,
            value=value,
            source_device_id=source_device_id,
            modality=modality,
            confidence=confidence,
            permission_session_id=_clean(permission_session_id, "permission session", 200),
        )
        result.update(collaborative=True, raw_media_accepted=False)
        return result


class SensoriumIntelligence:
    def __init__(self, path: Path, events=None) -> None:
        store = IntelligenceStore(path, events=events)
        self.store = store
        self.active_perception = ActivePerceptionPlanner(store)
        self.causal = CausalWorldModel(store)
        self.scene = SemanticSceneGraph(store)
        self.tasks = TaskStateTracker(store)
        self.procedures = ProceduralMemory(store)
        self.simulator = OutcomeSimulator(store)
        self.verifier = ActionObservationVerifier(store)
        self.safety = PhysicalSafetyEngine()
        self.reality = UnifiedRealityModel(store)
        self.benchmark = SensoriumBenchmark(store)
        self.predictive = PredictiveContextEngine(store)
        self.capabilities = AdvancedCapabilityRegistry(store)
        self.collaboration = CollaborativePerception(self.reality)

    @staticmethod
    def architecture() -> dict:
        return {
            "pipeline": [
                "goal_or_question", "hypotheses_and_task_state", "active_perception_planner",
                "permission_and_attention_manager", "sensors_memory_device_state",
                "temporal_sensor_fusion", "semantic_scene_graph", "causal_world_model",
                "outcome_simulator", "reasoning_and_proposed_action", "approval_policy_and_safety",
                "computer_device_iot_action", "observe_result", "verify_learn_update_world_model",
            ],
            "permanent_invariants": [
                "Knowing what is happening does not grant permission to act.",
                "Predicting the correct action does not grant permission to act.",
                "Learning how to perform an action does not grant permission to act.",
            ],
            "execution_authority": False,
        }
