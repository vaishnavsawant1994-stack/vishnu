from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.trust_continuity_api import trust_continuity_router
from trust_continuity.integration import attach_trust_continuity_runtime


class FakeRegistry:
    OWNER_SCOPES = {"device:read", "device:admin", "memory:sensitive", "qualification:read"}

    def __init__(self):
        self.devices = {
            "trusted-phone": {
                "id": "trusted-phone",
                "name": "Phone",
                "platform": "android",
                "revoked": False,
                "permissions": sorted(self.OWNER_SCOPES),
                "last_seen_at": None,
            }
        }
        self.metadata_values = {}
        self.counter = 0

    def is_active(self, device_id):
        item = self.devices.get(device_id)
        return bool(item and not item["revoked"])

    def list(self):
        return [dict(value) for value in self.devices.values()]

    def enroll(self, name, platform):
        self.counter += 1
        device_id = f"restored-device-{self.counter:02d}"
        self.devices[device_id] = {
            "id": device_id,
            "name": name,
            "platform": platform,
            "revoked": False,
            "permissions": [],
            "last_seen_at": None,
        }
        return {"id": device_id, "name": name, "platform": platform}, f"credential-{self.counter}-not-persisted"

    def set_permissions(self, device_id, scopes):
        self.devices[device_id]["permissions"] = sorted(scopes)
        return {"scopes": sorted(scopes)}

    def set_metadata(self, device_id, key, value):
        self.metadata_values[(device_id, key)] = value
        return True

    def revoke(self, device_id):
        item = self.devices.get(device_id)
        if not item or item["revoked"]:
            return False
        item["revoked"] = True
        return True


class FakeOwnerAccess:
    def __init__(self):
        self.codes = {"GOOD-CODE"}

    def identity(self):
        return {
            "owner_id": "OWNER-0123456789ABCDEF0123456789ABCDEF",
            "vishnu_id": "VISHNU-0123456789ABCDEF0123456789ABCDEF",
            "display_name": "Owner",
        }

    def consume_recovery_code(self, code):
        candidate = str(code).strip().upper()
        if candidate not in self.codes:
            return False
        self.codes.remove(candidate)
        return True


class FakeTools:
    def __init__(self):
        self.enabled = False

    def set_emergency_stop(self, enabled):
        self.enabled = bool(enabled)


class FakeOAuth:
    def __init__(self):
        self.calls = []

    def unlink(self, provider_id, **kwargs):
        self.calls.append((provider_id, kwargs))
        return {"revoked": True}


def runtime_dict(tmp_path: Path):
    return {
        "settings": SimpleNamespace(data_dir=tmp_path),
        "device_registry": FakeRegistry(),
        "owner_access": FakeOwnerAccess(),
        "tools": FakeTools(),
        "oauth": FakeOAuth(),
        "oauth_providers": {},
        "running_git_revision": "a" * 40,
    }


def test_attach_uses_canonical_authorities_and_is_idempotent(tmp_path: Path):
    services = runtime_dict(tmp_path)
    first = attach_trust_continuity_runtime(services)
    second = attach_trust_continuity_runtime(services)
    assert first is second
    assert first.oauth is services["oauth"]
    assert first.owner_id == services["owner_access"].identity()["owner_id"]
    assert first.status()["execution_authority"] is False
    assert first.readiness.commit_sha == "a" * 40
    assert services["sensor_permissions"] is not None


def test_recovery_is_one_shot_and_never_persists_proof_or_device_credential(tmp_path: Path):
    services = runtime_dict(tmp_path)
    runtime = attach_trust_continuity_runtime(services)
    token = runtime.recovery.begin_restore(
        runtime.owner_id,
        method="recovery_code",
        destination_platform="android",
    )
    result = runtime.recovery.complete_restore(
        token,
        owner_proof="GOOD-CODE",
        device_metadata={"platform": "android", "name": "Recovered phone"},
        lost_device_id="trusted-phone",
    )
    assert result.device_credential == "credential-1-not-persisted"
    assert services["device_registry"].devices[result.restored_device_id]["permissions"] == sorted(
        FakeRegistry.OWNER_SCOPES
    )
    with pytest.raises(PermissionError):
        runtime.recovery.complete_restore(
            token,
            owner_proof="GOOD-CODE",
            device_metadata={"platform": "android"},
        )
    stored = repr(runtime.store.list("owner_restore", limit=10))
    assert "GOOD-CODE" not in stored
    assert "credential-1-not-persisted" not in stored


def test_work_engine_rejects_cycles_and_manual_dependency_bypass(tmp_path: Path):
    runtime = attach_trust_continuity_runtime(runtime_dict(tmp_path))
    with pytest.raises(ValueError, match="cycle"):
        runtime.work.create_job(
            owner_id=runtime.owner_id,
            title="cyclic",
            steps=[
                {"id": "a", "depends_on": ["b"]},
                {"id": "b", "depends_on": ["a"]},
            ],
        )
    job = runtime.work.create_job(
        owner_id=runtime.owner_id,
        title="ordered",
        steps=[{"id": "first"}, {"id": "second", "depends_on": ["first"]}],
    )
    with pytest.raises(RuntimeError, match="dependencies"):
        runtime.work.start_step(job, "second")


def test_trust_center_delegates_to_canonical_emergency_and_oauth_authorities(tmp_path: Path):
    services = runtime_dict(tmp_path)
    runtime = attach_trust_continuity_runtime(services)
    runtime.trust_center.stop_actions(actor="trusted-phone")
    assert services["tools"].enabled is True
    runtime.trust_center.emergency_stop(False, actor="trusted-phone")
    assert services["tools"].enabled is False
    runtime.trust_center.disconnect_provider("google", actor="trusted-phone")
    assert services["oauth"].calls[0][0] == "google"


def test_owner_trust_api_uses_stable_owner_identity(tmp_path: Path):
    services = runtime_dict(tmp_path)
    runtime = attach_trust_continuity_runtime(services)
    runtime.memory.remember(
        owner_id=runtime.owner_id,
        entity="router",
        predicate="location",
        value="office",
        source={"kind": "owner"},
        confidence=1.0,
    )

    def auth_device(_authorization, _device_id, _scope):
        return "trusted-phone"

    app = FastAPI()
    app.include_router(trust_continuity_router(runtime, auth_device))
    response = TestClient(app).get("/owner/trust/memory/timeline")
    assert response.status_code == 200
    facts = response.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["owner_id"] == runtime.owner_id
