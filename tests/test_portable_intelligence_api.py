from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.portable_intelligence_api import portable_intelligence_router
from training.contribution_settings import ContributionSettingsService


class Registry:
    def authenticate(self, device_id, token):
        return device_id == "owner-device" and token == "owner-token"

    def is_active(self, device_id):
        return device_id == "owner-device"

    def authorize(self, device_id, scope):
        return device_id == "owner-device" and scope == "device:admin"


class PublicValue:
    def __init__(self, payload):
        self.payload = payload

    def public(self):
        return dict(self.payload)


class FakePortable:
    def __init__(self):
        self.published = 0
        self.offline = 0
        self.activated = 0

    def status(self):
        return {
            "manifest": {"manifest_id": "vim-test"},
            "hardware": {"platform": "linux", "ram_gb": 16},
            "offline_readiness": {"ready": True},
            "activation": {"activated": False},
            "vault": {"production_durable": True},
            "specialist_bindings": [],
        }

    def publish_current_restore_package(self, *, core_version):
        self.published += 1
        return PublicValue({"package_id": "virp-test", "core_version": core_version})

    def prepare_offline_pack(self):
        self.offline += 1
        return PublicValue({"pack_id": "vop-test", "ready": True})

    def activation_preflight(self, *, online=False):
        return PublicValue({"ready": True, "online": bool(online), "runtime_id": "self_hosted"})

    def activate(self, *, online=False):
        self.activated += 1
        return PublicValue({"receipt_id": "var-test", "runtime_id": "self_hosted", "online": bool(online)})


class FakeSpecialists:
    def __init__(self):
        self.rows = []

    def active_bindings(self):
        return tuple(self.rows)

    def history(self, *, limit=100):
        return tuple(self.rows[:limit])

    def bind(self, *, owner_id, specialist_role, task_domain, model_id):
        assert owner_id == "owner"
        row = PublicValue({
            "binding_id": "specialist-test",
            "specialist_role": specialist_role,
            "task_domain": task_domain,
            "model_id": model_id,
            "promotion_authority": False,
        })
        self.rows.append(row)
        return row

    def unbind(self, *, owner_id, specialist_role, task_domain):
        assert owner_id == "owner"
        changed = bool(self.rows)
        self.rows.clear()
        return changed


def _client(tmp_path):
    portable = FakePortable()
    contributions = ContributionSettingsService(tmp_path / "contributions.json")
    specialists = FakeSpecialists()
    runtime = {
        "device_registry": Registry(),
        "portable_intelligence": portable,
        "contribution_settings": contributions,
        "specialist_registry": specialists,
        "training_coordinator": SimpleNamespace(backends={"local_peft": object(), "remote_gpu:test": object()}),
        "running_git_revision": "abc123",
        # pwa_sessions intentionally omitted: this mirrors existing isolated
        # owner-router tests; production cloud_app installs fresh-reauth context.
    }
    app = FastAPI()
    app.include_router(portable_intelligence_router(runtime))
    client = TestClient(app)
    return client, portable, contributions, specialists


def _trust(client):
    client.cookies.set("pa_device", "owner-device")
    client.cookies.set("pa_token", "owner-token")


def test_summary_requires_trusted_admin_device(tmp_path):
    client, _, _, _ = _client(tmp_path)
    response = client.get("/iphone/api/owner/portable-intelligence/summary")
    assert response.status_code == 401

    _trust(client)
    response = client.get("/iphone/api/owner/portable-intelligence/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["manifest_id"] == "vim-test"
    assert payload["contributions"]["mode"] == "private"
    assert payload["remote_gpu_backend_configured"] is True
    assert payload["remote_gpu_credentials_exposed"] is False


def test_owner_can_publish_prepare_and_preflight(tmp_path):
    client, portable, _, _ = _client(tmp_path)
    _trust(client)

    published = client.post("/iphone/api/owner/portable-intelligence/publish")
    assert published.status_code == 200
    assert published.json()["package"]["package_id"] == "virp-test"
    assert portable.published == 1

    offline = client.post("/iphone/api/owner/portable-intelligence/offline-pack")
    assert offline.status_code == 200
    assert offline.json()["offline_pack"]["pack_id"] == "vop-test"
    assert portable.offline == 1

    preflight = client.post(
        "/iphone/api/owner/portable-intelligence/activation/preflight",
        json={"online": False},
    )
    assert preflight.status_code == 200
    assert preflight.json()["preflight"]["ready"] is True

    activated = client.post(
        "/iphone/api/owner/portable-intelligence/activation",
        json={"online": False},
    )
    assert activated.status_code == 200
    assert activated.json()["receipt"]["runtime_id"] == "self_hosted"
    assert portable.activated == 1


def test_contribution_preferences_remain_private_until_owner_changes_them(tmp_path):
    client, _, contributions, _ = _client(tmp_path)
    _trust(client)

    initial = client.get("/iphone/api/owner/portable-intelligence/contributions")
    assert initial.status_code == 200
    assert initial.json()["settings"]["mode"] == "private"
    assert initial.json()["documents_default_off"] is True

    changed = client.patch(
        "/iphone/api/owner/portable-intelligence/contributions",
        json={"mode": "aggregate", "agent_outcomes": True, "tool_metrics": True},
    )
    assert changed.status_code == 200
    assert changed.json()["settings"]["mode"] == "aggregate"
    assert contributions.snapshot().preferences.mode.value == "aggregate"

    unsafe = client.patch(
        "/iphone/api/owner/portable-intelligence/contributions",
        json={"documents": True},
    )
    assert unsafe.status_code == 422


def test_specialist_binding_surface_has_no_promotion_authority(tmp_path):
    client, _, _, specialists = _client(tmp_path)
    _trust(client)

    created = client.post(
        "/iphone/api/owner/portable-intelligence/specialists",
        json={"specialist_role": "coding", "task_domain": "general", "model_id": "model-active"},
    )
    assert created.status_code == 200
    assert created.json()["binding"]["promotion_authority"] is False

    listed = client.get("/iphone/api/owner/portable-intelligence/specialists")
    assert listed.status_code == 200
    assert listed.json()["promotion_authority"] is False
    assert len(listed.json()["active"]) == 1

    removed = client.request(
        "DELETE",
        "/iphone/api/owner/portable-intelligence/specialists",
        json={"specialist_role": "coding", "task_domain": "general"},
    )
    assert removed.status_code == 200
    assert removed.json()["changed"] is True
    assert specialists.rows == []
