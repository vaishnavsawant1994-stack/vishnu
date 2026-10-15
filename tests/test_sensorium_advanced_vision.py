import io
import json
import sqlite3
import time

import pytest
from PIL import Image

from sensorium.biometrics import BiometricIdentityStore
from sensorium.fusion import SensorFusionContext
from sensorium.live_vision import LiveVisionManager
from sensorium.privacy import PrivacyOptions, sanitize_image, scene_delta, scene_fingerprint
from sensorium.sensor_permissions import SensorPermissionStore
from sensorium.visual_memory import VisualMemoryManager


class FakeEvents:
    def __init__(self): self.rows=[]
    def emit(self,event,**payload): self.rows.append((event,payload))


class FakeVault:
    def __init__(self): self.rows={}
    def get(self,key): return self.rows.get(key)
    def set(self,key,value): self.rows[key]=value
    def delete(self,key): self.rows.pop(key,None)


class FakeMemory:
    def __init__(self): self.rows=[]
    def remember(self,**kwargs): self.rows.append(kwargs); return f"memory-{len(self.rows)}"


def image_bytes(size=(320,240), color=(120,80,40)):
    out=io.BytesIO();Image.new("RGB",size,color).save(out,"JPEG",quality=90);return out.getvalue()


def test_sensor_permission_has_no_persistent_allow_and_restart_invalidates_session(tmp_path):
    path=tmp_path/"sensor.sqlite3";store=SensorPermissionStore(path)
    assert store.permission("device","camera","front")["mode"]=="ask"
    with pytest.raises(ValueError): store.set_policy("device","camera","always","front")
    store.set_policy("device","camera","never","front")
    with pytest.raises(PermissionError): store.grant_session("device","camera","front")
    store.set_policy("device","camera","ask","front")
    grant=store.grant_session("device","camera","front",session_id="temporary-session")
    assert grant["mode"]=="session" and store.allows("device","camera","front",session_id="temporary-session")
    restarted=SensorPermissionStore(path)
    assert restarted.permission("device","camera","front")["mode"]=="ask"
    assert not restarted.allows("device","camera","front",session_id="temporary-session")


def test_biometric_permission_defaults_never():
    # A separate biometric sensor is fail-closed even before the identity store is considered.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        store=SensorPermissionStore(Path(directory)/"s.sqlite3")
        assert store.permission("owner","biometric","*")["mode"]=="never"


def test_privacy_crop_downsample_redaction_and_face_fail_closed():
    raw=image_bytes((1600,1200))
    processed,meta=sanitize_image(raw,{"max_edge":640,"crop":{"x":0,"y":0,"width":0.5,"height":1},"redact_regions":[{"x":0,"y":0,"width":0.25,"height":0.25}]})
    image=Image.open(io.BytesIO(processed))
    assert max(image.size)<=640 and meta["cropped"] is True and meta["redacted_regions"]==1
    with pytest.raises(PermissionError): sanitize_image(raw,{"require_face_redaction":True,"faces_processed":False})
    processed,_=sanitize_image(raw,{"require_face_redaction":True,"faces_processed":True})
    assert processed.startswith(b"\xff\xd8")


def test_scene_change_fingerprint_skips_stable_frames():
    first=scene_fingerprint(image_bytes(color=(20,20,20)));same=scene_fingerprint(image_bytes(color=(20,20,20)));changed=scene_fingerprint(image_bytes(color=(240,240,240)))
    assert scene_delta(first,same)<0.001 and scene_delta(first,changed)>0.5


def test_live_vision_is_bounded_and_scene_gated():
    events=FakeEvents();live=LiveVisionManager(events=events)
    session=live.start(controller_device_id="a",target_device_id="a",resource_id="front",question="watch",sample_fps=99,duration_seconds=99999,max_frames=2,max_bytes=1_000_000,max_model_calls=1)
    assert session.sample_interval==1.0 and session.expires_at-session.started_at<=601
    live.reserve_tick(session.id,frame_bytes=100)
    with pytest.raises(RuntimeError,match="interval"): live.reserve_tick(session.id,frame_bytes=100)
    session.last_sample_at=0
    assert live.scene_decision(session.id,(1,2,3),delta=1.0) is True
    assert live.scene_decision(session.id,(1,2,3),delta=0.0) is False
    live.reserve_model_call(session.id)
    with pytest.raises(RuntimeError,match="model budget"): live.reserve_model_call(session.id)


def test_visual_memory_none_description_and_encrypted_image(tmp_path):
    memory=FakeMemory();vault=FakeVault();manager=VisualMemoryManager(memory,data_dir=tmp_path,vault=vault)
    assert manager.remember(mode="none",analysis="nothing",source="camera",device_id="d")["memory_id"] is None
    desc=manager.remember(mode="description",analysis="router has three cables",source="camera",device_id="d")
    assert desc["memory_id"]=="memory-1" and memory.rows[0]["content"]=="router has three cables" and not memory.rows[0]["evidence"]
    raw=image_bytes((80,60));saved=manager.remember(mode="image",analysis="privacy processed",source="camera",device_id="d",sanitized_image=raw,metadata={"width":80,"height":60,"mime_type":"image/jpeg"})
    assert saved["image_ref"].startswith("visual-memory:") and manager._read_blob_for_test_or_explicit_retrieval(saved["image_ref"])==raw
    blob=next((tmp_path/"visual-memory").glob("*.vimg")).read_bytes()
    assert raw not in blob and b"router has three cables" not in blob


def test_biometric_identity_is_explicit_encrypted_and_deletable(tmp_path):
    vault=FakeVault();store=BiometricIdentityStore(tmp_path/"bio.sqlite3",vault=vault)
    assert store.enabled() is False
    with pytest.raises(PermissionError): store.set_enabled(True)
    assert store.set_enabled(True,explicit_consent=True) is True
    template=[float(i+1) for i in range(16)]
    with pytest.raises(PermissionError): store.enroll("Owner",template)
    profile=store.enroll("Owner",template,explicit_consent=True)
    match=store.match(template,threshold=.99)
    assert match and match["profile_id"]==profile["profile_id"]
    with sqlite3.connect(tmp_path/"bio.sqlite3") as con:
        encrypted=con.execute("SELECT encrypted_template FROM biometric_profiles").fetchone()[0]
    assert json.dumps(template,separators=(",",":")) not in encrypted
    assert store.delete(profile["profile_id"]) is True and store.list_profiles()==[]


def test_fusion_context_is_evidence_only_and_strips_secret_payload_fields():
    fusion=SensorFusionContext();envelope=fusion.create("device",purpose="help me repair this")
    fusion.add(envelope,modality="camera",source="phone",payload={"description":"wire loose","data_url":"secret-frame"})
    fusion.add(envelope,modality="computer_control",source="runtime",payload={"state":"available","token":"secret"})
    public=envelope.public()
    assert public["execution_authority"] is False
    assert public["items"][0]["instruction_trust"]=="untrusted"
    assert public["items"][1]["instruction_trust"]=="authority_separate"
    assert "data_url" not in public["items"][0]["payload"] and "token" not in public["items"][1]["payload"]
