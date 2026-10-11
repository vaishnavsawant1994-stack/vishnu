from __future__ import annotations

import base64
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from products.platform_jobs import RUNNER_TOKEN_ENV
from products.signing import PUBLIC_KEY_ENV, SIGNING_KEY_ENV
from products.store import ProductStore
from server.product_runner_queue_api import product_runner_queue_router


def configure_signing(monkeypatch):
    key = Ed25519PrivateKey.generate()
    private_raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv(SIGNING_KEY_ENV, base64.b64encode(private_raw).decode("ascii"))
    monkeypatch.setenv(PUBLIC_KEY_ENV, base64.b64encode(public_raw).decode("ascii"))


def app_client(tmp_path, monkeypatch):
    configure_signing(monkeypatch)
    monkeypatch.setenv(RUNNER_TOKEN_ENV, "qualification-runner-token")
    store = ProductStore(tmp_path / "products.sqlite3")
    product = store.create(name="Queue API Product", targets=["linux"])
    store.create_version(product["id"], version="0.1.0")
    build = store.request_build(product["id"], target="linux")
    assert build
    runtime = {"settings": SimpleNamespace(data_dir=tmp_path)}
    app = FastAPI()
    app.include_router(product_runner_queue_router(runtime, store))
    return TestClient(app), store, product, build


def auth_headers(**extra):
    return {
        "Authorization": "Bearer qualification-runner-token",
        "X-Vishnu-Runner-ID": "linux-runner-qualification",
        **extra,
    }


def test_runner_claim_requires_bearer_authentication(tmp_path, monkeypatch):
    client, _store, _product, _build = app_client(tmp_path, monkeypatch)
    assert client.post("/iphone/api/products/runner/claim?target=linux").status_code == 401
    assert client.post(
        "/iphone/api/products/runner/claim?target=linux",
        headers={"Authorization": "Bearer wrong", "X-Vishnu-Runner-ID": "runner"},
    ).status_code == 401


def test_runner_claim_returns_signed_job_and_lease(tmp_path, monkeypatch):
    client, _store, product, build = app_client(tmp_path, monkeypatch)
    response = client.post("/iphone/api/products/runner/claim?target=linux", headers=auth_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.vishnu.product-build-job+zip")
    assert response.headers["x-vishnu-product-id"] == product["id"]
    assert response.headers["x-vishnu-build-id"] == build["id"]
    assert response.headers["x-vishnu-build-target"] == "linux"
    assert len(response.headers["x-vishnu-runner-lease"]) >= 32
    assert response.headers["x-vishnu-build-job-sha256"]
    assert response.content.startswith(b"PK")

    # The first claim is exclusive while its lease is active.
    empty = client.post("/iphone/api/products/runner/claim?target=linux", headers=auth_headers())
    assert empty.status_code == 204


def test_runner_heartbeat_is_bound_to_lease_token(tmp_path, monkeypatch):
    client, _store, _product, build = app_client(tmp_path, monkeypatch)
    claimed = client.post("/iphone/api/products/runner/claim?target=linux", headers=auth_headers())
    token = claimed.headers["x-vishnu-runner-lease"]

    denied = client.post(
        f"/iphone/api/products/runner/{build['id']}/heartbeat",
        headers={"Authorization": "Bearer qualification-runner-token", "X-Vishnu-Runner-Lease": "wrong"},
    )
    assert denied.status_code == 409

    heartbeat = client.post(
        f"/iphone/api/products/runner/{build['id']}/heartbeat",
        headers={"Authorization": "Bearer qualification-runner-token", "X-Vishnu-Runner-Lease": token},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["lease"]["state"] == "active"


def test_queue_status_never_returns_lease_material(tmp_path, monkeypatch):
    client, _store, _product, _build = app_client(tmp_path, monkeypatch)
    claimed = client.post("/iphone/api/products/runner/claim?target=linux", headers=auth_headers())
    token = claimed.headers["x-vishnu-runner-lease"]
    status = client.get(
        "/iphone/api/products/runner/status",
        headers={"Authorization": "Bearer qualification-runner-token"},
    )
    assert status.status_code == 200
    serialized = status.text
    assert token not in serialized
    assert "lease_token_hash" not in serialized
