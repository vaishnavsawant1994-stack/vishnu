from __future__ import annotations

import asyncio
import time

from sensorium.context_service import MobileContextService
from sensorium.sensor_health import SensorHealthMonitor
from sensorium.sensor_permissions import SensorPermissionStore
from sensorium.world_model import TemporalWorldModel


class Registry:
    def is_active(self, _device):
        return True

    def authorize(self, _device, _scope):
        return True


class Gateway:
    def __init__(self):
        self.last_command = None

    async def request(self, target, command, timeout=15):
        self.last_command = command
        if command.action == "sensor_session_start":
            return {
                "device_id": target,
                "ok": True,
                "result": {
                    "active": False,
                    "consent_required": True,
                    "sensor": command.parameters["sensor"],
                    "resource_id": command.parameters["resource_id"],
                },
            }
        if command.action == "sensor_snapshot":
            return {
                "device_id": target,
                "ok": True,
                "result": {
                    "sensors": {
                        "location": {
                            "available": True,
                            "accuracy_m": 10,
                            "captured_at": time.time(),
                            "freshness_seconds": 30,
                            "confidence": 0.95,
                        }
                    },
                    "sessions": {
                        "location": {
                            "local_consent": True,
                            "resource_id": "*",
                            "sensor_session_id": "local-session-proof-123",
                            "expires_at_epoch": time.time() + 300,
                        }
                    },
                },
            }
        raise AssertionError(command.action)


def test_permission_store_persists_requesting_device_for_active_session_and_audit(tmp_path):
    store = SensorPermissionStore(tmp_path / "permissions.sqlite3")
    state = store.grant_session(
        "phone",
        "location",
        session_id="session-proof-123",
        requested_by_device_id="laptop-controller",
        ttl_seconds=300,
    )
    assert state["requested_by_device_id"] == "laptop-controller"
    audit = store.audit("phone")
    assert audit[0]["requested_by_device_id"] == "laptop-controller"
    store.revoke_session("phone", "location")
    revoked = store.audit("phone")[0]
    assert revoked["requested_by_device_id"] == "laptop-controller"


def test_mobile_requester_is_sent_to_phone_and_attached_when_local_proof_arrives(tmp_path):
    gateway = Gateway()
    permissions = SensorPermissionStore(tmp_path / "permissions.sqlite3")
    service = MobileContextService(
        Registry(),
        gateway,
        permissions=permissions,
        health=SensorHealthMonitor(),
        world=TemporalWorldModel(tmp_path / "world.sqlite3"),
    )
    request = asyncio.run(
        service.request_session(
            "laptop-controller",
            "phone",
            sensor="location",
            reason="Need location for the owner's current task",
        )
    )
    assert request["consent_required"] is True
    assert gateway.last_command.parameters["requesting_device_id"] == "laptop-controller"

    asyncio.run(service.snapshot("laptop-controller", "phone", sensors=["location"]))
    active = permissions.permission("phone", "location")
    assert active["mode"] == "session"
    assert active["requested_by_device_id"] == "laptop-controller"
    assert active["session_id"] == "local-session-proof-123"
