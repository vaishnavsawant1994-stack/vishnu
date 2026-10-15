from __future__ import annotations

import asyncio
import time

import pytest

from sensorium.attention import AttentionManager
from sensorium.context_service import MobileContextService
from sensorium.episodic_memory import EpisodicMemoryManager
from sensorium.fusion import SensorFusionContext
from sensorium.iot import IoTSensorRegistry
from sensorium.l4_qualification import PhysicalDeviceQualification
from sensorium.privacy_zones import PrivacyZoneStore
from sensorium.proactive import ProactivePhysicalAssistant
from sensorium.sensor_health import SensorHealthMonitor
from sensorium.sensor_permissions import SensorPermissionStore
from sensorium.world_model import TemporalWorldModel


class FakeVault:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


class FakeMemory:
    def __init__(self):
        self.rows = []

    def remember(self, **kwargs):
        self.rows.append(kwargs)
        return f"memory-{len(self.rows)}"


class FakeRegistry:
    def is_active(self, _device):
        return True

    def authorize(self, _device, _scope):
        return True


class FakeGateway:
    async def request(self, target, command, timeout=15):
        if command.action == "sensor_snapshot":
            return {
                "device_id": target,
                "ok": True,
                "result": {
                    "sensors": {
                        "location": {
                            "available": True,
                            "latitude": 10.0,
                            "longitude": 20.0,
                            "accuracy_m": 12.0,
                            "coarse_area": "test-area",
                            "captured_at": time.time(),
                            "freshness_seconds": 60,
                            "confidence": 0.95,
                        }
                    },
                    "sessions": {
                        "location": {
                            "local_consent": True,
                            "resource_id": "*",
                            "sensor_session_id": "local-session-proof",
                            "expires_at_epoch": time.time() + 300,
                        }
                    },
                },
            }
        if command.action == "sensor_inventory":
            return {"device_id": target, "ok": True, "result": {"location": {"available": True}}}
        raise AssertionError(f"unexpected action {command.action}")


def test_sensor_permissions_are_session_only_audited_and_restart_invalidates(tmp_path):
    path = tmp_path / "sensor-permissions.sqlite3"
    store = SensorPermissionStore(path)
    assert store.permission("phone", "location")["mode"] == "ask"
    assert store.permission("phone", "biometric")["mode"] == "never"
    with pytest.raises(ValueError, match="never or ask"):
        store.set_policy("phone", "location", "always")
    store.set_policy("phone", "location", "ask", reason="owner policy")
    granted = store.grant_session(
        "phone", "location", "*", session_id="location-session-123", ttl_seconds=300,
        reason="owner tapped allow",
    )
    assert granted["mode"] == "session"
    assert store.allows("phone", "location", session_id="location-session-123") is True
    actions = [row["action"] for row in store.audit("phone")]
    assert "session_granted" in actions and "policy_changed" in actions

    restarted = SensorPermissionStore(path)
    assert restarted.permission("phone", "location")["mode"] == "ask"
    assert restarted.allows("phone", "location", session_id="location-session-123") is False


def test_revoke_all_removes_every_active_sensor_session(tmp_path):
    store = SensorPermissionStore(tmp_path / "sensor-permissions.sqlite3")
    for sensor in ("location", "motion", "microphone", "screen"):
        store.grant_session("phone", sensor, session_id=f"{sensor}-session-123", ttl_seconds=300)
    assert len(store.active_sessions("phone")) == 4
    assert store.revoke_all("phone") == 4
    assert store.active_sessions("phone") == []


def test_attention_manager_selects_minimum_relevant_sensors_without_activation():
    plan = AttentionManager().plan(
        "The router is offline and I am pointing at its cable",
        permitted={"camera", "network", "location", "microphone"},
        max_active_sensors=2,
    ).public()
    requested = [row["sensor"] for row in plan["requested"]]
    assert requested[0] == "memory"
    assert "network" in requested
    assert "camera" in requested
    assert "microphone" not in requested
    assert plan["activation_authorized"] is False


def test_attention_manager_respects_privacy_and_battery_budget():
    plan = AttentionManager().plan(
        "Look at this room and listen for the alarm",
        permitted={"camera", "microphone"},
        privacy_denied={"microphone"},
        battery_percent=10,
        max_active_sensors=6,
    )
    assert plan.battery_saver is True
    assert plan.max_active_sensors == 2
    assert "microphone" in plan.denied
    assert all(item.sensor != "microphone" for item in plan.requested)


def test_world_model_keeps_contradictions_and_current_semantic_state(tmp_path):
    model = TemporalWorldModel(tmp_path / "world.sqlite3")
    first = model.observe(
        "router", attribute="power", value="on", source="camera", modality="camera",
        confidence=0.9, freshness_seconds=60,
    )
    second = model.observe(
        "router", attribute="power", value="off", source="screen", modality="screen",
        confidence=0.95, freshness_seconds=60,
    )
    assert first["observation_id"] in second["contradictions"]
    entity = model.entity("router", include_history=True)
    assert entity["current"]["power"]["value"] == "off"
    assert any(row["contradicted"] for row in entity["history"])
    assert model.contradictions()


def test_world_relations_are_persistent_semantic_not_media(tmp_path):
    model = TemporalWorldModel(tmp_path / "world.sqlite3")
    model.ensure_entity("screwdriver", label="Screwdriver")
    model.ensure_entity("desk", kind="place", label="Desk")
    relation = model.relate("screwdriver", "on", "desk", source="camera", confidence=0.9)
    entity = model.entity("screwdriver")
    assert relation["execution_authority"] is False
    assert entity["relations"][0]["predicate"] == "on"


def test_fusion_exposes_confidence_freshness_and_cross_source_conflicts():
    fusion = SensorFusionContext()
    envelope = fusion.create("phone", purpose="network troubleshooting")
    fusion.add(
        envelope, modality="network", source="phone", payload={"connected": False},
        confidence=0.95, freshness_seconds=30,
    )
    fusion.add(
        envelope, modality="screen", source="router-ui", payload={"connected": True},
        confidence=0.8, freshness_seconds=30,
    )
    conflicts = fusion.contradictions(envelope)
    assert conflicts and conflicts[0]["field"] == "connected"
    public = envelope.public()
    assert public["items"][0]["confidence_band"] == "high"
    assert public["execution_authority"] is False


def test_sensor_health_blocks_invalid_high_severity_inputs():
    monitor = SensorHealthMonitor()
    bad = monitor.evaluate("microphone", {"muted": True, "captured_at": time.time()})
    assert bad["healthy"] is False
    assert bad["reasoning_allowed"] is False
    stale = monitor.evaluate("location", {"accuracy_m": 500, "captured_at": time.time() - 60})
    assert any(row["code"] == "location_low_accuracy" for row in stale["findings"])


def test_privacy_zones_are_encrypted_and_only_restrict(tmp_path):
    vault = FakeVault()
    store = PrivacyZoneStore(tmp_path / "zones.sqlite3", vault=vault)
    zone = store.put(
        label="Private room",
        rule={
            "context_tags": ["private-room"],
            "deny_sensors": ["camera", "microphone"],
            "require_bystander_redaction": True,
            "forbid_media_retention": True,
        },
    )
    assert zone["rule"]["deny_sensors"] == ["camera", "microphone"]
    assert any(key.startswith("sensorium.privacy_zone.") for key in vault.values)
    result = store.evaluate({"context_tags": ["private-room"]})
    assert set(result["deny_sensors"]) == {"camera", "microphone"}
    assert result["require_bystander_redaction"] is True
    assert result["forbid_media_retention"] is True
    assert result["execution_authority"] is False


def test_episodic_memory_defaults_to_semantic_retention_and_media_requires_privacy_processing(tmp_path):
    memory = FakeMemory()
    vault = FakeVault()
    manager = EpisodicMemoryManager(memory, data_dir=tmp_path, vault=vault)
    assert manager.remember(mode="none", summary="ignored", device_id="phone", modalities=["camera"])["memory_id"] is None
    saved = manager.remember(
        mode="event", summary="Connected HDMI cable B and display came on", device_id="phone",
        modalities=["camera", "audio"], event={"task": "monitor repair"},
    )
    assert saved["memory_id"] == "memory-1"
    assert memory.rows[0]["metadata"]["raw_audio_retained"] is False
    assert memory.rows[0]["metadata"]["raw_video_retained"] is False
    with pytest.raises(PermissionError, match="privacy-processed"):
        manager.remember(
            mode="media", summary="selected frame", device_id="phone", modalities=["camera"],
            selected_media=b"image", media_metadata={"privacy_processed": False},
        )


def test_iot_observation_and_action_authority_are_separate(tmp_path):
    iot = IoTSensorRegistry(tmp_path / "iot.sqlite3")
    source = iot.register(
        label="Living room thermostat", kind="thermostat",
        observe_capabilities=["temperature"], action_capabilities=["set_temperature"],
    )
    observed = iot.observe(source["source_id"], capability="temperature", payload={"celsius": 22.5})
    assert observed["execution_authority"] is False
    proposal = iot.propose_action(source["source_id"], capability="set_temperature", parameters={"celsius": 21})
    assert proposal["requires_approval"] is True
    assert proposal["execution_authority"] is False
    assert "ApprovalManager" in proposal["handoff"]


def test_proactive_assistance_is_task_bound_and_never_executes():
    assistant = ProactivePhysicalAssistant()
    session = assistant.start("phone", purpose="assemble the desk", allowed_sensors=["camera"], duration_seconds=300)
    quiet = assistant.evaluate(
        session["session_id"], sensor="camera", observation={"change": "minor"}, significance=0.2,
        message="minor change", confidence=0.9,
    )
    assert quiet["cue"] is None
    cue = assistant.evaluate(
        session["session_id"], sensor="camera", observation={"missing_screw": True}, significance=0.9,
        message="One screw appears to be missing", confidence=0.8,
    )
    assert cue["cue"]["requires_user_attention"] is True
    assert cue["acted"] is False
    with pytest.raises(PermissionError):
        assistant.evaluate(
            session["session_id"], sensor="microphone", observation={}, significance=1,
            message="not allowed", confidence=1,
        )


def test_l4_qualification_rejects_emulator_and_requires_all_real_hardware_scenarios(tmp_path):
    l4 = PhysicalDeviceQualification(tmp_path)
    with pytest.raises(PermissionError, match="real physical device"):
        l4.record("android", {"physical_device": False, "device_class": "emulator", "scenarios": {}})
    required = l4.REQUIRED["android"]
    partial = {name: True for name in required if name != "thermal_behavior"}
    status = l4.record("android", {"physical_device": True, "device_class": "Pixel test phone", "scenarios": partial})
    assert status["qualified"] is False
    assert status["level"] == "L3_or_lower"
    status = l4.record("android", {"physical_device": True, "device_class": "Pixel test phone", "scenarios": {name: True for name in required}})
    assert status["qualified"] is True
    assert status["level"] == "L4"


def test_mobile_context_requires_local_session_proof_and_does_not_persist_exact_location(tmp_path):
    permissions = SensorPermissionStore(tmp_path / "permissions.sqlite3")
    world = TemporalWorldModel(tmp_path / "world.sqlite3")
    service = MobileContextService(
        FakeRegistry(), FakeGateway(), permissions=permissions,
        health=SensorHealthMonitor(), world=world,
    )
    result = asyncio.run(service.snapshot("controller", "phone", sensors=["location"]))
    assert result["sensors"]["location"]["confidence_band"] == "high"
    assert permissions.allows("phone", "location", session_id="local-session-proof") is True
    device = world.entity("device:phone")
    value = device["current"]["location"]["value"]
    assert "latitude" not in value and "longitude" not in value
    assert value["coarse_area"] == "test-area"
