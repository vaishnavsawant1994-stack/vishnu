from __future__ import annotations

import json
import subprocess
import sys
import zipfile

import pytest

from products.artifact_builders import ArtifactBuilderError, ProductArtifactBuilder
from products.build_lifecycle import ProductBuildLifecycle
from products.store import ProductStore


def _runtime(tmp_path):
    store = ProductStore(tmp_path / "products.sqlite3")
    lifecycle = ProductBuildLifecycle(store.path)
    builder = ProductArtifactBuilder(store, lifecycle, tmp_path / "artifacts")
    return store, lifecycle, builder


def _build(store, product_id, target):
    request = store.request_build(product_id, target=target)
    assert request is not None
    return request


def test_web_builder_generates_verified_secret_free_artifact(tmp_path):
    store, lifecycle, builder = _runtime(tmp_path)
    product = store.create(
        name="ACME Research Employee",
        product_type="ai_employee",
        targets=["web"],
    )
    store.set_ai_policy(
        product["id"],
        {
            "mode": "client_api",
            "provider": "openai",
            "model": "client-model",
            "secret_ref": "vault://owner/acme/openai",
        },
    )
    store.add_component(
        product["id"],
        component_type="agent",
        component_ref="agent.research",
        name="Research Agent",
        config={"instructions": "Research the requested company."},
    )
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], "web")

    completed = builder.execute(product["id"], request["id"])
    assert completed["status"] == "succeeded"
    assert completed["metadata"]["artifact_ready"] is True
    assert completed["metadata"]["artifact_uri"].startswith("product-artifact://")
    assert len(completed["checksum"]) == 64

    path, resolved = builder.resolve_artifact(product["id"], request["id"])
    assert resolved["id"] == request["id"]
    assert path.name.endswith("-web.zip")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {"index.html", "runtime.js", "runtime.css", "manifest.json"} <= names
        manifest_text = archive.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
        assert "vault://owner/acme/openai" not in manifest_text
        assert "secret_ref" not in manifest_text
        assert manifest["ai_policy"]["credentials"] == "runtime-provisioned"
        capabilities = json.loads(archive.read("runtime-capabilities.json"))
        assert capabilities["owner_source_bundled"] is False
        assert capabilities["owner_data_bundled"] is False
        assert capabilities["credentials_bundled"] is False

    # Execution is idempotent once verified evidence exists.
    again = builder.execute(product["id"], request["id"])
    assert again["checksum"] == completed["checksum"]


def test_pwa_builder_contains_installable_shell(tmp_path):
    store, _lifecycle, builder = _runtime(tmp_path)
    product = store.create(name="Field Assistant", targets=["pwa"])
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], "pwa")
    completed = builder.execute(product["id"], request["id"])
    path, _ = builder.resolve_artifact(product["id"], request["id"])
    assert completed["metadata"]["artifact_ready"] is True
    with zipfile.ZipFile(path) as archive:
        assert "app.webmanifest" in archive.namelist()
        assert "service-worker.js" in archive.namelist()
        webmanifest = json.loads(archive.read("app.webmanifest"))
        assert webmanifest["display"] == "standalone"


@pytest.mark.parametrize("target", ["api", "worker"])
def test_server_bundle_boots_without_owner_vishnu_source(tmp_path, target):
    store, _lifecycle, builder = _runtime(tmp_path)
    product = store.create(name=f"Standalone {target}", product_type="automation", targets=[target])
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], target)
    builder.execute(product["id"], request["id"])
    path, _ = builder.resolve_artifact(product["id"], request["id"])

    extract = tmp_path / f"extract-{target}"
    with zipfile.ZipFile(path) as archive:
        archive.extractall(extract)
    result = subprocess.run(
        [sys.executable, str(extract / "runtime.py"), "--check"],
        cwd=extract,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    status = json.loads(result.stdout)
    assert status["ok"] is True
    assert status["target"] == target
    assert status["component_execution"] == "runtime-connector-required"
    assert not (extract / "app").exists()
    assert not (extract / "memory").exists()


def test_frozen_version_required_and_same_failed_build_can_retry(tmp_path):
    store, lifecycle, builder = _runtime(tmp_path)
    product = store.create(name="Freeze First", targets=["web"])
    request = _build(store, product["id"], "web")

    with pytest.raises(ArtifactBuilderError, match="must be frozen"):
        builder.execute(product["id"], request["id"])
    failed = lifecycle.ensure(builder._raw_build(product["id"], request["id"]))
    assert failed["status"] == "failed"
    assert failed["metadata"]["artifact_ready"] is False

    store.create_version(product["id"], version="0.1.0")
    retried = builder.execute(product["id"], request["id"])
    assert retried["status"] == "succeeded"
    assert retried["metadata"]["artifact_ready"] is True


def test_native_target_remains_fail_closed(tmp_path):
    store, lifecycle, builder = _runtime(tmp_path)
    product = store.create(name="Native Product", targets=["android"])
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], "android")

    with pytest.raises(ArtifactBuilderError, match="No verified in-process builder"):
        builder.execute(product["id"], request["id"])
    still_requested = lifecycle.ensure(builder._raw_build(product["id"], request["id"]))
    assert still_requested["status"] == "requested"
    assert still_requested["metadata"]["artifact_ready"] is False


def test_download_resolution_detects_tampered_artifact(tmp_path):
    store, _lifecycle, builder = _runtime(tmp_path)
    product = store.create(name="Tamper Check", targets=["web"])
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], "web")
    builder.execute(product["id"], request["id"])
    path, _ = builder.resolve_artifact(product["id"], request["id"])
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ArtifactBuilderError, match="checksum"):
        builder.resolve_artifact(product["id"], request["id"])


def test_download_resolution_rejects_malicious_artifact_uri(tmp_path):
    store, _lifecycle, builder = _runtime(tmp_path)
    product = store.create(name="Traversal Check", targets=["web"])
    store.create_version(product["id"], version="0.1.0")
    request = _build(store, product["id"], "web")
    builder.execute(product["id"], request["id"])
    with store.con() as con:
        con.execute(
            "UPDATE product_build_lifecycle SET artifact_uri=? WHERE build_id=?",
            (f"product-artifact://{product['id']}/{request['id']}/../../outside.zip", request["id"]),
        )

    with pytest.raises(ArtifactBuilderError, match="invalid"):
        builder.resolve_artifact(product["id"], request["id"])
