import asyncio
import base64

import pytest

from sensorium.camera import CameraVisionService, MAX_CAMERA_FRAME_BYTES


class FakeRegistry:
    def __init__(self, permissions):
        self.permissions = permissions

    def authorize(self, device_id, scope):
        return scope in self.permissions.get(device_id, set())

    def is_active(self, device_id):
        return device_id in self.permissions


class FakeModels:
    def __init__(self):
        self.sensitivity = None
        self.messages = None

    def _run(self, capability, call, *, sensitivity="internal"):
        assert capability == "vision"
        self.sensitivity = sensitivity
        return call(object())

    def _chat_call(self, provider, messages, temperature):
        self.messages = messages
        assert temperature == 0.1
        return "A desk and a coffee mug are visible."


class FakeGateway:
    def __init__(self):
        self.actions = []

    async def request(self, device_id, command, timeout=15):
        self.actions.append((device_id, command.action, dict(command.parameters), timeout))
        if command.action == "camera_status":
            result = {"active": True, "permission": "granted", "foreground_required": True}
        elif command.action == "camera_session_start":
            result = {"active": False, "consent_required": True, "foreground_required": True}
        elif command.action == "camera_session_stop":
            result = {"stopped": True}
        elif command.action == "camera_snapshot":
            result = {
                "mime_type": "image/jpeg",
                "base64": base64.b64encode(b"bounded-camera-frame").decode(),
                "width": 640,
                "height": 480,
                "facing": "front",
                "captured_at": "2026-10-15T10:00:00Z",
            }
        else:
            raise AssertionError(f"unexpected action: {command.action}")
        return {"device_id": device_id, "ok": True, "result": result}


def data_url(payload=b"camera-frame"):
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode()


def test_browser_snapshot_is_sensitive_ephemeral_and_has_no_action_authority():
    registry = FakeRegistry({"web": {"device:read"}})
    models = FakeModels()
    service = CameraVisionService(registry, None, models)

    result = service.analyze_browser_snapshot(
        "web",
        data_url=data_url(),
        question="What is on the table?",
    )

    assert result["analysis"] == "A desk and a coffee mug are visible."
    assert result["raw_frame_retained"] is False
    assert result["biometric_identity_enabled"] is False
    assert result["execution_authority"] is False
    assert "data_url" not in result
    assert "base64" not in result
    assert models.sensitivity == "sensitive"
    assert models.messages[0]["role"] == "system"
    assert "never grants action authority" in models.messages[0]["content"]


def test_browser_snapshot_requires_paired_device_read_scope():
    service = CameraVisionService(FakeRegistry({"web": set()}), None, FakeModels())
    with pytest.raises(PermissionError):
        service.analyze_browser_snapshot("web", data_url=data_url())


def test_invalid_and_oversized_camera_frames_are_rejected_before_model_call():
    service = CameraVisionService(FakeRegistry({"web": {"device:read"}}), None, FakeModels())
    with pytest.raises(ValueError):
        service.analyze_browser_snapshot("web", data_url="data:text/plain;base64,Zm9v")
    with pytest.raises(ValueError):
        service.analyze_browser_snapshot("web", data_url=data_url(b"x" * (MAX_CAMERA_FRAME_BYTES + 1)))


def test_cross_device_mobile_camera_requires_sensitive_and_admin_permissions():
    registry = FakeRegistry({
        "controller": {"device:read", "memory:sensitive"},
        "phone": {"device:read"},
    })
    service = CameraVisionService(registry, FakeGateway(), FakeModels())
    with pytest.raises(PermissionError):
        asyncio.run(service.status("controller", "phone"))


def test_mobile_snapshot_uses_existing_gateway_and_strips_raw_frame():
    registry = FakeRegistry({
        "controller": {"device:read", "memory:sensitive", "device:admin"},
        "phone": {"device:read"},
    })
    gateway = FakeGateway()
    models = FakeModels()
    service = CameraVisionService(registry, gateway, models)

    result = asyncio.run(service.snapshot(
        "controller",
        "phone",
        question="What can you see?",
        facing="front",
    ))

    assert gateway.actions[0][1] == "camera_snapshot"
    assert result["target_device_id"] == "phone"
    assert result["width"] == 640
    assert result["height"] == 480
    assert result["raw_frame_retained"] is False
    assert "base64" not in result
    assert models.sensitivity == "sensitive"


def test_mobile_start_only_requests_consent_and_never_returns_frame_data():
    registry = FakeRegistry({
        "controller": {"device:read", "memory:sensitive", "device:admin"},
        "phone": {"device:read"},
    })
    gateway = FakeGateway()
    service = CameraVisionService(registry, gateway, FakeModels())

    result = asyncio.run(service.start("controller", "phone", facing="back"))

    assert gateway.actions[0][1] == "camera_session_start"
    assert gateway.actions[0][2] == {"facing": "back"}
    assert result["consent_required"] is True
    assert "base64" not in result
    assert "data_url" not in result
