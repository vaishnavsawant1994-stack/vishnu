import asyncio
import base64
import io

import pytest
from PIL import Image

from sensorium.camera import CameraVisionService, MAX_CAMERA_FRAME_BYTES


class FakeRegistry:
    def __init__(self, permissions): self.permissions = permissions
    def authorize(self, device_id, scope): return scope in self.permissions.get(device_id, set())
    def is_active(self, device_id): return device_id in self.permissions


class FakeSensorPermissions:
    def __init__(self): self.rows = {}
    def can_request(self, device_id, sensor, resource_id): return self.rows.get((device_id, resource_id), {"mode":"ask"})["mode"] != "never"
    def permission(self, device_id, sensor, resource_id): return self.rows.get((device_id, resource_id), {"device_id":device_id,"sensor":sensor,"resource_id":resource_id,"mode":"ask","session_id":None,"expires_at":None})
    def grant_session(self, device_id, sensor, resource_id, ttl_seconds=300, session_id=None):
        current=self.permission(device_id,sensor,resource_id)
        if current["mode"]=="never": raise PermissionError("disabled")
        row={"device_id":device_id,"sensor":sensor,"resource_id":resource_id,"mode":"session","session_id":session_id or "session-123","expires_at":9999999999.0};self.rows[(device_id,resource_id)]=row;return row
    def allows(self, device_id, sensor, resource_id, session_id=None):
        row=self.permission(device_id,sensor,resource_id);return row["mode"]=="session" and (not session_id or row["session_id"]==session_id)
    def revoke_session(self, device_id, sensor, resource_id): self.rows[(device_id,resource_id)]={"device_id":device_id,"sensor":sensor,"resource_id":resource_id,"mode":"ask","session_id":None,"expires_at":None};return self.rows[(device_id,resource_id)]
    def set_policy(self, device_id, sensor, mode, resource_id): self.rows[(device_id,resource_id)]={"device_id":device_id,"sensor":sensor,"resource_id":resource_id,"mode":mode,"session_id":None,"expires_at":None};return self.rows[(device_id,resource_id)]
    def list_device(self, device_id, sensor=None): return [v for (d,_),v in self.rows.items() if d==device_id]


class FakeModels:
    def __init__(self): self.sensitivity = None; self.messages = None
    def _run(self, capability, call, *, sensitivity="internal"):
        assert capability == "vision"; self.sensitivity = sensitivity; return call(object())
    def _chat_call(self, provider, messages, temperature):
        self.messages = messages; assert temperature == 0.1; return "A desk and a coffee mug are visible."


class FakeGateway:
    def __init__(self): self.actions = []
    async def request(self, device_id, command, timeout=15):
        self.actions.append((device_id, command.action, dict(command.parameters), timeout))
        if command.action == "camera_status": result = {"active": True, "permission": "granted", "foreground_required": True, "camera_id":"mobile:front"}
        elif command.action == "camera_session_start": result = {"active": False, "consent_required": True, "foreground_required": True}
        elif command.action == "camera_session_stop": result = {"stopped": True}
        elif command.action == "camera_list": result = {"cameras":[{"camera_id":"mobile:front","label":"Front","facing":"front","external":False}]}
        elif command.action == "camera_snapshot":
            result = {"mime_type":"image/jpeg","base64":base64.b64encode(jpeg_bytes()).decode(),"width":64,"height":48,"facing":"front","camera_id":"mobile:front","sensor_session_id":"local-session-123","captured_at":"2026-10-15T10:00:00Z"}
        else: raise AssertionError(f"unexpected action: {command.action}")
        return {"device_id":device_id,"ok":True,"result":result}


def jpeg_bytes(width=64,height=48):
    out=io.BytesIO();Image.new("RGB",(width,height),(80,120,160)).save(out,"JPEG",quality=80);return out.getvalue()

def data_url(payload=None): return "data:image/jpeg;base64,"+base64.b64encode(payload or jpeg_bytes()).decode()

def service_for(registry,gateway=None,models=None,permissions=None): return CameraVisionService(registry,gateway,models or FakeModels(),sensor_permissions=permissions or FakeSensorPermissions())


def test_browser_snapshot_is_sensitive_ephemeral_and_has_no_action_authority():
    registry=FakeRegistry({"web":{"device:read","sensor:camera"}});models=FakeModels();permissions=FakeSensorPermissions();permissions.grant_session("web","camera","browser:default",session_id="browser-session")
    service=service_for(registry,models=models,permissions=permissions)
    result=service.analyze_browser_snapshot("web",data_url=data_url(),question="What is on the table?",resource_id="browser:default",sensor_session_id="browser-session")
    assert result["analysis"]=="A desk and a coffee mug are visible."
    assert result["raw_frame_retained"] is False and result["privacy_processed"] is True
    assert result["biometric_identity_enabled"] is False and result["execution_authority"] is False
    assert "data_url" not in result and "base64" not in result
    assert models.sensitivity=="sensitive" and models.messages[0]["role"]=="system"
    assert "never grants action authority" in models.messages[0]["content"]


def test_browser_snapshot_requires_sensor_scope_and_active_session():
    permissions=FakeSensorPermissions()
    service=service_for(FakeRegistry({"web":{"device:read"}}),permissions=permissions)
    with pytest.raises(PermissionError): service.analyze_browser_snapshot("web",data_url=data_url(),resource_id="browser:default",sensor_session_id="s")
    service=service_for(FakeRegistry({"web":{"device:read","sensor:camera"}}),permissions=permissions)
    with pytest.raises(PermissionError): service.analyze_browser_snapshot("web",data_url=data_url(),resource_id="browser:default",sensor_session_id="s")


def test_invalid_and_oversized_camera_frames_are_rejected_before_model_call():
    registry=FakeRegistry({"web":{"device:read","sensor:camera"}});permissions=FakeSensorPermissions();permissions.grant_session("web","camera","browser:default",session_id="s-session")
    service=service_for(registry,permissions=permissions)
    with pytest.raises(ValueError): service.analyze_browser_snapshot("web",data_url="data:text/plain;base64,Zm9v",resource_id="browser:default",sensor_session_id="s-session")
    with pytest.raises(ValueError): service.analyze_browser_snapshot("web",data_url=data_url(b"x"*(MAX_CAMERA_FRAME_BYTES+1)),resource_id="browser:default",sensor_session_id="s-session")


def test_cross_device_mobile_camera_requires_sensitive_admin_and_sensor_permissions():
    registry=FakeRegistry({"controller":{"device:read","memory:sensitive","sensor:camera"},"phone":{"device:read","sensor:camera"}})
    service=service_for(registry,FakeGateway())
    with pytest.raises(PermissionError): asyncio.run(service.status("controller","phone"))


def test_mobile_snapshot_proves_local_sensor_session_and_strips_raw_frame():
    registry=FakeRegistry({"controller":{"device:read","memory:sensitive","device:admin","sensor:camera"},"phone":{"device:read","sensor:camera"}})
    gateway=FakeGateway();models=FakeModels();permissions=FakeSensorPermissions();service=service_for(registry,gateway,models,permissions)
    result=asyncio.run(service.snapshot("controller","phone",question="What can you see?",facing="front"))
    assert gateway.actions[0][1]=="camera_snapshot"
    assert permissions.allows("phone","camera","mobile:front",session_id="local-session-123")
    assert result["target_device_id"]=="phone" and result["raw_frame_retained"] is False and "base64" not in result
    assert models.sensitivity=="sensitive"


def test_mobile_start_only_requests_consent_and_never_grants_sensor_session():
    registry=FakeRegistry({"controller":{"device:read","memory:sensitive","device:admin","sensor:camera"},"phone":{"device:read","sensor:camera"}})
    gateway=FakeGateway();permissions=FakeSensorPermissions();service=service_for(registry,gateway,permissions=permissions)
    result=asyncio.run(service.start("controller","phone",facing="back"))
    assert gateway.actions[0][1]=="camera_session_start"
    assert gateway.actions[0][2]=={"facing":"back","camera_id":"mobile:back"}
    assert result["consent_required"] is True
    assert permissions.permission("phone","camera","mobile:back")["mode"]=="ask"
    assert "base64" not in result and "data_url" not in result


def test_mobile_sources_keep_each_camera_independently_governed():
    registry=FakeRegistry({"controller":{"device:read","memory:sensitive","device:admin","sensor:camera"},"phone":{"device:read","sensor:camera"}})
    service=service_for(registry,FakeGateway())
    rows=asyncio.run(service.mobile_sources("controller","phone"))
    assert rows[0]["camera_id"]=="mobile:front"
    assert rows[0]["permission"]["mode"]=="ask"
