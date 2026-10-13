from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from future_intelligence.capability_forge import (
    CapabilityForgeLifecycle,
    CapabilityForgeWorkBridge,
    build_capability_forge,
)
from future_intelligence.work_orchestration.store import WorkStore
from integrations.discovery.catalog_store import CapabilityCatalogStore
from server.capability_forge_api import capability_forge_router


class Registry:
    def authenticate(self, device_id, token):
        return device_id == "owner-device" and token == "good-token"

    def is_active(self, device_id):
        return device_id == "owner-device"

    def authorize(self, device_id, scope):
        return device_id == "owner-device" and scope == "device:admin"


def _client(tmp_path):
    catalog = CapabilityCatalogStore(tmp_path / "capability-catalog.sqlite3")
    service = build_capability_forge(tmp_path, catalog=catalog)
    work_store = WorkStore(tmp_path / "work.sqlite3")
    work_bridge = CapabilityForgeWorkBridge(work_store)
    lifecycle = CapabilityForgeLifecycle(tmp_path / "capability-forge.sqlite3")
    runtime = {
        "settings": SimpleNamespace(data_dir=tmp_path),
        "device_registry": Registry(),
        "capability_forge": service,
        "capability_forge_store": service.store,
        "capability_forge_work": work_bridge,
        "capability_forge_lifecycle": lifecycle,
        "capability_catalog": catalog,
        "capability_forge_activation": None,
        "capability_forge_build_factory": lambda: None,
        "engineering": None,
        "events": None,
        "agent_executor": SimpleNamespace(reauth_ttl_seconds=300),
    }
    app = FastAPI()
    app.include_router(capability_forge_router(runtime))
    client = TestClient(app)
    client.cookies.set("pa_device", "owner-device")
    client.cookies.set("pa_token", "good-token")
    return client, runtime


def test_forge_owner_api_requires_trusted_admin_device(tmp_path):
    client, _runtime = _client(tmp_path)
    client.cookies.clear()
    response = client.get("/iphone/api/owner/forge/summary")
    assert response.status_code == 401


def test_forge_proposal_and_work_projection_remain_nonexecuting(tmp_path):
    client, runtime = _client(tmp_path)
    proposal = client.post(
        "/iphone/api/owner/forge/proposals",
        json={
            "source": "conversation",
            "capability_name": "Pure score calculator",
            "requested_outcome": "Calculate a reusable normalized score from JSON inputs.",
            "required_operations": ["calculate_score"],
            "preferred_route": "generated",
            "requirements": {
                "inputs": {"type": "object"},
                "outputs": {"type": "object"},
                "acceptance_criteria": ["returns the expected normalized score"],
                "metadata": {"entrypoint": "capability.py:run"},
            },
        },
    )
    assert proposal.status_code == 200, proposal.text
    body = proposal.json()
    assert body["plan"]["route"] == "generated"

    projected = client.post(
        "/iphone/api/owner/forge/work",
        json={
            "spec_id": body["spec"]["id"],
            "plan_id": body["plan"]["id"],
            "repository": "vaishnavsawant1994-stack/vishnu",
            "allowed_paths": ["generated-capabilities/score-calculator"],
        },
    )
    assert projected.status_code == 200, projected.text
    work = projected.json()["work_order"]
    assert work["status"] == "draft"
    assert projected.json()["queued"] is False
    assert projected.json()["execution_started"] is False
    assert runtime["capability_forge_work"].work_store.get_order(work["id"]).status.value == "draft"

    attempted = client.post(
        f"/iphone/api/owner/forge/work/{work['id']}/build",
        json={"version": "1.0.0", "source_root": "generated-capabilities/score-calculator"},
    )
    assert attempted.status_code == 503 or attempted.status_code == 409
