from __future__ import annotations

import pytest

from sensorium.intelligence import SensoriumIntelligence


def v3(tmp_path):
    return SensoriumIntelligence(tmp_path / "sensorium-v3.sqlite3")


def test_active_perception_chooses_information_gain_without_authority(tmp_path):
    intelligence = v3(tmp_path)
    plan = intelligence.active_perception.plan(
        "Inspect the router WAN light",
        [
            {
                "sensor": "camera",
                "observation": "closer view of WAN LED",
                "information_gain": 0.95,
                "uncertainty_reduction": 0.9,
                "privacy_cost": 0.2,
                "battery_cost": 0.2,
                "latency_ms": 250,
                "available": True,
                "permission_ready": False,
            },
            {
                "sensor": "microphone",
                "observation": "listen for router noise",
                "information_gain": 0.2,
                "uncertainty_reduction": 0.1,
                "privacy_cost": 0.8,
                "battery_cost": 0.2,
                "latency_ms": 100,
                "available": True,
                "permission_ready": True,
            },
        ],
        uncertainty=0.8,
        limit=1,
    )
    assert plan["selected"][0]["sensor"] == "camera"
    assert plan["selected"][0]["activation_authorized"] is False
    assert plan["requires_sensor_permission"] is True


def test_causal_model_keeps_hypotheses_and_counterfactuals_uncertain(tmp_path):
    intelligence = v3(tmp_path)
    hypothesis = intelligence.causal.propose("HDMI B connected", "display came on", prior=0.4)
    assessed = intelligence.causal.add_evidence(
        hypothesis["hypothesis_id"],
        direction="support",
        weight=0.9,
        source="temporal-world-model",
        summary="Display changed immediately after cable connection.",
    )
    assert assessed["confidence"] > 0.4
    assert assessed["causality_proven"] is False
    counterfactual = intelligence.causal.counterfactual(
        hypothesis["hypothesis_id"],
        "Disconnect HDMI B",
        assumed=False,
    )
    assert counterfactual["counterfactual_only"] is True
    assert counterfactual["execution_authority"] is False


def test_scene_graph_preserves_identity_and_relations_across_observations(tmp_path):
    intelligence = v3(tmp_path)
    first = intelligence.scene.upsert_entity(
        kind="tool",
        label="screwdriver",
        identity_signature="visual:driver:red-handle",
        aliases=["red screwdriver"],
        confidence=0.8,
    )
    second = intelligence.scene.upsert_entity(
        kind="tool",
        label="screwdriver",
        identity_signature="visual:driver:red-handle",
        attributes={"location": "desk"},
        confidence=0.9,
    )
    owner = intelligence.scene.upsert_entity(kind="person", label="owner", identity_signature="owner")
    relation = intelligence.scene.relate(
        owner["entity_id"], "holding", second["entity_id"], source="camera", confidence=0.9
    )
    assert first["entity_id"] == second["entity_id"]
    assert relation["predicate"] == "holding"
    assert relation["execution_authority"] is False


def test_task_state_and_demonstration_learning_never_grant_execution(tmp_path):
    intelligence = v3(tmp_path)
    task = intelligence.tasks.create(
        "Assemble monitor stand",
        "Finish assembly safely",
        [
            {"instruction": "Attach base", "expected": {"base_attached": True}},
            {"instruction": "Tighten two screws", "expected": {"screws": 2}},
        ],
    )
    updated = intelligence.tasks.update_step(
        task["task_id"], 0, state="complete", observed={"base_attached": True}, confidence=0.95
    )
    assert updated["current_step"] == 1

    procedure = intelligence.procedures.learn(
        "Router recovery",
        [
            {"steps": [{"action": "disable bridge mode"}, {"action": "restart router"}]},
            {"steps": [{"action": "disable bridge mode"}, {"action": "restart router"}]},
        ],
        prerequisites=["owner present"],
        safety_conditions=["do not reset credentials without explicit approval"],
    )
    assert procedure["source_count"] == 2
    assert procedure["requires_action_approval"] is True
    assert procedure["execution_authority"] is False


def test_simulation_safety_and_post_action_verification(tmp_path):
    intelligence = v3(tmp_path)
    intelligence.simulator.register(
        "disconnect_wan",
        [{"key": "internet_connected", "op": "set", "value": False}],
        reversible=True,
        hazards=[],
        required_scopes=["device:control"],
        confidence=0.85,
    )
    simulation = intelligence.simulator.simulate(
        "disconnect_wan", {"internet_connected": True, "router_powered": True}
    )
    assert simulation["predicted_after"]["internet_connected"] is False
    assert simulation["predicted_after"]["router_powered"] is True
    assert simulation["execution_authority"] is False

    unsafe = intelligence.safety.evaluate(
        ["mains_voltage"],
        ppe_present=[],
        observed_conditions=["exposed_live_conductor"],
        action_reversible=True,
    )
    assert unsafe["safe_to_propose"] is False
    assert unsafe["action_authorized"] is False

    verification = intelligence.verifier.begin(
        "approved-action-123",
        "disconnect_wan",
        [{"key": "internet_connected", "comparator": "equals", "value": False}],
    )
    intelligence.verifier.observe(
        verification["verification_id"], {"key": "internet_connected", "value": False, "source": "network"}
    )
    result = intelligence.verifier.finalize(verification["verification_id"])
    assert result["verified"] is True
    assert result["execution_authority"] is False


def test_unified_reality_keeps_provenance_and_collaboration_refuses_raw_media(tmp_path):
    intelligence = v3(tmp_path)
    intelligence.reality.ingest(
        entity_id="laptop",
        attribute="location",
        value="desk",
        source_device_id="phone-1",
        modality="camera",
        confidence=0.9,
        permission_session_id="session-a",
    )
    fused = intelligence.reality.ingest(
        entity_id="laptop",
        attribute="location",
        value="desk",
        source_device_id="laptop-1",
        modality="self_state",
        confidence=0.8,
    )
    assert {item["source_device_id"] for item in fused["provenance"]} == {"phone-1", "laptop-1"}
    assert fused["execution_authority"] is False

    with pytest.raises(ValueError):
        intelligence.collaboration.ingest(
            trusted=True,
            permission_session_id="session-a",
            source_device_id="phone-1",
            entity_id="room",
            attribute="view",
            value={"raw_image": "not-allowed"},
            modality="camera",
            confidence=0.9,
        )


def test_benchmark_prediction_and_optional_hardware_capabilities(tmp_path):
    intelligence = v3(tmp_path)
    benchmark = intelligence.benchmark.record(
        "sensorium-v3-core",
        {
            "object_persistence_accuracy": 0.95,
            "causal_hypothesis_accuracy": 0.85,
            "privacy_violations": 0,
        },
    )
    assert benchmark["passed"] is True

    for value in (10.0, 11.0, 12.0, 13.0):
        intelligence.predictive.add_sample("room-temperature", value, "sensor-1")
    prediction = intelligence.predictive.forecast("room-temperature", 2)
    assert prediction["execution_authority"] is False

    capability = intelligence.capabilities.register(
        "uwb_indoor_positioning",
        provider="phone-hardware",
        device_id="phone-1",
        available=False,
        evidence_level="declared",
        metadata={"reason": "hardware unavailable"},
    )
    assert capability["available"] is False
    assert capability["execution_authority"] is False


def test_architecture_permanently_separates_knowledge_prediction_and_learning_from_action(tmp_path):
    intelligence = v3(tmp_path)
    architecture = intelligence.architecture()
    assert architecture["execution_authority"] is False
    text = " ".join(architecture["permanent_invariants"])
    assert "Knowing what is happening" in text
    assert "Predicting the correct action" in text
    assert "Learning how to perform an action" in text
