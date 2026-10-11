from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from products.build_lifecycle import ProductBuildLifecycle
from products.store import ProductStore
from server.products_api import products_router


class TrustedRegistry:
    def authenticate(self, device_id: str, token: str) -> bool:
        return device_id == "owner-device" and token == "owner-token"

    def authorize(self, device_id: str, capability: str) -> bool:
        return device_id == "owner-device" and capability == "ai:chat"


def client_for(tmp_path):
    store = ProductStore(tmp_path / "products.sqlite3")
    runtime = {"device_registry": TrustedRegistry()}
    app = FastAPI()
    app.include_router(products_router(runtime, store))
    client = TestClient(app)
    client.cookies.set("pa_device", "owner-device")
    client.cookies.set("pa_token", "owner-token")
    return client, store


def test_runner_readiness_reports_enabled_target_authority_without_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("VISHNU_PRODUCT_RUNNER_TOKEN", raising=False)
    client, store = client_for(tmp_path)
    product = store.create(name="Portable Operations Employee", targets=["linux", "android", "web"])
    linux = store.request_build(product["id"], target="linux")
    assert linux

    response = client.get(f"/iphone/api/products/{product['id']}/runner-readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == product["id"]
    assert payload["platform_runner_auth_configured"] is False

    targets = {item["target"]: item for item in payload["targets"]}
    assert set(targets) == {"linux", "android", "web"}
    assert targets["linux"]["builder"] == "platform-runner"
    assert targets["linux"]["compiler_available"] is True
    assert targets["linux"]["runner_configured"] is False
    assert targets["linux"]["production_requirements"] == ["compile"]
    assert targets["linux"]["latest_build"]["id"] == linux["id"]
    assert targets["linux"]["latest_build"]["status"] == "requested"
    assert targets["linux"]["latest_build"]["artifact_ready"] is False
    assert targets["android"]["production_requirements"] == ["compile", "release-signature"]
    assert targets["android"]["latest_build"] is None
    assert targets["web"]["builder"] == "local-runtime"
    assert targets["web"]["runner_configured"] is True

    serialized = response.text.lower()
    assert "lease_token" not in serialized
    assert "runner-token" not in serialized
    assert "secret" not in serialized


def test_runner_readiness_reflects_verified_platform_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("VISHNU_PRODUCT_RUNNER_TOKEN", "qualification-runner-token")
    client, store = client_for(tmp_path)
    product = store.create(name="Qualified Linux Product", targets=["linux"])
    build = store.request_build(product["id"], target="linux")
    assert build
    lifecycle = ProductBuildLifecycle(store.path)
    lifecycle.ensure(build)
    lifecycle.update(product["id"], build["id"], status="running")

    # Simulate the same evidence projection written by ProductPlatformBuildJobs
    # before the verified-builder lifecycle transition.
    with store.con() as con:
        row = con.execute("SELECT metadata_json FROM product_builds WHERE id=?", (build["id"],)).fetchone()
        import json
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata["platform_runner"] = {
            "evidence": {
                "schema": "vishnu.platform-runner-evidence/v1",
                "compiler_verified": True,
                "signing_verified": False,
                "provisioning_verified": False,
                "notarization_verified": False,
                "metadata": {},
            }
        }
        con.execute("UPDATE product_builds SET metadata_json=? WHERE id=?", (json.dumps(metadata), build["id"]))
    lifecycle.update(
        product["id"],
        build["id"],
        status="succeeded",
        artifact_name="qualified.deb",
        artifact_uri=f"product-artifact://{product['id']}/{build['id']}/qualified.deb",
        checksum="a" * 64,
        signing_verified=False,
        verified_builder=True,
    )

    response = client.get(f"/iphone/api/products/{product['id']}/runner-readiness")
    assert response.status_code == 200
    target = response.json()["targets"][0]
    assert target["runner_configured"] is True
    assert target["latest_build"]["status"] == "succeeded"
    assert target["latest_build"]["artifact_ready"] is True
    assert target["latest_build"]["compiler_verified"] is True
