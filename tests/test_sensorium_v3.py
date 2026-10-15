from __future__ import annotations

import pytest

from core.events import EventBus
from sensorium.action_feedback import ActionObservationLoop
from sensorium.active_perception import ActivePerceptionPlanner
from sensorium.advanced_context import (
    CollaborativePerception,
    ContextAnomalyDetector,
    EcosystemBoundary,
    IndoorPositioningFusion,
    LocalModelProfile,
    LocalMultimodalRegistry,
    PredictiveEnvironmentModel,
    RoboticsBoundary,
    RoomReconstruction,
)
from sensorium.benchmark import SensoriumBenchmark
from sensorium.causal_world import CausalWorldModel
from sensorium.outcome_simulator import OutcomeSimulator
from sensorium.physical_safety import PhysicalSafetyEngine
from sensorium.procedural_memory import ProceduralMemory
from sensorium.scene_graph import SemanticSceneGraph
from sensorium.task_state import TaskStateTracker
from sensorium.unified_reality import UnifiedRealityModel
from sensorium.world_model import TemporalWorldModel


def test_active_perception_prefers_information_without_granting_sensor():
    planner = ActivePerceptionPlanner()
    result = planner.plan(
        "Which router light is failing?",
        uncertainty=0.9,
        candidates=[
            {
                "sensor": "camera",
                "query": "closer view of WAN LED",
                "expected_information_gain": 0.95,
                "uncertainty_reduction": 0.9,
                "privacy_cost": 0.2,
                "battery_cost": 0.2,
                "latency_ms": 200,
                "permitted": True,
            },
            {
                "sensor": "microphone",
                "query": "listen for router noise",
                "expected_information_gain": 0.1,
                "uncertainty_reduction": 0.1,
                "privacy_cost": 0.7,
                "battery_cost": 0.1,
                "latency_ms": 100,
                "permitted": True,
            },
        ],
    )
    assert result["selected"][0]["sensor"] == "camera"
    assert result["activation_authorized"] is False
    assert result["selected"][0]["execution_authority"] is False


def test_active_perception_refuses_unpermitted_candidate():
    result = ActivePerceptionPlanner().plan(
        "inspect the label",
        candidates=[
            {
                "sensor": "camera",
                "query": "read label",
                "expected_information_gain": 1,
                "uncertainty_reduction": 1,
                "permitted": False,
            }
        ],
    )
    assert result["selected"] == []
    assert result["rejected"][0]["reason"].startswith("no current permission")


def test_scene_graph_persists_identity_across_frames(tmp_path):
    graph = SemanticSceneGraph(tmp_path / "v3.sqlite3")
    first = graph.resolve_or_create(
        "frame-1-object-7",
        kind="tool",
        label="screwdriver",
        stable_key="visual-fingerprint-123",
        source_device_id="phone-1",
    )
    second = graph.resolve_or_create(
        "frame-2-object-2",
        kind="tool",
        label="screwdriver",
        stable_key="visual-fingerprint-123",
        source_device_id="phone-1",
    )
    assert first["entity_id"] == second["entity_id"]
    assert second["matched_by"] == "stable_key"


def test_scene_graph_relationships_keep_provenance(tmp_path):
    graph = SemanticSceneGraph(tmp_path / "v3.sqlite3")
    owner = graph.resolve_or_create("owner", kind="person", stable_key="owner")
    tool = graph.resolve_or_create("tool-1", kind="tool", stable_key="tool-serial")
    relation = graph.relate(
        owner["entity_id"],
        "holding",
        tool["entity_id"],
        source_device_id="phone-1",
        source_modality="vision",
        confidence=0.9,
    )
    assert relation["execution_authority"] is False
    snapshot = graph.snapshot()
    assert snapshot["relations"][0]["source_device_id"] == "phone-1"


def test_causal_model_distinguishes_observation_from_intervention(tmp_path):
    model = CausalWorldModel(tmp_path / "v3.sqlite3")
    hypothesis = model.propose(
        {"cable": "HDMI-B", "connected": True},
        {"display": "on"},
        description="Connecting HDMI-B causes the display to come on",
    )
    observational = model.add_evidence(
        hypothesis["hypothesis_id"],
        evidence_type="temporal_precedence",
        supports=True,
        confidence=1,
        source="world-model",
    )
    assert observational["causal_basis"] == "observational-hypothesis"
    intervention = model.add_evidence(
        hypothesis["hypothesis_id"],
        evidence_type="intervention",
        supports=True,
        confidence=1,
        source="owner-approved-test",
    )
    assert intervention["causal_basis"] == "intervention-supported"
    counterfactual = model.counterfactual(
        hypothesis["hypothesis_id"],
        intervention={"connected": True},
    )
    assert counterfactual["action_authorized"] is False
    assert counterfactual["execution_authority"] is False


def test_causal_counterexamples_lower_confidence(tmp_path):
    model = CausalWorldModel(tmp_path / "v3.sqlite3")
    hypothesis = model.propose(
        {"router": "powered"},
        {"internet": "online"},
        description="Router power causes internet connectivity",
        prior=0.7,
    )
    lowered = model.add_evidence(
        hypothesis["hypothesis_id"],
        evidence_type="counterexample",
        supports=True,
        confidence=1,
        source="network-sensor",
    )
    assert lowered["score"] < 0.7


def test_task_state_tracks_progress_and_hypotheses(tmp_path):
    tracker = TaskStateTracker(tmp_path / "v3.sqlite3")
    task = tracker.create(
        "Assemble monitor arm",
        purpose="complete assembly safely",
        steps=[
            {"title": "attach base", "expected_state": {"base": "secure"}},
            {"title": "attach arm", "expected_state": {"arm": "secure"}},
        ],
    )
    task_id = task["task"]["task_id"]
    updated = tracker.update_step(task_id, 1, state="completed", uncertainty=0.1)
    tracker.record_hypothesis(
        task_id,
        description="missing screw is under packaging",
        probability=0.6,
    )
    state = tracker.state(task_id)
    assert updated["progress"] == 0.5
    assert state["hypotheses"][0]["description"].startswith("missing screw")
    assert state["execution_authority"] is False


def test_procedural_memory_requires_explicit_owner_save(tmp_path):
    memory = ProceduralMemory(tmp_path / "v3.sqlite3")
    with pytest.raises(PermissionError):
        memory.learn(
            "Router setup",
            demonstrations=[{"steps": [{"action": "open settings"}]}],
            explicit_owner_save=False,
        )


def test_procedural_memory_learns_consensus_steps_without_execution_authority(tmp_path):
    memory = ProceduralMemory(tmp_path / "v3.sqlite3")
    learned = memory.learn(
        "Router setup",
        demonstrations=[
            {
                "steps": [
                    {"action": "disable bridge mode", "expected_state": {"bridge": False}},
                    {"action": "restart router", "expected_state": {"online": True}},
                ]
            },
            {
                "steps": [
                    {"action": "disable bridge mode", "expected_state": {"bridge": False}},
                    {"action": "restart router", "expected_state": {"online": True}},
                ]
            },
        ],
        safety_conditions=["do not reset factory settings"],
        explicit_owner_save=True,
    )
    assert learned["steps"][0]["confidence"] == 1
    assert learned["execution_authority"] is False


def test_outcome_simulator_predicts_state_but_never_authorizes(tmp_path):
    simulator = OutcomeSimulator(tmp_path / "v3.sqlite3")
    simulator.register_model(
        "disconnect-wan",
        preconditions=[{"path": "router.power", "equals": True}],
        effects=[{"path": "router.internet", "op": "set", "value": False}],
        reversible=True,
        confidence=0.9,
    )
    result = simulator.simulate(
        "disconnect-wan",
        current_state={"router": {"power": True, "internet": True}},
    )
    assert result["predicted_state"]["router"]["internet"] is False
    assert result["action_authorized"] is False
    assert result["execution_authority"] is False


def test_action_feedback_requires_approval_reference_and_verifies_effect(tmp_path):
    events = EventBus()
    feedback = ActionObservationLoop(tmp_path / "v3.sqlite3", events=events)
    with pytest.raises(ValueError):
        feedback.begin(
            "action-1",
            approval_reference="",
            expected_effects=[{"path": "router.online", "after": False}],
            verification_sensors=["network"],
        )
    started = feedback.begin(
        "action-1",
        approval_reference="approval-123",
        expected_effects=[{"path": "router.online", "after": False}],
        verification_sensors=["network"],
    )
    assert started["state"] == "awaiting_execution"
    events.emit(
        "approval.completed",
        approval_id="approval-123",
        execution_id="action-1",
        tool="network.disconnect",
    )
    assert feedback.get(started["verification_id"])["state"] == "awaiting_observation"
    feedback.observe(
        started["verification_id"],
        sensor="network",
        observed_state={"router": {"online": False}},
        source_device_id="laptop-1",
    )
    complete = feedback.complete(
        started["verification_id"],
        final_observed_state={"router": {"online": False}},
    )
    assert complete["result"]["success_ratio"] == 1
    assert complete["action_executed_here"] is False


def test_feedback_rejects_unselected_sensor(tmp_path):
    events = EventBus()
    feedback = ActionObservationLoop(tmp_path / "v3.sqlite3", events=events)
    started = feedback.begin(
        "action-1",
        approval_reference="approval-123",
        expected_effects=[{"path": "device.on", "after": True}],
        verification_sensors=["camera"],
    )
    events.emit(
        "approval.completed",
        approval_id="approval-123",
        execution_id="action-1",
        tool="device.power",
    )
    with pytest.raises(PermissionError):
        feedback.observe(
            started["verification_id"],
            sensor="microphone",
            observed_state={},
            source_device_id="phone-1",
        )


def test_physical_safety_blocks_unverified_mains_work():
    result = PhysicalSafetyEngine().evaluate(
        "repair a live wire in the wall outlet",
        observed_conditions={"power_isolated": False, "unknown_live_state": True},
    )
    assert result["risk"] == "critical"
    assert result["proposal_blocked"] is True
    assert result["approval_granted"] is False


def test_unified_reality_preserves_device_provenance(tmp_path):
    world = TemporalWorldModel(tmp_path / "world.sqlite3")
    scene = SemanticSceneGraph(tmp_path / "v3.sqlite3")
    reality = UnifiedRealityModel(world=world, scene=scene)
    result = reality.ingest(
        source_device_id="phone-1",
        trusted_device=True,
        permission_valid=True,
        modality="vision",
        observed_id="router-frame-a",
        kind="router",
        label="office router",
        stable_key="router-mac-redacted-fingerprint",
        attributes={"wan_led": "red"},
        confidence=0.9,
    )
    entity = world.entity(result["entity_id"])
    assert entity["current"]["wan_led"]["source"] == "device:phone-1"
    assert result["execution_authority"] is False


def test_unified_reality_refuses_untrusted_or_unpermitted_evidence(tmp_path):
    reality = UnifiedRealityModel(
        world=TemporalWorldModel(tmp_path / "world.sqlite3"),
        scene=SemanticSceneGraph(tmp_path / "v3.sqlite3"),
    )
    with pytest.raises(PermissionError):
        reality.ingest(
            source_device_id="unknown",
            trusted_device=False,
            permission_valid=True,
            modality="vision",
            observed_id="x",
            kind="object",
            label=None,
            stable_key=None,
            attributes={},
        )


def test_benchmark_covers_core_quality_metrics():
    benchmark = SensoriumBenchmark()
    report = benchmark.report(
        {
            "object_persistence": {
                "predicted": ["a", "a", "b"],
                "truth": ["a", "a", "b"],
            },
            "ocr": {"predicted": "ABC123", "truth": "ABC123"},
            "calibration": [
                {"confidence": 0.9, "correct": True},
                {"confidence": 0.2, "correct": False},
            ],
            "causal": {"predicted": [True, False], "truth": [True, False]},
            "task_progress": {"predicted": [0.5, 1.0], "truth": [0.5, 1.0]},
            "battery": [
                {"timestamp": 0, "battery_percent": 100},
                {"timestamp": 3600, "battery_percent": 95},
            ],
            "privacy": [{"sensor_used_without_permission": False}],
        }
    )
    assert report["metrics"]["object_persistence"]["accuracy"] == 1
    assert report["metrics"]["privacy"]["violations"] == 0
    assert report["execution_authority"] is False


def test_environment_prediction_and_anomaly_detection():
    prediction = PredictiveEnvironmentModel().predict_numeric(
        [
            {"timestamp": 0, "value": 20},
            {"timestamp": 60, "value": 21},
            {"timestamp": 120, "value": 22},
        ],
        horizon_seconds=60,
    )
    assert prediction["predicted_value"] > 22
    anomaly = ContextAnomalyDetector().score(
        [10, 10.1, 9.9, 10.0, 10.05],
        20,
    )
    assert anomaly["anomaly"] is True


def test_local_multimodal_registry_prefers_smallest_capable_local_model():
    registry = LocalMultimodalRegistry()
    registry.register(
        LocalModelProfile("large", ("vision",), ("ocr",), 10_000_000)
    )
    registry.register(
        LocalModelProfile("small", ("vision",), ("ocr",), 1_000_000)
    )
    chosen = registry.choose(modality="vision", operation="ocr", input_bytes=500_000)
    assert chosen["model_id"] == "small"


def test_indoor_positioning_prioritizes_uwb():
    result = IndoorPositioningFusion().fuse(
        [
            {"source": "wifi", "x": 0, "y": 0, "confidence": 1},
            {"source": "uwb", "x": 10, "y": 0, "confidence": 1},
        ]
    )
    assert result["position"]["x"] > 5


def test_ecosystem_and_robotics_are_proposal_only():
    ecosystem = EcosystemBoundary().propose_action(
        "matter",
        "thermostat-1",
        "set_temperature",
        {"c": 21},
    )
    robotics = RoboticsBoundary().propose(
        "robot-1",
        "pick",
        {"object": "box"},
    )
    assert ecosystem["action_authorized"] is False
    assert ecosystem["requires_existing_action_authority"] is True
    assert robotics["action_authorized"] is False
    assert robotics["requires_robot_control_authority"] is True


def test_room_reconstruction_and_collaboration_are_semantic_only():
    room = RoomReconstruction().reconstruct(
        [
            {
                "kind": "surface",
                "id": "wall-1",
                "source_device_id": "phone-1",
                "geometry": {"normal": [0, 0, 1]},
                "confidence": 0.9,
            },
            {
                "kind": "anchor",
                "id": "desk-1",
                "source_device_id": "phone-1",
                "geometry": {"x": 1, "y": 2, "z": 0},
                "confidence": 0.8,
            },
        ]
    )
    assert room["raw_media_retained"] is False

    collaborative = CollaborativePerception().fuse(
        [
            {
                "source_device_id": "phone-1",
                "trusted_device": True,
                "permission_valid": True,
                "payload": {"router_led": "green"},
                "confidence": 0.9,
            }
        ]
    )
    assert collaborative["source_count"] == 1
    assert collaborative["raw_media_retained"] is False

    with pytest.raises(ValueError):
        CollaborativePerception().fuse(
            [
                {
                    "source_device_id": "phone-1",
                    "trusted_device": True,
                    "permission_valid": True,
                    "payload": {"image": "raw"},
                }
            ]
        )


def test_action_knowledge_never_becomes_authority(tmp_path):
    simulator = OutcomeSimulator(tmp_path / "v3.sqlite3")
    simulator.register_model(
        "toggle-light",
        preconditions=[],
        effects=[{"path": "light.on", "op": "toggle"}],
        reversible=True,
    )
    predicted = simulator.simulate(
        "toggle-light",
        current_state={"light": {"on": False}},
    )
    safety = PhysicalSafetyEngine().evaluate("toggle a low voltage light", reversible=True)
    assert predicted["execution_authority"] is False
    assert predicted["action_authorized"] is False
    assert safety["approval_granted"] is False
